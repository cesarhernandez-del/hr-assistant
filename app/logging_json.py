"""Log en JSON: una línea por evento."""

import json
import sys
import threading

from app.request_context import current_client, current_request_id


class JsonLogger:
    """Escribe eventos como líneas JSON.

    Nunca debe recibir el texto de preguntas ni de respuestas.

    :param service: Valor del campo ``service``.
    :type service: str
    :param clock: Reloj con ``now()``.
    :param stream: Destino con ``write`` y ``flush`` (por omisión stdout).
    """

    def __init__(self, service: str, clock, stream=None):
        self._service = service
        self._clock = clock
        self._stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()

    def emit(self, event: str, **fields) -> None:
        """Escribe una línea con ``ts``, ``service``, ``event`` y ``request_id``.

        :param event: Nombre del evento.
        :type event: str
        :param fields: Campos adicionales del evento.
        """
        record = {
            "ts": self._clock.now().isoformat(),
            "service": self._service,
            "event": event,
            "request_id": current_request_id(),
        }
        client = current_client()
        if client is not None:
            record["client"] = client
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()
