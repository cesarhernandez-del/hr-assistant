"""Pruebas unitarias del modelo simulado y del agente."""

import json

from app.agent import Agent
from app.llm import FakeModel

TOOL_PREFIX = "Resultado de la herramienta: "
DEPARTMENTS = ["Tecnología", "Ventas", "Finanzas"]


def reply(**payload):
    """Texto JSON que devolveria un modelo."""
    return json.dumps(payload, ensure_ascii=False)


def ask_model(model, text):
    """Pregunta al modelo con un solo mensaje de usuario y decodifica el JSON."""
    return json.loads(model.complete([{"role": "user", "content": text}]))


def test_fake_model_summarizes_a_tool_result():
    model = FakeModel(DEPARTMENTS)

    decoded = ask_model(model, TOOL_PREFIX + "Jorge Díaz")

    assert decoded == {"answer": "Según el directorio: Jorge Díaz"}


def test_fake_model_requests_get_employee_for_an_id():
    decoded = ask_model(FakeModel(DEPARTMENTS), "Dime de EMP-0004 por favor")

    assert decoded == {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}


def test_fake_model_requests_search_for_a_known_department():
    decoded = ask_model(FakeModel(DEPARTMENTS), "Quien trabaja en Ventas")

    assert decoded["tool"] == "search_by_department"
    assert decoded["args"] == {"department": "Ventas"}


def test_fake_model_falls_back_and_counts_words_as_tokens():
    model = FakeModel(DEPARTMENTS)

    decoded = ask_model(model, "Hola")

    assert decoded == {
        "answer": "Pregúntame por un empleado (EMP-0001) o un departamento."
    }
    assert model.input_tokens == 1
    assert model.output_tokens == 8


def test_agent_feeds_the_tool_result_back_as_a_user_message(directory,
                                                            scripted_model):
    model = scripted_model(
        reply(tool="get_employee", args={"employee_id": "EMP-0004"}),
        reply(answer="Es Jorge Díaz"),
    )

    result = Agent(model, directory, max_steps=3).run("Quien es EMP-0004")

    last = model.calls[1][-1]
    assert last["role"] == "user"
    assert last["content"].startswith(TOOL_PREFIX)
    assert "Jorge Díaz" in last["content"]
    assert result["answer"] == "Es Jorge Díaz"
    assert result["steps"] == 2
    assert result["tools_used"] == ["get_employee"]


def test_agent_survives_invalid_json_from_the_model(directory, scripted_model):
    model = scripted_model("this is not json")

    result = Agent(model, directory, max_steps=3).run("Hola")

    assert isinstance(result["answer"], str) and result["answer"]
    assert not result["tools_used"]


def test_agent_does_not_run_an_unknown_tool(directory, scripted_model):
    model = scripted_model(reply(tool="delete_everything", args={}))

    result = Agent(model, directory, max_steps=2).run("Borra todo")

    assert isinstance(result["answer"], str) and result["answer"]
    assert "delete_everything" not in result["tools_used"]
    assert len(model.calls) <= 2
