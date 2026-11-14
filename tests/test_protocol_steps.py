"""Pasos de los escenarios del protocolo con el modelo real (pytest-bdd)."""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import GatewayStub

scenarios("features/protocol.feature")

ANSWER_JSON = '{"answer": "respuesta lista"}'
QUESTION = "¿Quién es EMP-0004?"


@pytest.fixture(name="state")
def state_fixture():
    """Guarda la ultima respuesta HTTP entre pasos."""
    return {}


def _assistant(make_costed, stub, env=None):
    """Arma la aplicacion con el gateway falso dado."""
    return {"observed": make_costed(env=env, stub=stub), "stub": stub}


@given(
    "a gateway assistant whose model replies with a fenced JSON answer",
    target_fixture="setup",
)
def given_fenced(make_costed):
    """El modelo envuelve el JSON en un bloque de codigo."""
    stub = GatewayStub(text=f"```json\n{ANSWER_JSON}\n```")
    return _assistant(make_costed, stub)


@given(
    "a gateway assistant whose model replies with text around the JSON",
    target_fixture="setup",
)
def given_surrounded(make_costed):
    """El modelo escribe texto antes y despues del JSON."""
    stub = GatewayStub(text=f"Claro, aqui va: {ANSWER_JSON} Espero que sirva.")
    return _assistant(make_costed, stub)


@given(
    "a gateway assistant whose model replies with plain text",
    target_fixture="setup",
)
def given_plain(make_costed):
    """El modelo responde sin ningun JSON."""
    return _assistant(make_costed, GatewayStub(text="No tengo idea."))


@given(
    parsers.parse("a gateway assistant with history window {size:d}"),
    target_fixture="setup",
)
def given_window(make_costed, size):
    """Gateway falso con una ventana de historial dada."""
    return _assistant(make_costed, GatewayStub(), {"HISTORY_WINDOW": str(size)})


@when(parsers.parse('I ask "{question}"'))
def ask(setup, state, question):
    """Hace una pregunta sin historial."""
    state["response"] = setup["observed"].client.post(
        "/ask", json={"question": question}
    )


@when(parsers.parse('I ask "{question}" with a history of {count:d} messages'))
def ask_with_history(setup, state, question, count):
    """Hace una pregunta con un historial de ``count`` mensajes."""
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"mensaje {i}"}
        for i in range(count)
    ]
    state["response"] = setup["observed"].client.post(
        "/ask", json={"question": question, "history": history}
    )


@then(parsers.parse("the response status is {code:d}"))
def status_is(state, code):
    """Codigo HTTP de la respuesta."""
    assert state["response"].status_code == code


@then(parsers.parse('the response answer is "{text}"'))
def answer_is(state, text):
    """Texto de la respuesta del agente."""
    assert state["response"].json()["answer"] == text


@then("the response answer says the model reply was not understood")
def answer_is_invalid(state):
    """El agente trato el texto sin JSON como respuesta invalida."""
    assert "No pude entender" in state["response"].json()["answer"]


@then(parsers.parse("the gateway received {count:d} messages"))
def gateway_message_count(setup, count):
    """Cantidad de mensajes del cuerpo enviado al gateway."""
    assert len(setup["stub"].sent_json()["messages"]) == count


@then("the first message sent to the gateway has the system role")
def first_is_system(setup):
    """El primer mensaje es el de sistema."""
    assert setup["stub"].sent_json()["messages"][0]["role"] == "system"


@then("the last message sent to the gateway is the question")
def last_is_question(setup):
    """El ultimo mensaje es la pregunta de la persona."""
    assert setup["stub"].sent_json()["messages"][-1] == {
        "role": "user",
        "content": QUESTION,
    }
