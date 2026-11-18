"""Agente clasificador: decide la intención de la pregunta."""

import json

INTENTS = ("directory", "out_of_scope", "sensitive")
DEFAULT_INTENT = "out_of_scope"

CLASSIFIER_SYSTEM = (
    "Eres un clasificador de preguntas de un asistente de recursos humanos. "
    "Respondes solo con un objeto JSON, sin texto adicional, con una de "
    'estas tres formas: {"intent": "directory"}, {"intent": "out_of_scope"} '
    'o {"intent": "sensitive"}.\n'
    "directory: preguntas sobre empleados o departamentos del directorio.\n"
    "sensitive: preguntas por salario, sueldo, teléfono, domicilio, RFC, "
    "CURP, cuenta bancaria o evaluación de desempeño.\n"
    "out_of_scope: cualquier otra cosa."
)


def classify(model, question: str) -> str:
    """Pide al modelo la intención y la valida con código.

    :param model: Modelo con ``complete(messages)`` que devuelve texto.
    :param question: Pregunta ya enmascarada.
    :type question: str
    :return: ``directory``, ``out_of_scope`` o ``sensitive``; cualquier otra
        respuesta del modelo se trata como ``out_of_scope``.
    :rtype: str
    """
    messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM},
        {"role": "user", "content": question},
    ]
    try:
        decoded = json.loads(model.complete(messages))
    except (json.JSONDecodeError, TypeError):
        return DEFAULT_INTENT
    if not isinstance(decoded, dict):
        return DEFAULT_INTENT
    intent = decoded.get("intent")
    if isinstance(intent, str) and intent in INTENTS:
        return intent
    return DEFAULT_INTENT
