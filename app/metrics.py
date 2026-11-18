"""Métricas en memoria de este proceso."""

import math
import threading
from collections import deque
from typing import Deque, Dict, List, Optional

WINDOW_SIZE = 1000


def _percentile(samples: List[float], fraction: float) -> float:
    """Calcula un percentil por el método del rango más cercano.

    :param samples: Muestras ordenadas de menor a mayor.
    :type samples: list
    :param fraction: Fracción entre 0 y 1 (0.95 para p95).
    :type fraction: float
    :return: El valor, o 0 si no hay muestras.
    :rtype: float
    """
    if not samples:
        return 0
    rank = max(1, math.ceil(fraction * len(samples)))
    return samples[rank - 1]


class Metrics:  # pylint: disable=too-many-instance-attributes
    """Contadores de peticiones, errores, latencias y tokens.

    :param slo_p95_ms: Meta de latencia p95 en milisegundos.
    :type slo_p95_ms: int
    """

    def __init__(self, slo_p95_ms: int):
        self._slo_p95_ms = slo_p95_ms
        self._latencies: Deque[float] = deque(maxlen=WINDOW_SIZE)
        self._requests = 0
        self._errors = 0
        self._ask_requests = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0
        self._intents = {"directory": 0, "out_of_scope": 0, "sensitive": 0}
        self._pii_masked = 0
        self._injections_blocked = 0
        self._fallbacks = 0
        self._model_calls = 0
        self._cached_calls = 0
        self._cost_by_client: Dict[str, float] = {}
        self._lock = threading.Lock()

    def record_answer(  # pylint: disable=too-many-arguments
        self,
        *,
        intent: str,
        pii_masked: bool,
        injection_blocked: bool,
        fallback: bool,
        client: Optional[str],
        cost_usd: float,
        model_calls: int,
        cached_calls: int,
    ) -> None:
        """Suma las métricas de negocio de una respuesta.

        :param intent: Intención decidida (``directory``, ``out_of_scope`` o
            ``sensitive``).
        :type intent: str
        :param pii_masked: Si se enmascaró algún dato personal.
        :type pii_masked: bool
        :param injection_blocked: Si el filtro bloqueó la pregunta.
        :type injection_blocked: bool
        :param fallback: Si se usó el modelo de respaldo.
        :type fallback: bool
        :param client: Nombre del cliente (nunca su clave), o ``None``.
        :type client: str or None
        :param cost_usd: Costo de la respuesta en USD.
        :type cost_usd: float
        :param model_calls: Llamadas al modelo de la respuesta.
        :type model_calls: int
        :param cached_calls: Llamadas que vinieron de la caché.
        :type cached_calls: int
        """
        with self._lock:
            self._intents[intent] = self._intents.get(intent, 0) + 1
            self._pii_masked += 1 if pii_masked else 0
            self._injections_blocked += 1 if injection_blocked else 0
            self._fallbacks += 1 if fallback else 0
            self._model_calls += model_calls
            self._cached_calls += cached_calls
            if client is not None:
                self._cost_by_client[client] = (
                    self._cost_by_client.get(client, 0.0) + cost_usd
                )

    def record_request(
        self, latency_ms: float, failed: bool, ask: bool = True
    ) -> None:
        """Registra una petición terminada.

        Todas cuentan para ``requests`` y ``error_rate``; solo las de
        ``POST /ask`` entran en la latencia y el SLO.

        :param latency_ms: Latencia en milisegundos.
        :type latency_ms: float
        :param failed: Si terminó con error del servidor.
        :type failed: bool
        :param ask: Si la petición fue ``POST /ask``.
        :type ask: bool
        """
        with self._lock:
            self._requests += 1
            self._errors += 1 if failed else 0
            if ask:
                self._latencies.append(latency_ms)
                self._ask_requests += 1

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Suma los tokens de una corrida del agente.

        :param input_tokens: Tokens de entrada.
        :type input_tokens: int
        :param output_tokens: Tokens de salida.
        :type output_tokens: int
        """
        with self._lock:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens

    def record_cost(self, usd: float) -> None:
        """Suma el costo de una respuesta.

        :param usd: Costo en USD.
        :type usd: float
        """
        with self._lock:
            self._cost_usd += usd

    def snapshot(self) -> dict:
        """Resume el estado actual.

        :return: ``requests``, ``ask_requests``, ``error_rate``, ``latency_ms``
            (solo ``POST /ask``), ``tokens`` y ``slo``.
        :rtype: dict
        """
        with self._lock:
            samples = sorted(self._latencies)
            requests = self._requests
            errors = self._errors
            ask_requests = self._ask_requests
            tokens = {"input": self._input_tokens, "output": self._output_tokens}
            cost_usd = self._cost_usd
            business = {
                "intents": dict(self._intents),
                "pii_masked": self._pii_masked,
                "injections_blocked": self._injections_blocked,
                "fallbacks": self._fallbacks,
                "cache_hit_rate": (
                    self._cached_calls / self._model_calls if self._model_calls else 0
                ),
                "cost_by_client": dict(self._cost_by_client),
            }
        p95 = _percentile(samples, 0.95)
        return {
            **business,
            "requests": requests,
            "ask_requests": ask_requests,
            "error_rate": errors / requests if requests else 0,
            "latency_ms": {"p50": _percentile(samples, 0.5), "p95": p95},
            "tokens": tokens,
            "cost_usd": cost_usd,
            "slo": {"p95_ms_target": self._slo_p95_ms, "met": p95 < self._slo_p95_ms},
        }
