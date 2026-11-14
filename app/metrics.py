"""Métricas en memoria de este proceso."""

import math
import threading
from collections import deque
from typing import Deque, List

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
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0
        self._lock = threading.Lock()

    def record_request(self, latency_ms: float, failed: bool) -> None:
        """Registra una petición terminada.

        :param latency_ms: Latencia en milisegundos.
        :type latency_ms: float
        :param failed: Si terminó con error del servidor.
        :type failed: bool
        """
        with self._lock:
            self._requests += 1
            self._errors += 1 if failed else 0
            self._latencies.append(latency_ms)

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

        :return: ``requests``, ``error_rate``, ``latency_ms``, ``tokens`` y
            ``slo``.
        :rtype: dict
        """
        with self._lock:
            samples = sorted(self._latencies)
            requests = self._requests
            errors = self._errors
            tokens = {"input": self._input_tokens, "output": self._output_tokens}
            cost_usd = self._cost_usd
        p95 = _percentile(samples, 0.95)
        return {
            "requests": requests,
            "error_rate": errors / requests if requests else 0,
            "latency_ms": {"p50": _percentile(samples, 0.5), "p95": p95},
            "tokens": tokens,
            "cost_usd": cost_usd,
            "slo": {"p95_ms_target": self._slo_p95_ms, "met": p95 < self._slo_p95_ms},
        }
