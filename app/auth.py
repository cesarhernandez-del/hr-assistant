"""Claves de API por cliente: lectura de ``API_KEYS`` y autenticación."""

import hmac
from typing import Dict, Mapping, Optional

from app.errors import ConfigError


def _fail(position: int, entry: str, reason: str) -> ConfigError:
    """Arma el error de una entrada mal formada, sin mostrar su valor.

    :param position: Posición de la entrada, desde 1.
    :type position: int
    :param entry: Entrada completa; solo se usa su largo.
    :type entry: str
    :param reason: Qué falla de la entrada.
    :type reason: str
    :return: Error de configuración listo para lanzar.
    :rtype: ConfigError
    """
    return ConfigError(
        f"API_KEYS entry {position} is malformed: {reason} (length {len(entry)})"
    )


def parse_api_keys(raw: str) -> Dict[str, str]:
    """Convierte ``cliente:clave,cliente2:clave2`` en un diccionario.

    Los dos puntos extra pertenecen a la clave. Los mensajes de error dan la
    posición de la entrada y su largo, nunca la clave.

    :param raw: Valor de la variable ``API_KEYS``.
    :type raw: str
    :return: Diccionario cliente -> clave (vacío si ``raw`` está en blanco).
    :rtype: dict
    :raises ConfigError: Si una entrada no tiene cliente, clave o está repetida.
    """
    keys: Dict[str, str] = {}
    for position, part in enumerate(raw.split(","), start=1):
        entry = part.strip()
        if not entry:
            continue
        client, separator, key = entry.partition(":")
        client, key = client.strip(), key.strip()
        if not separator:
            raise _fail(position, entry, "expected client:key")
        if not client:
            raise _fail(position, entry, "empty client name")
        if not key:
            raise _fail(position, entry, f"empty key for client {client!r}")
        if client in keys:
            raise _fail(position, entry, f"repeated client {client!r}")
        keys[client] = key
    return keys


def authenticate(
    presented: Optional[str], keys: Mapping[str, str]
) -> Optional[str]:
    """Busca el cliente dueño de la clave, comparando en tiempo constante.

    :param presented: Valor del encabezado ``X-API-Key`` o ``None``.
    :type presented: str or None
    :param keys: Diccionario cliente -> clave.
    :type keys: Mapping[str, str]
    :return: Nombre del cliente, o ``None`` si la clave no es válida.
    :rtype: str or None
    """
    if not presented:
        return None
    candidate = presented.encode("utf-8")
    found = None
    for client, key in keys.items():
        if hmac.compare_digest(candidate, key.encode("utf-8")):
            found = client
    return found
