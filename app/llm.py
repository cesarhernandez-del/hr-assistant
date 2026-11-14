"""Interfaz del modelo y modelo simulado determinista."""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Protocol

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
FALLBACK_ANSWER = "Pregúntame por un empleado (EMP-0001) o un departamento."
_EMPLOYEE_ID = re.compile(r"EMP-\d{4}")


class Model(Protocol):  # pylint: disable=too-few-public-methods
    """Interfaz que cumple cualquier modelo de lenguaje."""

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Devuelve un texto JSON con ``tool`` o ``answer``.

        :param messages: Conversación como lista de ``role`` y ``content``.
        :type messages: list
        :return: Objeto JSON serializado.
        :rtype: str
        """


class ModelUnavailable(Exception):
    """El modelo no respondió o su respuesta no se pudo usar."""


@dataclass(frozen=True)
class Completion:
    """Resultado de una llamada al modelo.

    :param text: Texto JSON devuelto por el modelo.
    :param input_tokens: Tokens de entrada de esta llamada.
    :param output_tokens: Tokens de salida de esta llamada.
    :param cached: Si el gateway respondió desde su caché.
    """

    text: str
    input_tokens: int
    output_tokens: int
    cached: bool = False


class ModelBackend:  # pylint: disable=too-few-public-methods
    """Adapta un modelo con ``complete(messages)`` a la interfaz de backend.

    Los tokens de cada llamada son la diferencia de sus contadores.

    :param model: Modelo con ``complete(messages)`` y contadores opcionales.
    """

    def __init__(self, model):
        self._model = model

    def complete(self, model: str, messages: List[Dict[str, str]]) -> Completion:
        """Llama al modelo adaptado; ``model`` solo sirve para el costo.

        :param model: Nombre del modelo elegido por el enrutador.
        :type model: str
        :param messages: Conversación completa.
        :type messages: list
        :return: Texto y tokens de esta llamada.
        :rtype: Completion
        """
        del model
        before_in = getattr(self._model, "input_tokens", 0)
        before_out = getattr(self._model, "output_tokens", 0)
        text = self._model.complete(messages)
        return Completion(
            text,
            getattr(self._model, "input_tokens", 0) - before_in,
            getattr(self._model, "output_tokens", 0) - before_out,
        )


class RequestModel:
    """Modelo de una sola petición: mide tokens, caché y costo.

    :param backend: Objeto con ``complete(model, messages)``.
    :param model: Nombre del modelo elegido (define el precio).
    :type model: str
    :param prices: Tabla de precios con ``cost(model, input, output)``.
    """

    def __init__(self, backend, model: str, prices):
        self._backend = backend
        self._model = model
        self._prices = prices
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_calls = 0
        self.cost_usd = 0.0

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Llama al backend y acumula tokens y costo (las cacheadas no cuestan).

        :param messages: Conversación completa.
        :type messages: list
        :return: Texto JSON del modelo.
        :rtype: str
        """
        result = self._backend.complete(self._model, messages)
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        if result.cached:
            self.cached_calls += 1
        else:
            self.cost_usd += self._prices.cost(
                self._model, result.input_tokens, result.output_tokens
            )
        return result.text


class FakeBackend:  # pylint: disable=too-few-public-methods
    """Backend simulado: responde igual con cualquier nombre de modelo.

    :param departments: Departamentos que el modelo simulado reconoce.
    :type departments: list
    """

    def __init__(self, departments: List[str]):
        self._departments = list(departments)

    def complete(self, model: str, messages: List[Dict[str, str]]) -> Completion:
        """Responde de forma determinista; el nombre solo define el precio.

        :param model: Nombre del modelo elegido por el enrutador.
        :type model: str
        :param messages: Conversación completa.
        :type messages: list
        :return: Texto y tokens aproximados de esta llamada.
        :rtype: Completion
        """
        del model
        return ModelBackend(FakeModel(self._departments)).complete("", messages)


class TracedModel:  # pylint: disable=too-few-public-methods
    """Envuelve un modelo para que cada llamada quede como traza.

    :param model: Modelo con ``complete(messages)``.
    :param tracer: Trazador con ``traceable(name, run_type)``.
    """

    def __init__(self, model, tracer):
        self._model = model
        self.complete = tracer.traceable(name="model_call", run_type="llm")(
            model.complete
        )

    @property
    def input_tokens(self) -> int:
        """Tokens de entrada acumulados del modelo envuelto."""
        return getattr(self._model, "input_tokens", 0)

    @property
    def output_tokens(self) -> int:
        """Tokens de salida acumulados del modelo envuelto."""
        return getattr(self._model, "output_tokens", 0)


class FakeModel:
    """Modelo simulado: decide con reglas sobre el último mensaje.

    :param departments: Departamentos que el modelo reconoce.
    :type departments: list
    """

    def __init__(self, departments: List[str]):
        self._departments = list(departments)
        self.input_tokens = 0
        self.output_tokens = 0

    def _decide(self, last: str) -> dict:
        """Aplica las reglas del modelo simulado.

        :param last: Contenido del último mensaje.
        :type last: str
        :return: Decisión con ``tool`` y ``args``, o ``answer``.
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            result = last[len(TOOL_RESULT_PREFIX):]
            return {"answer": f"Según el directorio: {result}"}
        found = _EMPLOYEE_ID.search(last)
        if found:
            return {"tool": "get_employee", "args": {"employee_id": found.group()}}
        lowered = last.casefold()
        for department in self._departments:
            if department.casefold() in lowered:
                return {
                    "tool": "search_by_department",
                    "args": {"department": department},
                }
        return {"answer": FALLBACK_ANSWER}

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Responde de forma determinista y cuenta tokens aproximados.

        :param messages: Conversación completa.
        :type messages: list
        :return: Objeto JSON serializado.
        :rtype: str
        """
        self.input_tokens += sum(len(m["content"].split()) for m in messages)
        decision = self._decide(messages[-1]["content"] if messages else "")
        reply_text = decision.get("answer") or json.dumps(
            decision, ensure_ascii=False
        )
        self.output_tokens += len(reply_text.split())
        return json.dumps(decision, ensure_ascii=False)
