"""Modelo real: Cloudflare Workers AI a través de AI Gateway."""

import json
from typing import Dict, List

import httpx

from app.config import Settings
from app.llm import Completion, ModelUnavailable

BASE_URL = "https://gateway.ai.cloudflare.com/v1"

SYSTEM_PROMPT = (
    "Eres un asistente de recursos humanos que responde preguntas sobre "
    "empleados. Respondes siempre en español y siempre con un solo objeto "
    "JSON, sin texto adicional.\n"
    "Tienes dos herramientas:\n"
    "- get_employee: busca un empleado por su identificador (employee_id).\n"
    "- search_by_department: lista los empleados de un departamento "
    "(department).\n"
    "Para usar una herramienta responde con "
    '{"tool": "get_employee", "args": {"employee_id": "EMP-XXXX"}} o con '
    '{"tool": "search_by_department", "args": {"department": "Ventas"}}.\n'
    "Después recibirás un mensaje que empieza con "
    '"Resultado de la herramienta: " seguido de los datos.\n'
    "Cuando tengas la información responde con "
    '{"answer": "tu respuesta para la persona"}.\n'
    "No inventes datos: usa solo lo que devuelvan las herramientas."
)


def extract_json(text: str) -> str:
    """Extrae el primer objeto JSON completo de un texto.

    :param text: Texto del modelo, quizá con cercas de código o prosa.
    :type text: str
    :return: El primer objeto JSON, o el texto sin cambios si no hay ninguno.
    :rtype: str
    """
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return text[start:end]
        start = text.find("{", start + 1)
    return text


class GatewayBackend:  # pylint: disable=too-few-public-methods
    """Llama al gateway con un cliente HTTP inyectado.

    :param settings: Configuración con cuenta, token, tope y caché.
    :type settings: Settings
    :param client: Cliente ``httpx.Client`` (en pruebas, con transporte falso).
    """

    def __init__(self, settings: Settings, client: httpx.Client):
        self._settings = settings
        self._client = client
        self._url = (
            f"{BASE_URL}/{settings.cf_account_id}/{settings.cf_gateway_id}"
            "/workers-ai/v1/chat/completions"
        )

    def complete(self, model: str, messages: List[Dict[str, str]]) -> Completion:
        """Pide una respuesta al modelo.

        :param model: Nombre del modelo de Workers AI.
        :type model: str
        :param messages: Conversación completa.
        :type messages: list
        :return: Texto, tokens y si vino de la caché.
        :rtype: Completion
        :raises ModelUnavailable: Si la llamada falla o la respuesta es inválida.
        """
        settings = self._settings
        headers = {"Authorization": f"Bearer {settings.cf_api_token}"}
        if settings.cache_ttl_seconds > 0:
            headers["cf-aig-cache-ttl"] = str(settings.cache_ttl_seconds)
        body = {
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            "max_tokens": settings.model_max_tokens,
            "temperature": settings.model_temperature,
        }
        try:
            response = self._client.post(self._url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
            return Completion(
                text=extract_json(str(data["choices"][0]["message"]["content"])),
                input_tokens=int(data["usage"]["prompt_tokens"]),
                output_tokens=int(data["usage"]["completion_tokens"]),
                cached=response.headers.get("cf-aig-cache-status", "").upper()
                == "HIT",
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as err:
            # No se incluye el mensaje original: podría traer la URL o el token.
            raise ModelUnavailable(type(err).__name__) from None
