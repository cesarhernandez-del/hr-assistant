"""Orquestador: encadena filtro, enmascarado y los tres agentes de una pregunta."""

from typing import Dict, List, Optional

from app import pii
from app.agent import Agent
from app.classifier import classify
from app.config import Settings
from app.directory import Directory
from app.guard import check_injection
from app.llm import RequestModel, TracedModel
from app.reviewer import review
from app.router import choose_route

OUT_OF_SCOPE_ANSWER = (
    "Solo puedo responder preguntas sobre el directorio de empleados."
)
SENSITIVE_ANSWER = "Esa información no está disponible en este asistente."
UNVERIFIED_ANSWER = (
    "No pude verificar la respuesta. Intenta con una pregunta más concreta."
)
NO_DIRECTORY_ROUTE = "no_directory"
REASON_MAX_CHARS = 200


class Orchestrator:  # pylint: disable=too-many-instance-attributes
    """Reparte una pregunta entre clasificador, directorio y revisor.

    No conoce HTTP: recibe la pregunta y devuelve un diccionario. Se crea uno
    por petición porque su ``backend`` guarda el estado de resiliencia.

    :param settings: Configuración validada.
    :type settings: Settings
    :param directory: Directorio de empleados.
    :type directory: Directory
    :param backend: Objeto con ``complete(model, messages)``.
    :param prices: Tabla de precios con ``cost(model, input, output)``.
    :param tracer: Trazador con ``traceable(name, run_type)``.
    :param logger: Logger JSON con ``emit(event, **fields)``.
    :param multiagent: Si es ``False`` solo corre el agente de directorio
        (modo de las sesiones 1 a 4, para modelos inyectados en pruebas).
    :type multiagent: bool
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        settings: Settings,
        directory: Directory,
        backend,
        prices,
        tracer,
        logger,
        multiagent: bool = True,
    ):
        self._settings = settings
        self._directory = directory
        self._backend = backend
        self._prices = prices
        self._tracer = tracer
        self._logger = logger
        self._multiagent = multiagent
        self._models: List[RequestModel] = []

    def _request_model(self, name: str) -> RequestModel:
        """Crea un modelo medido para un agente y lo recuerda para sumar.

        :param name: Nombre del modelo de lenguaje.
        :type name: str
        :return: Modelo con sus propios contadores.
        :rtype: RequestModel
        """
        model = RequestModel(self._backend, name, self._prices)
        self._models.append(model)
        return model

    def _audit_pii(self, where: str, types: List[str]) -> None:
        """Registra que se enmascaró un dato: el tipo, nunca el valor.

        :param where: ``question`` o ``answer``.
        :type where: str
        :param types: Tipos de dato hallados.
        :type types: list
        """
        if types:
            self._logger.emit("audit", action="pii_masked", where=where, types=types)

    def _run_directory(self, model_name: str, question: str, history: list) -> dict:
        """Corre el agente de directorio una vez, como tramo ``directory``.

        :param model_name: Modelo elegido por el enrutador.
        :type model_name: str
        :param question: Pregunta enmascarada (quizá con el motivo del revisor).
        :type question: str
        :param history: Historial enmascarado.
        :type history: list
        :return: Resultado del agente.
        :rtype: dict
        """
        agent = Agent(
            TracedModel(self._request_model(model_name), self._tracer),
            self._directory,
            self._settings.agent_max_steps,
            on_tool=lambda name, args: self._logger.emit(
                "audit", action="tool_call", tool=name, args=args
            ),
            tracer=self._tracer,
        )
        return self._tracer.traceable(name="directory")(agent.run)(question, history)

    def _review(self, model, question: str, result: dict) -> dict:
        """Corre el revisor como tramo ``reviewer``.

        :param model: Modelo medido de ``MODEL_SMALL`` para el revisor.
        :param question: Pregunta enmascarada.
        :type question: str
        :param result: Resultado del agente de directorio.
        :type result: dict
        :return: Veredicto validado por ``review``.
        :rtype: dict
        """

        def run_review() -> dict:
            verdict = review(
                TracedModel(model, self._tracer),
                question,
                result["answer"],
                result["tool_results"],
            )
            verdict = {**verdict, "reason": _safe_reason(verdict["reason"])}
            # Excepción declarada a HIDE_OUTPUTS: el motivo ya va enmascarado.
            self._tracer.annotate(verdict=verdict["verdict"], reason=verdict["reason"])
            return verdict

        return self._tracer.traceable(name="reviewer")(run_review)()

    def _pipeline(  # pylint: disable=too-many-locals
        self, question: str, history: list
    ) -> dict:
        """Clasifica, corre el directorio y revisa; recibe todo enmascarado.

        :param question: Pregunta enmascarada y sin inyección.
        :type question: str
        :param history: Historial enmascarado.
        :type history: list
        :return: ``answer``, ``intent``, ``agents_used`` y los campos del
            agente de directorio.
        :rtype: dict
        """
        small = self._settings.model_small
        out = {
            "intent": "directory",
            "agents_used": [],
            "reviewer_invalid": False,
            "review_retries": 0,
            "review_reason": "",
        }
        if self._multiagent:
            classifier_model = TracedModel(self._request_model(small), self._tracer)
            out["intent"] = self._tracer.traceable(name="classifier")(classify)(
                classifier_model, question
            )
            out["agents_used"].append("classifier")
        if out["intent"] != "directory":
            answer = OUT_OF_SCOPE_ANSWER
            if out["intent"] == "sensitive":
                answer = SENSITIVE_ANSWER
            return {**_idle(small), **out, "answer": answer}
        model_name, route = choose_route(question, self._settings)
        reviewer_model = (
            self._request_model(small)
            if self._multiagent and self._settings.reviewer_enabled
            else None
        )
        tools: List[str] = []
        asked = question
        for attempt in range(2):
            result = self._run_directory(model_name, asked, history)
            out["agents_used"].append("directory")
            tools.extend(result["tools_used"])
            masked_answer, _ = pii.mask(result["answer"])
            result = {**result, "answer": masked_answer}
            if reviewer_model is None:
                break
            verdict = self._review(reviewer_model, question, result)
            out["agents_used"].append("reviewer")
            out["reviewer_invalid"] = out["reviewer_invalid"] or verdict["invalid"]
            if verdict["verdict"] == "ok":
                break
            out["review_reason"] = verdict["reason"]
            if attempt == 1:
                result = {**result, "answer": UNVERIFIED_ANSWER}
                break
            out["review_retries"] = 1
            asked = f"{question}\n\nMotivo de la revisión: {verdict['reason']}"
        extra = {"tools_used": tools, "model": model_name, "route": route}
        return {**result, **out, **extra}

    def run(self, question: str, history: Optional[List[Dict[str, str]]] = None):
        """Responde una pregunta con los tres agentes.

        :param question: Pregunta original de la persona.
        :type question: str
        :param history: Mensajes previos enviados por el cliente.
        :type history: list or None
        :return: ``answer``, ``intent``, ``agents_used``, ``pii_detected``,
            ``fallback``, ``review_retries``, ``review_reason``, ``cost_usd``,
            ``input_tokens``, ``output_tokens``, ``cached_calls``,
            ``model_calls``, ``injection``, ``steps``,
            ``tools_used``, ``model``, ``route`` y ``stopped``.
        :rtype: dict
        :raises ModelUnavailable: Si el modelo y su respaldo fallan.
        """
        masked_question, question_types = pii.mask(question)
        masked_history = []
        for item in history or []:
            text, _ = pii.mask(item["content"])
            masked_history.append({**item, "content": text})
        self._audit_pii("question", question_types)
        phrase = check_injection(masked_question)
        if phrase is not None:
            self._logger.emit("audit", action="injection_blocked", phrase=phrase)
            body = {
                **_idle(self._settings.model_small),
                "answer": SENSITIVE_ANSWER,
                "intent": "sensitive",
                "agents_used": [],
                "reviewer_invalid": False,
                "review_retries": 0,
                "review_reason": "",
            }
        else:
            body = self._tracer.traceable(name="agent_run")(self._pipeline)(
                masked_question, masked_history
            )
        answer, answer_types = pii.mask(body["answer"])
        self._audit_pii("answer", answer_types)
        models = self._models
        return {
            **body,
            "answer": answer,
            "pii_detected": sorted(set(question_types) | set(answer_types)),
            "injection": phrase,
            "fallback": bool(getattr(self._backend, "fallback_used", False)),
            "cost_usd": sum(m.cost_usd for m in models),
            "input_tokens": sum(m.input_tokens for m in models),
            "output_tokens": sum(m.output_tokens for m in models),
            "cached_calls": sum(m.cached_calls for m in models),
            "model_calls": sum(m.calls for m in models),
        }


def _safe_reason(reason: str) -> str:
    """Enmascara el motivo del revisor y lo recorta a 200 caracteres.

    :param reason: Motivo tal como lo dio el revisor.
    :type reason: str
    :return: Motivo sin datos personales y de a lo más 200 caracteres.
    :rtype: str
    """
    masked, _ = pii.mask(reason)
    return masked[:REASON_MAX_CHARS]


def _idle(model_name: str) -> dict:
    """Campos del agente de directorio cuando no corrió.

    :param model_name: Modelo que se informa (el pequeño).
    :type model_name: str
    :return: ``steps``, ``tools_used``, ``model``, ``route`` y ``stopped``.
    :rtype: dict
    """
    return {
        "steps": 0,
        "tools_used": [],
        "model": model_name,
        "route": NO_DIRECTORY_ROUTE,
        "stopped": "not_run",
    }
