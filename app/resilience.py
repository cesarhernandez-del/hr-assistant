"""Resiliencia ante fallas del modelo: reintento único y modelo de respaldo."""

import time
from dataclasses import replace
from typing import Callable, Dict, List, Optional

from app.config import Settings
from app.llm import Completion, ModelUnavailable

RETRYABLE_KINDS = ("timeout", "network", "429", "5xx")


class ResilientBackend:  # pylint: disable=too-few-public-methods
    """Envuelve un backend con un reintento y respaldo a ``MODEL_SMALL``.

    Se crea uno por petición: recuerda si ya cayó al respaldo, y desde
    entonces el resto de la petición usa ``MODEL_SMALL``.

    :param backend: Objeto con ``complete(model, messages)``.
    :param settings: Configuración con modelos y espera del reintento.
    :type settings: Settings
    :param sleep: Función de espera ``sleep(segundos)`` (inyectable en pruebas).
    :param on_fallback: Observador ``on_fallback(modelo_que_falló, tipo)``.
    """

    def __init__(
        self,
        backend,
        settings: Settings,
        sleep: Callable[[float], None] = time.sleep,
        on_fallback: Optional[Callable[[str, str], None]] = None,
    ):
        self._backend = backend
        self._settings = settings
        self._sleep = sleep
        self._on_fallback = on_fallback
        self.fallback_used = False
        self.last_model = ""

    def _try_twice(self, model: str, messages: List[Dict[str, str]]) -> Completion:
        """Llama al backend y, si la falla es transitoria, reintenta una vez.

        :param model: Modelo pedido.
        :type model: str
        :param messages: Conversación completa.
        :type messages: list
        :return: Resultado de la llamada.
        :rtype: Completion
        :raises ModelUnavailable: Si la falla no es transitoria o se repite.
        """
        try:
            return self._backend.complete(model, messages)
        except ModelUnavailable as error:
            if error.kind not in RETRYABLE_KINDS:
                raise
        self._sleep(self._settings.model_retry_backoff_seconds)
        return self._backend.complete(model, messages)

    def complete(self, model: str, messages: List[Dict[str, str]]) -> Completion:
        """Llama al modelo con reintento y respaldo.

        :param model: Modelo pedido (``MODEL_SMALL`` no tiene respaldo).
        :type model: str
        :param messages: Conversación completa.
        :type messages: list
        :return: Resultado, con el modelo que respondió de verdad.
        :rtype: Completion
        :raises ModelUnavailable: Si el modelo (y el respaldo) fallan.
        """
        small = self._settings.model_small
        if self.fallback_used:
            model = small
        self.last_model = model
        try:
            return replace(self._try_twice(model, messages), model=model)
        except ModelUnavailable as error:
            if model == small or error.kind not in RETRYABLE_KINDS:
                raise
            self.fallback_used = True
            self.last_model = small
            if self._on_fallback is not None:
                self._on_fallback(model, error.kind)
        return replace(self._backend.complete(small, messages), model=small)
