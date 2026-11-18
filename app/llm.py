"""Interfaz del modelo y modelo simulado determinista."""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from app.classifier import CLASSIFIER_SYSTEM
from app.guard import normalize
from app.reviewer import REVIEWER_SYSTEM

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
FALLBACK_ANSWER = "Pregúntame por un empleado (EMP-0001) o un departamento."
_EMPLOYEE_ID = re.compile(r"EMP-\d{4}")
# Se comparan sin acentos ni mayúsculas. «cuenta» sola no basta: es un puesto.
_SENSITIVE_WORDS = (
    "salario",
    "sueldo",
    "telefono",
    "domicilio",
    "rfc",
    "curp",
    "cuenta bancaria",
    "desempeno",
)


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
    """El modelo no respondió o su respuesta no se pudo usar.

    :param message: Texto corto sin datos sensibles.
    :param kind: Tipo de falla: ``timeout``, ``network``, ``429``, ``5xx``,
        ``4xx`` o ``invalid``. Define si se reintenta.
    """

    def __init__(self, message: str = "", kind: str = "invalid"):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class Completion:
    """Resultado de una llamada al modelo.

    :param text: Texto JSON devuelto por el modelo.
    :param input_tokens: Tokens de entrada de esta llamada.
    :param output_tokens: Tokens de salida de esta llamada.
    :param cached: Si el gateway respondió desde su caché.
    :param model: Modelo que respondió de verdad (vacío si es el pedido).
    """

    text: str
    input_tokens: int
    output_tokens: int
    cached: bool = False
    model: str = ""


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


class RequestModel:  # pylint: disable=too-many-instance-attributes
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
        self.calls = 0
        self.cost_usd = 0.0

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Llama al backend y acumula tokens y costo (las cacheadas no cuestan).

        El costo usa el modelo que respondió, que puede ser el de respaldo.

        :param messages: Conversación completa.
        :type messages: list
        :return: Texto JSON del modelo.
        :rtype: str
        """
        result = self._backend.complete(self._model, messages)
        self.calls += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        if result.cached:
            self.cached_calls += 1
        else:
            self.cost_usd += self._prices.cost(
                result.model or self._model, result.input_tokens, result.output_tokens
            )
        return result.text


class FakeBackend:  # pylint: disable=too-few-public-methods
    """Backend simulado: responde igual con cualquier nombre de modelo.

    :param departments: Departamentos que el modelo simulado reconoce.
    :type departments: list
    :param fail_model: Nombre del modelo que siempre falla (para probar el
        respaldo sin red), o ``None``.
    :type fail_model: str or None
    """

    def __init__(self, departments: List[str], fail_model: Optional[str] = None):
        self._departments = list(departments)
        self._fail_model = fail_model

    def complete(self, model: str, messages: List[Dict[str, str]]) -> Completion:
        """Responde de forma determinista; el nombre solo define el precio.

        :param model: Nombre del modelo elegido por el enrutador.
        :type model: str
        :param messages: Conversación completa.
        :type messages: list
        :return: Texto y tokens aproximados de esta llamada.
        :rtype: Completion
        :raises ModelUnavailable: Si ``model`` es el que debe fallar.
        """
        if self._fail_model is not None and model == self._fail_model:
            raise ModelUnavailable("simulated failure", kind="5xx")
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

    def _classify(self, question: str) -> dict:
        """Clasifica la pregunta con las reglas del modelo simulado.

        :param question: Pregunta enmascarada.
        :type question: str
        :return: ``{"intent": ...}``.
        :rtype: dict
        """
        lowered = normalize(question)
        if any(word in lowered for word in _SENSITIVE_WORDS):
            return {"intent": "sensitive"}
        if _EMPLOYEE_ID.search(question):
            return {"intent": "directory"}
        if any(normalize(d) in lowered for d in self._departments):
            return {"intent": "directory"}
        return {"intent": "out_of_scope"}

    @staticmethod
    def _review(content: str) -> dict:
        """Revisa una respuesta: ``ok`` salvo que esté vacía.

        :param content: JSON con ``question``, ``answer`` y ``tool_results``.
        :type content: str
        :return: ``{"verdict": ...}``.
        :rtype: dict
        """
        try:
            answer = str(json.loads(content).get("answer", ""))
        except (json.JSONDecodeError, AttributeError):
            answer = ""
        if not answer.strip():
            return {"verdict": "retry", "reason": "empty answer"}
        return {"verdict": "ok"}

    def complete(self, messages: List[Dict[str, str]]) -> str:
        """Responde de forma determinista y cuenta tokens aproximados.

        Si el primer mensaje es el de sistema del clasificador o del revisor,
        responde como ellos; si no, como el agente de directorio.

        :param messages: Conversación completa.
        :type messages: list
        :return: Objeto JSON serializado.
        :rtype: str
        """
        self.input_tokens += sum(len(m["content"].split()) for m in messages)
        last = messages[-1]["content"] if messages else ""
        system = messages[0]["content"] if messages else ""
        if system == CLASSIFIER_SYSTEM:
            decision = self._classify(last)
        elif system == REVIEWER_SYSTEM:
            decision = self._review(last)
        else:
            decision = self._decide(last)
        reply_text = decision.get("answer") or json.dumps(
            decision, ensure_ascii=False
        )
        self.output_tokens += len(reply_text.split())
        return json.dumps(decision, ensure_ascii=False)
