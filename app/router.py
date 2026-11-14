"""Enrutamiento por regla y ventana de historial (palancas 1 y 2)."""

from typing import Dict, List, Tuple

from app.config import Settings

LARGE_KEYWORDS = ("compara", "resume", "explica", "por qué", "analiza", "todos")


def choose_route(question: str, settings: Settings) -> Tuple[str, str]:
    """Elige el modelo de una pregunta con una regla en código.

    :param question: Pregunta de la persona.
    :type question: str
    :param settings: Configuración con modelos y límite de largo.
    :type settings: Settings
    :return: Nombre del modelo y motivo (``routing_off``, ``too_long``,
        ``keyword:<palabra>`` o ``simple``).
    :rtype: tuple
    """
    if not settings.routing:
        return settings.model_large, "routing_off"
    if len(question) > settings.router_max_chars:
        return settings.model_large, "too_long"
    lowered = question.casefold()
    for keyword in LARGE_KEYWORDS:
        if keyword in lowered:
            return settings.model_large, f"keyword:{keyword}"
    return settings.model_small, "simple"


def window_history(
    history: List[Dict[str, str]], size: int
) -> List[Dict[str, str]]:
    """Deja solo los últimos ``size`` mensajes del historial.

    :param history: Mensajes previos.
    :type history: list
    :param size: Cuántos mensajes conservar (0 no conserva ninguno).
    :type size: int
    :return: Copia con los últimos mensajes.
    :rtype: list
    """
    if size <= 0:
        return []
    return list(history[-size:])
