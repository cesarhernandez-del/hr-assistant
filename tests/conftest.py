"""Fixtures compartidas de las pruebas del HR Assistant.

Interfaz que estas pruebas esperan del producto (el developer la implementa):

- ``app.config.load_settings(env)`` -> objeto con ``model_provider``,
  ``agent_max_steps``, ``max_question_chars`` y ``employees_path``.
  Lanza ``app.config.ConfigError`` si un valor es invalido.
- ``app.directory.Directory(employees)`` con ``get_employee(id)`` (dict o None)
  y ``search_by_department(name)`` (lista de dicts).
- ``app.llm.FakeModel(departments)`` con ``complete(messages)`` (devuelve un
  texto JSON) y los contadores acumulados ``input_tokens`` y ``output_tokens``.
- ``app.agent.Agent(model, directory, max_steps)`` con
  ``run(question, history=None)`` que devuelve un dict con ``answer``,
  ``steps``, ``tools_used``, ``input_tokens`` y ``output_tokens``.
- ``app.main.create_app(settings=None, model=None, directory=None)``.
"""

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

from app.config import load_settings  # noqa: E402  pylint: disable=C0413
from app.directory import Directory  # noqa: E402  pylint: disable=C0413
from app.llm import FakeModel  # noqa: E402  pylint: disable=C0413
from app.main import create_app  # noqa: E402  pylint: disable=C0413

TEST_KEY = "test-key-0123456789abcdef"
KEY_ENV = {"API_KEYS": f"tester:{TEST_KEY}"}
KEY_HEADERS = {"X-API-Key": TEST_KEY}

EMPLOYEES = [
    {"id": "EMP-0001", "name": "Ana López", "department": "Tecnología",
     "role": "Analista de datos", "start_date": "2019-03-04",
     "status": "activo"},
    {"id": "EMP-0002", "name": "Luis Pérez", "department": "Ventas",
     "role": "Ejecutivo de cuenta", "start_date": "2021-07-19",
     "status": "activo"},
    {"id": "EMP-0003", "name": "Marta Ruiz", "department": "Tecnología",
     "role": "Desarrolladora", "start_date": "2016-11-02", "status": "baja"},
    {"id": "EMP-0004", "name": "Jorge Díaz", "department": "Tecnología",
     "role": "Líder técnico", "start_date": "2022-01-10",
     "status": "activo"},
    {"id": "EMP-0005", "name": "Sofía Gómez", "department": "Finanzas",
     "role": "Contadora", "start_date": "2020-05-25", "status": "activo"},
]
DEPARTMENTS = ["Tecnología", "Ventas", "Finanzas"]


class ScriptedModel:
    """Modelo falso que responde con textos preparados y guarda lo recibido."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages):
        """Devuelve la siguiente respuesta; repite la ultima si se acaban."""
        self.calls.append([dict(message) for message in messages])
        index = min(len(self.calls), len(self.replies)) - 1
        return self.replies[index]


class RecordingModel:
    """Envuelve al modelo simulado y guarda cada lista de mensajes."""

    def __init__(self):
        self.inner = FakeModel(DEPARTMENTS)
        self.calls = []

    def complete(self, messages):
        """Guarda los mensajes y delega en el modelo simulado."""
        self.calls.append([dict(message) for message in messages])
        return self.inner.complete(messages)

    @property
    def input_tokens(self):
        """Tokens de entrada acumulados del modelo envuelto."""
        return self.inner.input_tokens

    @property
    def output_tokens(self):
        """Tokens de salida acumulados del modelo envuelto."""
        return self.inner.output_tokens


def reply(**payload):
    """Convierte un diccionario en el texto JSON que devolveria un modelo."""
    return json.dumps(payload, ensure_ascii=False)


class FakeClock:
    """Reloj de prueba: hora fija y un reloj de latencia que avanza solo.

    Interfaz de sesion 2 que se espera de ``app.clock``: ``now()`` devuelve un
    ``datetime`` con zona UTC y ``perf()`` devuelve segundos (float). El
    middleware llama a ``perf()`` una vez al empezar y otra al terminar cada
    peticion, asi que la latencia es ``step_seconds * 1000`` milisegundos.
    """

    def __init__(self, step_seconds=0.25):
        self.step_seconds = step_seconds
        self._ticks = 0

    def now(self):
        """Devuelve siempre la misma hora UTC."""
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    def perf(self):
        """Avanza el reloj de latencia un paso en cada llamada."""
        self._ticks += 1
        return self._ticks * self.step_seconds


class Observed:
    """Cliente HTTP junto con el log JSON que produjo la aplicacion."""

    def __init__(self, client, stream, clock=None):
        self.client = client
        self.stream = stream
        self.clock = clock

    def lines(self):
        """Lineas no vacias de la salida del log."""
        return [line for line in self.stream.getvalue().splitlines() if line]

    def events(self, name=None):
        """Eventos del log como diccionarios (cada linea debe ser JSON)."""
        parsed = [json.loads(line) for line in self.lines()]
        return [e for e in parsed if name is None or e["event"] == name]


def build_observed(settings, directory, clock, **app_kwargs):
    """Arma la app con logger y metricas inyectados y devuelve un ``Observed``.

    ``app_kwargs`` se pasa tal cual a ``create_app`` (``model``, ``backend``).
    """
    # pylint: disable=import-outside-toplevel
    from app.logging_json import JsonLogger
    from app.metrics import Metrics

    stream = io.StringIO()
    app = create_app(
        settings=settings,
        directory=directory,
        clock=clock,
        logger=JsonLogger(settings.service_name, clock, stream),
        metrics=Metrics(settings.slo_p95_ms),
        **app_kwargs,
    )
    client = TestClient(app, raise_server_exceptions=False, headers=KEY_HEADERS)
    return Observed(client, stream, clock)


@pytest.fixture(name="make_observed")
def make_observed_factory(directory):
    """Fabrica de aplicaciones con reloj, logger y metricas inyectados.

    Interfaz esperada: ``create_app(settings, model, directory, clock=None,
    logger=None, metrics=None)``, ``JsonLogger(service, clock, stream)`` y
    ``Metrics(slo_p95_ms)``.
    """

    def build(model=None, step_seconds=0.25, env=None):
        settings = load_settings({**KEY_ENV, **(env or {})})
        return build_observed(
            settings,
            directory,
            FakeClock(step_seconds),
            model=model or FakeModel(DEPARTMENTS),
        )

    return build


SMALL_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
PRICES = {
    "currency": "USD",
    "unit": "per million tokens",
    "models": {
        "fake": {"input": 0.0, "output": 0.0},
        SMALL_MODEL: {"input": 0.045, "output": 0.384},
        LARGE_MODEL: {"input": 0.293, "output": 2.253},
    },
}
GATEWAY_ENV = {
    "MODEL_PROVIDER": "gateway",
    "CF_ACCOUNT_ID": "acct123",
    "CF_GATEWAY_ID": "gw1",
    "CF_API_TOKEN": "super-secret-token",
}


class GatewayStub:
    """Falso AI Gateway: guarda cada peticion y responde lo que se le pida.

    Se usa como transporte de ``httpx.MockTransport``; no hay red.
    """

    def __init__(
        self, status=200, cache="MISS", usage=True, network_error=False, text=None
    ):
        self.text = text
        self.status = status
        self.cache = cache
        self.usage = usage
        self.network_error = network_error
        self.calls = []

    def __call__(self, request):
        """Atiende una peticion de httpx."""
        # pylint: disable=import-outside-toplevel
        import httpx

        self.calls.append(request)
        if self.network_error:
            raise httpx.ConnectError("network down", request=request)
        content = self.text if self.text is not None else json.dumps({"answer": "ok"})
        message = {"role": "assistant", "content": content}
        body = {"choices": [{"message": message}]}
        if self.usage:
            body["usage"] = {"prompt_tokens": 1000, "completion_tokens": 500}
        return httpx.Response(
            self.status, json=body, headers={"cf-aig-cache-status": self.cache}
        )

    def client(self):
        """Cliente httpx cuyo transporte es este falso gateway."""
        import httpx  # pylint: disable=import-outside-toplevel

        return httpx.Client(transport=httpx.MockTransport(self))

    def sent_json(self, index=0):
        """Cuerpo JSON de la peticion numero ``index``."""
        return json.loads(self.calls[index].content)


@pytest.fixture(name="prices_file")
def prices_file_fixture(tmp_path):
    """Archivo de precios con las cifras de ``spec/model_prices.json``."""
    path = tmp_path / "model_prices.json"
    path.write_text(json.dumps(PRICES), encoding="utf-8")
    return path


@pytest.fixture(name="gateway_settings")
def gateway_settings_factory(prices_file):
    """Fabrica de ``Settings`` con ``MODEL_PROVIDER=gateway``."""

    def build(**overrides):
        env = {**GATEWAY_ENV, "PRICES_PATH": str(prices_file), **overrides}
        return load_settings(env)

    return build


@pytest.fixture(name="make_costed")
def make_costed_factory(directory, prices_file):
    """Fabrica de aplicaciones con precios, log y, si se pide, gateway falso.

    Interfaz de sesion 3 que se espera del producto:

    - ``load_settings`` agrega ``cf_account_id``, ``cf_gateway_id``,
      ``cf_api_token``, ``model_small``, ``model_large``, ``routing``,
      ``router_max_chars``, ``history_window``, ``model_max_tokens``,
      ``model_temperature``, ``cache_ttl_seconds`` y ``prices_path``.
    - ``app.router.choose_route(question, settings)`` -> ``(model, reason)``
      y ``app.router.window_history(history, n)`` -> lista.
    - ``app.pricing.load_prices(path)`` -> objeto con
      ``cost(model, input_tokens, output_tokens)``; lanza
      ``app.pricing.PricingError`` si falta el modelo o el archivo es malo.
    - ``app.llm.Completion(text, input_tokens, output_tokens, cached)``,
      ``app.llm.ModelUnavailable``, ``app.llm.FakeBackend(departments)`` con
      ``complete(model, messages)`` y
      ``app.llm.RequestModel(backend, model, prices)`` con ``complete(messages)``
      (devuelve texto), ``input_tokens``, ``output_tokens``, ``cached_calls``
      y ``cost_usd``.
    - ``app.gateway.GatewayBackend(settings, client)`` con
      ``complete(model, messages)``; el tope, la temperatura y el TTL salen de
      ``settings``.
    - ``Metrics.record_cost(usd)`` y ``cost_usd`` en ``snapshot()``.
    - ``create_app(..., backend=None)``: con ``fake`` se arma el simulado; el
      costo usa ``settings.prices_path``.
    """

    def build(env=None, stub=None):
        # pylint: disable=import-outside-toplevel
        from app.gateway import GatewayBackend

        base = GATEWAY_ENV if stub else {}
        settings = load_settings(
            {**KEY_ENV, **base, "PRICES_PATH": str(prices_file), **(env or {})}
        )
        backend = GatewayBackend(settings, stub.client()) if stub else None
        return build_observed(settings, directory, FakeClock(), backend=backend)

    return build


KEY_ALICE = "alice-key-0123456789abcdef"
KEY_BOB = "bob-key-fedcba9876543210"
TWO_CLIENTS = f"alice:{KEY_ALICE},bob:{KEY_BOB}"


class ManualClock:
    """Reloj que solo avanza cuando la prueba lo pide.

    Ofrece ``now()`` (datetime UTC), ``perf()`` (segundos) y ``advance()``;
    los dos relojes avanzan juntos, asi que sirve para el limitador.
    """

    def __init__(self):
        self.seconds = 1000.0

    def now(self):
        """Hora UTC derivada de los segundos actuales."""
        return datetime.fromtimestamp(self.seconds, tz=timezone.utc)

    def perf(self):
        """Segundos actuales."""
        return self.seconds

    def advance(self, seconds):
        """Mueve el reloj hacia adelante."""
        self.seconds += seconds


@pytest.fixture(name="manual_clock")
def manual_clock_fixture():
    """Reloj manual para probar el limitador."""
    return ManualClock()


@pytest.fixture(name="make_secured")
def make_secured_factory(directory):
    """Fabrica de aplicaciones con dos clientes, limitador y reloj manual.

    Interfaz de sesion 4 que se espera del producto:

    - ``load_settings`` agrega ``environment``, ``api_keys`` (dict
      cliente -> clave, fuera del ``repr``) y ``rate_limit_per_minute``.
    - ``app.auth.parse_api_keys(raw)`` y ``authenticate(key, keys)``.
    - ``app.ratelimit.RateLimiter(limit, clock)`` con ``check(client)``.
    - ``app.config.check_compliance(settings)`` lanza ``ConfigError``.
    - ``app.request_context.bind_client(name)``, ``reset_client(token)`` y
      ``current_client()``.
    - ``create_app(..., limiter=None)``; se llama a ``check_compliance`` al
      armar la aplicacion.
    """

    def build(env=None, model=None):
        # pylint: disable=import-outside-toplevel
        from app.logging_json import JsonLogger
        from app.metrics import Metrics
        from app.ratelimit import RateLimiter

        merged = {"API_KEYS": TWO_CLIENTS, **(env or {})}
        settings = load_settings(merged)
        clock = ManualClock()
        stream = io.StringIO()
        app = create_app(
            settings=settings,
            model=model or FakeModel(DEPARTMENTS),
            directory=directory,
            clock=clock,
            logger=JsonLogger(settings.service_name, clock, stream),
            metrics=Metrics(settings.slo_p95_ms),
            limiter=RateLimiter(settings.rate_limit_per_minute, clock),
        )
        return Observed(
            TestClient(app, raise_server_exceptions=False), stream, clock
        )

    return build


@pytest.fixture(name="directory")
def directory_fixture():
    """Directorio con los cinco empleados de ejemplo."""
    return Directory(EMPLOYEES)


@pytest.fixture(name="scripted_model")
def scripted_model_factory():
    """Fabrica de modelos con respuestas preparadas."""
    return ScriptedModel


@pytest.fixture(name="recording_model")
def recording_model_fixture():
    """Modelo simulado que recuerda los mensajes que recibio."""
    return RecordingModel()


@pytest.fixture(name="make_client")
def make_client_factory(directory):
    """Fabrica de clientes HTTP con dependencias inyectadas."""

    def build(max_steps=3, model=None):
        settings = load_settings({**KEY_ENV, "AGENT_MAX_STEPS": str(max_steps)})
        app = create_app(
            settings=settings,
            model=model or FakeModel(DEPARTMENTS),
            directory=directory,
        )
        return TestClient(app, headers=KEY_HEADERS)

    return build
