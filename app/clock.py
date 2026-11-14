"""Reloj inyectable: único lugar que toca la hora real."""

import time
from datetime import datetime, timezone


class SystemClock:
    """Reloj real. Las pruebas lo sustituyen por uno fijo."""

    def now(self) -> datetime:
        """Devuelve la hora actual con zona UTC.

        :return: Fecha y hora en UTC.
        :rtype: datetime
        """
        return datetime.now(tz=timezone.utc)

    def perf(self) -> float:
        """Devuelve un contador monótono para medir latencias.

        :return: Segundos desde un punto arbitrario.
        :rtype: float
        """
        return time.perf_counter()
