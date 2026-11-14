"""Id de petición: se obtiene o genera y se guarda en una ``ContextVar``."""

import re
import uuid
from contextvars import ContextVar, Token
from typing import Optional

_SAFE_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_REQUEST_ID: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_CLIENT: ContextVar[Optional[str]] = ContextVar("client", default=None)


def resolve_request_id(header_value: Optional[str]) -> str:
    """Usa el id del cliente si es seguro; si no, genera un UUID.

    :param header_value: Valor de ``X-Request-ID`` o ``None``.
    :type header_value: str or None
    :return: Id válido para el log y los encabezados.
    :rtype: str
    """
    if header_value and _SAFE_ID.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())


def bind_request_id(request_id: str) -> Token:
    """Guarda el id de la petición actual.

    :param request_id: Id a guardar.
    :type request_id: str
    :return: Token para restaurar el valor anterior.
    :rtype: Token
    """
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token) -> None:
    """Restaura el id anterior.

    :param token: Token devuelto por ``bind_request_id``.
    :type token: Token
    """
    _REQUEST_ID.reset(token)


def bind_client(client: str) -> Token:
    """Guarda el nombre del cliente autenticado (nunca su clave).

    :param client: Nombre del cliente.
    :type client: str
    :return: Token para restaurar el valor anterior.
    :rtype: Token
    """
    return _CLIENT.set(client)


def reset_client(token: Token) -> None:
    """Restaura el cliente anterior.

    :param token: Token devuelto por ``bind_client``.
    :type token: Token
    """
    _CLIENT.reset(token)


def current_client() -> Optional[str]:
    """Devuelve el cliente de la petición actual, si ya se autenticó.

    :return: Nombre del cliente o ``None``.
    :rtype: str or None
    """
    return _CLIENT.get()


def current_request_id() -> Optional[str]:
    """Devuelve el id de la petición actual, si hay una.

    :return: Id actual o ``None``.
    :rtype: str or None
    """
    return _REQUEST_ID.get()
