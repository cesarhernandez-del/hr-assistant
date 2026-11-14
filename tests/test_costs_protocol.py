"""Pruebas del mensaje de sistema y de la extraccion de JSON del gateway."""

import json

import pytest
from conftest import EMPLOYEES, SMALL_MODEL, GatewayStub

from app.gateway import SYSTEM_PROMPT, GatewayBackend, extract_json
from app.llm import FakeBackend, RequestModel
from app.pricing import load_prices

MESSAGES = [{"role": "user", "content": "¿Quién es EMP-0004?"}]
ANSWER = '{"answer": "hola"}'


def test_system_message_goes_first_and_the_history_is_untouched(gateway_settings):
    stub = GatewayStub()
    backend = GatewayBackend(gateway_settings(), stub.client())
    backend.complete(SMALL_MODEL, MESSAGES)
    sent = stub.sent_json()["messages"]
    assert sent[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert sent[1:] == MESSAGES
    assert len(MESSAGES) == 1


def test_system_message_is_not_duplicated_between_calls(gateway_settings):
    stub = GatewayStub()
    backend = GatewayBackend(gateway_settings(), stub.client())
    backend.complete(SMALL_MODEL, MESSAGES)
    backend.complete(SMALL_MODEL, MESSAGES)
    for index in (0, 1):
        roles = [m["role"] for m in stub.sent_json(index)["messages"]]
        assert roles == ["system", "user"]


@pytest.mark.parametrize(
    "required",
    [
        "get_employee",
        "search_by_department",
        "employee_id",
        "department",
        '"tool"',
        '"args"',
        '"answer"',
        "Resultado de la herramienta: ",
        "JSON",
    ],
)
def test_system_prompt_teaches_the_protocol(required):
    assert required in SYSTEM_PROMPT


def test_system_prompt_is_in_spanish():
    lowered = SYSTEM_PROMPT.lower()
    assert "asistente" in lowered
    assert "empleados" in lowered
    assert "you are" not in lowered


def test_system_prompt_has_no_employee_data():
    for employee in EMPLOYEES:
        assert employee["name"] not in SYSTEM_PROMPT
        assert employee["id"] not in SYSTEM_PROMPT


def test_fake_backend_and_request_model_add_no_system_message(prices_file):
    seen = []

    class SpyBackend(FakeBackend):
        """Guarda los mensajes que recibe del modelo por peticion."""

        def complete(self, model, messages):
            seen.append(list(messages))
            return super().complete(model, messages)

    model = RequestModel(SpyBackend(["Ventas"]), SMALL_MODEL, load_prices(prices_file))
    model.complete(MESSAGES)
    assert seen == [MESSAGES]


@pytest.mark.parametrize(
    "text, expected",
    [
        (ANSWER, ANSWER),
        (f"```json\n{ANSWER}\n```", ANSWER),
        (f"```\n{ANSWER}\n```", ANSWER),
        (f"Claro. {ANSWER} Saludos.", ANSWER),
        ('{"answer": "usa { y } con cuidado"}', '{"answer": "usa { y } con cuidado"}'),
        ('{"answer": "dijo \\"}\\" ya"}', '{"answer": "dijo \\"}\\" ya"}'),
        (
            '{"tool": "get_employee", "args": {"employee_id": "EMP-0001"}}',
            '{"tool": "get_employee", "args": {"employee_id": "EMP-0001"}}',
        ),
        (f'{ANSWER} {{"answer": "otro"}}', ANSWER),
    ],
    ids=[
        "clean",
        "json-fence",
        "plain-fence",
        "text-around",
        "braces-in-string",
        "escaped-quote",
        "nested",
        "first-of-two",
    ],
)
def test_extract_json_returns_the_first_complete_object(text, expected):
    result = extract_json(text)
    assert result == expected
    assert isinstance(json.loads(result), dict)


@pytest.mark.parametrize(
    "text",
    ["No tengo idea.", '{"answer": "sin cerrar', ""],
    ids=["no-json", "incomplete", "empty"],
)
def test_extract_json_returns_the_text_unchanged_when_there_is_no_object(text):
    assert extract_json(text) == text


def test_gateway_completion_text_is_only_the_json_object(gateway_settings):
    stub = GatewayStub(text=f"Aqui esta:\n```json\n{ANSWER}\n```\nFin.")
    completion = GatewayBackend(gateway_settings(), stub.client()).complete(
        SMALL_MODEL, MESSAGES
    )
    assert completion.text == ANSWER
