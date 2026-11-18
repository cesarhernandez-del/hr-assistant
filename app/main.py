"""API web del HR Assistant: ``create_app()`` y la instancia ``app``."""

import os
import sys
import time
from pathlib import Path
from typing import List, Literal, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.auth import authenticate
from app.clock import SystemClock
from app.config import Settings, check_compliance, load_settings
from app.directory import Directory
from app.gateway import GatewayBackend
from app.llm import FakeBackend, ModelBackend, ModelUnavailable
from app.logging_json import JsonLogger
from app.metrics import Metrics
from app.orchestrator import Orchestrator
from app.pricing import Prices, load_prices
from app.ratelimit import RateLimiter
from app.resilience import ResilientBackend
from app.router import window_history
from app.request_context import (
    bind_client,
    bind_request_id,
    current_client,
    current_request_id,
    reset_request_id,
    resolve_request_id,
)
from app.tracing import build_tracer

RESPONSE_FIELDS = (
    "answer",
    "steps",
    "tools_used",
    "input_tokens",
    "output_tokens",
    "stopped",
    "model",
    "route",
    "cached_calls",
    "cost_usd",
    "intent",
    "agents_used",
    "pii_detected",
    "fallback",
)
PRODUCT_ROOT = Path(__file__).resolve().parents[1]
INDEX_PAGE = Path(__file__).resolve().parent / "static" / "index.html"
REQUEST_ID_HEADER = "X-Request-ID"
API_KEY_HEADER = "X-API-Key"


class HistoryItem(BaseModel):
    """Mensaje previo de la conversación."""

    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    """Cuerpo de ``POST /ask``."""

    question: str
    history: Optional[List[HistoryItem]] = None


def _load_directory(settings: Settings) -> Directory:
    """Carga el directorio, buscando la ruta también desde la raíz del producto.

    :param settings: Configuración validada.
    :type settings: Settings
    :return: Directorio de empleados.
    :rtype: Directory
    """
    path = settings.employees_path
    if not path.is_absolute() and not path.exists():
        path = PRODUCT_ROOT / path
    return Directory.from_file(path)


def _install_middleware(application: FastAPI, clock, logger, metrics) -> None:
    """Agrega el middleware que pone el id, mide y registra cada petición.

    :param application: Aplicación a la que se agrega.
    :type application: FastAPI
    :param clock: Reloj con ``perf()``.
    :param logger: Logger JSON.
    :type logger: JsonLogger
    :param metrics: Métricas del proceso.
    :type metrics: Metrics
    """

    @application.middleware("http")
    async def observe(request: Request, call_next):
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = bind_request_id(request_id)
        started = clock.perf()
        try:
            try:
                response = await call_next(request)
            except Exception as error:  # pylint: disable=broad-exception-caught
                logger.emit("error", error_type=type(error).__name__)
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "internal error", "request_id": request_id},
                )
            response.headers[REQUEST_ID_HEADER] = request_id
            latency_ms = (clock.perf() - started) * 1000
            extra = {}
            client = getattr(request.state, "client", None)
            if client is not None:
                extra["client"] = client
            logger.emit(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=latency_ms,
                **extra,
            )
            metrics.record_request(latency_ms, response.status_code >= 500)
            return response
        finally:
            reset_request_id(token)


def _load_prices(settings: Settings) -> Prices:
    """Carga los precios, buscando la ruta también desde la raíz del producto.

    :param settings: Configuración validada.
    :type settings: Settings
    :return: Tabla de precios.
    :rtype: Prices
    """
    path = settings.prices_path
    if not path.is_absolute() and not path.exists():
        path = PRODUCT_ROOT / path
    return load_prices(path)


def _build_backend(settings: Settings, directory: Directory, model, backend):
    """Elige el backend: el inyectado, el del modelo dado, el real o el simulado.

    :param settings: Configuración validada.
    :type settings: Settings
    :param directory: Directorio (aporta los departamentos al simulado).
    :type directory: Directory
    :param model: Modelo inyectado con ``complete(messages)``, o ``None``.
    :param backend: Backend inyectado, o ``None``.
    :return: Objeto con ``complete(model, messages)``.
    """
    if backend is not None:
        return backend
    if model is not None:
        return ModelBackend(model)
    if settings.model_provider == "gateway":
        return GatewayBackend(settings, httpx.Client(timeout=30.0))
    fail_model = settings.model_large if settings.fake_fail_large else None
    return FakeBackend(directory.departments(), fail_model)


def create_app(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=too-many-locals
    settings=None,
    model=None,
    directory=None,
    clock=None,
    logger=None,
    metrics=None,
    backend=None,
    limiter=None,
    sleep=time.sleep,
) -> FastAPI:
    """Crea la aplicación con sus dependencias.

    :param settings: Configuración; si falta se lee del entorno.
    :type settings: Settings or None
    :param model: Modelo con ``complete(messages)``; si falta se usa el backend.
    :param directory: Directorio; si falta se carga del archivo.
    :type directory: Directory or None
    :param clock: Reloj con ``now()`` y ``perf()``; por omisión el real.
    :param logger: Logger JSON; por omisión escribe en la salida estándar.
    :param metrics: Métricas; por omisión unas nuevas del proceso.
    :param backend: Backend con ``complete(model, messages)``; si falta se arma
        el simulado o el del gateway según ``MODEL_PROVIDER``.
    :param limiter: Limitador con ``check(client)``; por omisión uno nuevo que usa
        ``RATE_LIMIT_PER_MINUTE`` y el reloj inyectado.
    :param sleep: Función de espera del reintento ``sleep(segundos)``.
    :return: Aplicación FastAPI sin estado global entre instancias.
    :rtype: FastAPI
    """
    settings = settings or load_settings(os.environ)
    check_compliance(settings)
    directory = directory or _load_directory(settings)
    clock = clock or SystemClock()
    logger = logger or JsonLogger(settings.service_name, clock, sys.stdout)
    metrics = metrics or Metrics(settings.slo_p95_ms)
    tracer = build_tracer(settings, os.environ)
    prices = _load_prices(settings)
    # Un modelo o backend inyectado solo se usa para probar el agente de
    # directorio con respuestas preparadas (modo de las sesiones 1 a 4); el
    # clasificador y el revisor corren cuando el backend lo arma la aplicación.
    multiagent = model is None and backend is None
    backend = _build_backend(settings, directory, model, backend)
    limiter = limiter or RateLimiter(settings.rate_limit_per_minute, clock)
    application = FastAPI(title="HR Assistant")
    _install_middleware(application, clock, logger, metrics)

    async def require_client(request: Request) -> str:
        """Autentica con ``X-API-Key`` y aplica el límite del cliente.

        :param request: Petición en curso.
        :type request: Request
        :return: Nombre del cliente autenticado.
        :rtype: str
        :raises HTTPException: ``401`` sin clave válida o ``429`` al pasar el límite.
        """
        client = authenticate(request.headers.get(API_KEY_HEADER), settings.api_keys)
        if client is None:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        bind_client(client)
        request.state.client = client
        wait = limiter.check(client)
        if wait:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(wait)},
            )
        return client

    @application.get("/")
    def home():
        """Sirve la página web."""
        return FileResponse(INDEX_PAGE, media_type="text/html")

    @application.get("/health")
    def health():
        """Informa que el proceso está vivo."""
        return {"status": "ok", "pid": os.getpid()}

    @application.get("/metrics", dependencies=[Depends(require_client)])
    def metrics_view():
        """Informa las métricas de este proceso."""
        return {"pid": os.getpid(), **metrics.snapshot()}

    @application.post("/ask", dependencies=[Depends(require_client)])
    def ask(body: AskRequest):
        """Responde una pregunta con el historial que manda el cliente."""
        question = body.question
        if not question.strip() or len(question) > settings.max_question_chars:
            raise HTTPException(status_code=422, detail="Invalid question length")
        history = window_history(
            [item.model_dump() for item in body.history or []],
            settings.history_window,
        )
        resilient = ResilientBackend(
            backend,
            settings,
            sleep,
            on_fallback=lambda failed, kind: logger.emit(
                "model_fallback", model=failed, error_type=kind
            ),
        )
        orchestrator = Orchestrator(
            settings, directory, resilient, prices, tracer, logger, multiagent
        )
        try:
            result = orchestrator.run(question, history)
        except ModelUnavailable as error:
            logger.emit(
                "error",
                error_type=type(error).__name__,
                model=resilient.last_model,
                kind=error.kind,
            )
            return JSONResponse(
                status_code=502,
                content={
                    "detail": "model unavailable",
                    "request_id": current_request_id(),
                },
            )
        logger.emit(
            "agent_run",
            model=result["model"],
            route=result["route"],
            cost_usd=result["cost_usd"],
            question_chars=len(question),
            history_messages=len(history),
            steps=result["steps"],
            tools=result["tools_used"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            stopped=result["stopped"],
            intent=result["intent"],
            agents=result["agents_used"],
            pii_types=result["pii_detected"],
            fallback=result["fallback"],
            reviewer_invalid=result["reviewer_invalid"],
        )
        metrics.record_tokens(result["input_tokens"], result["output_tokens"])
        metrics.record_cost(result["cost_usd"])
        metrics.record_answer(
            intent=result["intent"],
            pii_masked=bool(result["pii_detected"]),
            injection_blocked=result["injection"] is not None,
            fallback=result["fallback"],
            client=current_client(),
            cost_usd=result["cost_usd"],
            model_calls=result["model_calls"],
            cached_calls=result["cached_calls"],
        )
        return {
            **{k: v for k, v in result.items() if k in RESPONSE_FIELDS},
            "request_id": current_request_id(),
        }

    return application


app = create_app()
