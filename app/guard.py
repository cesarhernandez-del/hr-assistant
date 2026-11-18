"""Filtro en código contra la inyección de prompts."""

import unicodedata
from typing import Optional

# Configuración del código, no del modelo: ampliarla es agregar una línea.
INJECTION_PHRASES = (
    "ignora las instrucciones",
    "ignora tus instrucciones",
    "olvida tus instrucciones",
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "prompt del sistema",
    "revela tu prompt",
    "developer mode",
    "jailbreak",
)


def normalize(text: str) -> str:
    """Pasa a minúsculas y quita los acentos.

    :param text: Texto original.
    :type text: str
    :return: Texto sin acentos y en minúsculas.
    :rtype: str
    """
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return plain.casefold()


def check_injection(question: str) -> Optional[str]:
    """Busca una frase de inyección en la pregunta.

    :param question: Pregunta ya enmascarada.
    :type question: str
    :return: La frase de la lista que coincidió, nunca la pregunta; ``None`` si
        no hubo coincidencia.
    :rtype: str or None
    """
    normalized = normalize(question)
    for phrase in INJECTION_PHRASES:
        if phrase in normalized:
            return phrase
    return None
