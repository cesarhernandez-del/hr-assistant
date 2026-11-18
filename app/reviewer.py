"""Agente revisor: comprueba la respuesta contra los resultados de las herramientas."""

import json
from typing import List

REVIEWER_SYSTEM = (
    "Eres un revisor de respuestas de un asistente de recursos humanos. "
    "Recibes un objeto JSON con la pregunta, la respuesta y los resultados de "
    "las herramientas. Comprueba que la respuesta solo diga lo que esos "
    "resultados respaldan. Respondes solo con un objeto JSON, sin texto "
    'adicional: {"verdict": "ok"} o {"verdict": "retry", "reason": "..."}.'
)


def review(model, question: str, answer: str, tool_results: List[str]) -> dict:
    """Pide al modelo un veredicto y lo valida con código.

    :param model: Modelo con ``complete(messages)`` que devuelve texto.
    :param question: Pregunta ya enmascarada.
    :type question: str
    :param answer: Respuesta del agente de directorio, ya enmascarada.
    :type answer: str
    :param tool_results: Resultados de las herramientas de esa corrida.
    :type tool_results: list
    :return: ``verdict`` (``ok`` o ``retry``), ``reason`` e ``invalid``
        (``True`` si la respuesta del modelo no era válida y se trató como
        ``ok``).
    :rtype: dict
    """
    payload = {"question": question, "answer": answer, "tool_results": tool_results}
    messages = [
        {"role": "system", "content": REVIEWER_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        decoded = json.loads(model.complete(messages))
    except (json.JSONDecodeError, TypeError):
        decoded = None
    if isinstance(decoded, dict) and decoded.get("verdict") == "ok":
        return {"verdict": "ok", "reason": "", "invalid": False}
    if isinstance(decoded, dict) and decoded.get("verdict") == "retry":
        return {
            "verdict": "retry",
            "reason": str(decoded.get("reason", "")),
            "invalid": False,
        }
    return {"verdict": "ok", "reason": "", "invalid": True}
