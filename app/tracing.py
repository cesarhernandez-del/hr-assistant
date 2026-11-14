"""Trazas opcionales en LangSmith."""

from typing import Callable, Mapping

from app.config import Settings
from app.request_context import current_client, current_request_id


def _hide(_payload):
    """Sustituye entradas o salidas por un diccionario vacío."""
    return {}


class Tracer:
    """Decorador de trazas que no hace nada si LangSmith está apagado.

    :param enabled: Si las trazas están encendidas.
    :type enabled: bool
    :param hide_inputs: Si no se mandan las entradas.
    :type hide_inputs: bool
    :param hide_outputs: Si no se mandan las salidas.
    :type hide_outputs: bool
    """

    def __init__(self, enabled: bool, hide_inputs: bool, hide_outputs: bool):
        self.enabled = enabled
        self._hide_inputs = hide_inputs
        self._hide_outputs = hide_outputs

    def traceable(self, name: str, run_type: str = "chain") -> Callable:
        """Devuelve un decorador que traza la función con ``request_id``.

        :param name: Nombre de la traza.
        :type name: str
        :param run_type: Tipo de corrida (``chain``, ``llm`` o ``tool``).
        :type run_type: str
        :return: Decorador; la identidad si las trazas están apagadas.
        :rtype: Callable
        """
        if not self.enabled:
            return lambda func: func
        # pylint: disable-next=import-outside-toplevel
        from langsmith import traceable

        options = {"name": name, "run_type": run_type}
        if self._hide_inputs:
            options["process_inputs"] = _hide
        if self._hide_outputs:
            options["process_outputs"] = _hide

        def decorator(func):
            traced = traceable(**options)(func)

            def wrapper(*args, **kwargs):
                metadata = {"request_id": current_request_id()}
                client = current_client()
                if client is not None:
                    metadata["client"] = client
                extra = {"metadata": metadata}
                return traced(*args, langsmith_extra=extra, **kwargs)

            return wrapper

        return decorator


def build_tracer(settings: Settings, env: Mapping[str, str]) -> Tracer:
    """Crea el trazador; solo se enciende con la bandera y la clave.

    La clave se lee del entorno y nunca se guarda ni se registra.

    :param settings: Configuración validada.
    :type settings: Settings
    :param env: Variables de entorno.
    :type env: Mapping[str, str]
    :return: Trazador, apagado si falta la bandera o la clave.
    :rtype: Tracer
    """
    enabled = settings.langsmith_tracing and bool(env.get("LANGSMITH_API_KEY"))
    return Tracer(enabled, settings.hide_inputs, settings.hide_outputs)
