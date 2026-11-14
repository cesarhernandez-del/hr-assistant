"""Límite de peticiones por cliente con ventana deslizante."""

import math
import threading
from collections import deque
from typing import Deque, Dict

WINDOW_SECONDS = 60.0


class RateLimiter:
    """Permite hasta ``limit`` peticiones por cliente en 60 segundos.

    Usa solo el reloj inyectado (``now()``), así las pruebas controlan el tiempo.
    No usa ``perf()``, que el middleware reserva para medir la latencia.

    :param limit: Peticiones permitidas por ventana.
    :type limit: int
    :param clock: Reloj con ``now()`` que devuelve un ``datetime``.
    """

    def __init__(self, limit: int, clock):
        self._limit = limit
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str) -> int:
        """Registra una petición si cabe en la ventana.

        :param client: Nombre del cliente.
        :type client: str
        :return: ``0`` si pasa; si no, los segundos (al menos 1) que faltan.
        :rtype: int
        """
        with self._lock:
            now = self._clock.now().timestamp()
            hits = self._hits.setdefault(client, deque())
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if len(hits) < self._limit:
                hits.append(now)
                return 0
            return max(1, math.ceil(hits[0] + WINDOW_SECONDS - now))
