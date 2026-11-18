"""Detección y enmascarado de datos personales (PII) con expresiones regulares."""

import re
from typing import List, Tuple

# El orden importa: un patrón no debe comerse a otro (la tarjeta antes que el
# teléfono, la CURP antes que el RFC).
_PATTERNS = (
    ("email", "[EMAIL]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    (
        "curp",
        "[CURP]",
        re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b", re.IGNORECASE),
    ),
    ("rfc", "[RFC]", re.compile(r"\b[A-Z]{3,4}\d{6}[A-Z0-9]{3}\b", re.IGNORECASE)),
    ("card", "[CARD]", re.compile(r"(?<![\w-])(?:\d[ -]?){12,15}\d(?!\d)")),
    (
        "phone",
        "[PHONE]",
        re.compile(
            r"(?<![\w-])(?:\+52[ -]?)?"
            r"(?:\d{10}|\d{2}[ -]?\d{4}[ -]?\d{4}|\d{3}[ -]?\d{3}[ -]?\d{4})(?!\d)"
        ),
    ),
)


def mask(text: str) -> Tuple[str, List[str]]:
    """Reemplaza los datos personales de un texto por marcadores.

    :param text: Texto de la pregunta o de la respuesta.
    :type text: str
    :return: El texto enmascarado y los tipos hallados (``email``, ``phone``,
        ``curp``, ``rfc``, ``card``), sin repetir y en orden alfabético.
    :rtype: tuple
    """
    found = set()
    for kind, marker, pattern in _PATTERNS:
        text, count = pattern.subn(marker, text)
        if count:
            found.add(kind)
    return text, sorted(found)
