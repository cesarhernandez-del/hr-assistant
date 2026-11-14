"""Pasos de los escenarios de features/assistant.feature."""

import os

from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/assistant.feature")

HISTORY = [
    {"role": "user", "content": "¿Quién es EMP-0004?"},
    {"role": "assistant", "content": "Es Jorge Díaz, líder técnico."},
]


@given("an assistant with the sample employee directory",
       target_fixture="client")
def given_default_assistant(make_client):
    """Cliente con tope de pasos por omisión (3)."""
    return make_client()


@given(parsers.parse("an assistant limited to {steps:d} step"),
       target_fixture="client")
def given_limited_assistant(make_client, steps):
    """Cliente con el bucle limitado a ``steps`` vueltas."""
    return make_client(max_steps=steps)


@given("an assistant that records what the model receives",
       target_fixture="client")
def given_recording_assistant(make_client, recording_model):
    """Cliente cuyo modelo guarda los mensajes que recibe."""
    return make_client(model=recording_model)


@when(parsers.parse('I ask "{question}"'), target_fixture="response")
def when_ask(client, question):
    """Envia una pregunta sin historial."""
    return client.post("/ask", json={"question": question})


@when(parsers.parse('I continue a conversation asking "{question}"'),
      target_fixture="response")
def when_continue(client, recording_model, question):
    """Envia una pregunta con historial y recuerda cuantas llamadas hubo."""
    response = client.post(
        "/ask", json={"question": question, "history": HISTORY}
    )
    recording_model.first_request_calls = len(recording_model.calls)
    return response


@when(parsers.parse('I start over asking "{question}"'),
      target_fixture="response")
def when_start_over(client, question):
    """Envia otra peticion independiente, sin historial."""
    return client.post("/ask", json={"question": question})


@when(parsers.parse("I send a question of {length:d} characters"),
      target_fixture="response")
def when_send_sized_question(client, length):
    """Envia una pregunta de ``length`` caracteres."""
    return client.post("/ask", json={"question": "x" * length})


@when("I request the health endpoint", target_fixture="response")
def when_health(client):
    """Pide GET /health."""
    return client.get("/health")


@when("I request the home page", target_fixture="response")
def when_home(client):
    """Pide GET /."""
    return client.get("/")


@then(parsers.parse('the answer contains "{text}"'))
def then_answer_contains(response, text):
    """La respuesta incluye ``text``."""
    assert response.status_code == 200
    assert text in response.json()["answer"]


@then(parsers.parse('the answer does not contain "{text}"'))
def then_answer_lacks(response, text):
    """La respuesta no incluye ``text``."""
    assert text not in response.json()["answer"]


@then(parsers.parse('the answer is "{text}"'))
def then_answer_is(response, text):
    """La respuesta es exactamente ``text``."""
    assert response.json()["answer"] == text


@then("the answer says the employee does not exist")
def then_answer_not_found(response):
    """La respuesta dice que el empleado no existe."""
    assert "no existe" in response.json()["answer"].lower()


@then(parsers.parse('the tools used are "{tool}"'))
def then_tools_used(response, tool):
    """Se uso exactamente la herramienta ``tool`` una vez."""
    assert response.json()["tools_used"] == [tool]


@then("no tools are used")
def then_no_tools(response):
    """No se uso ninguna herramienta."""
    assert response.json()["tools_used"] == []


@then("token counts are reported")
def then_tokens(response):
    """La API informa tokens de entrada y salida."""
    body = response.json()
    assert body["input_tokens"] > 0
    assert body["output_tokens"] > 0


@then(parsers.parse("the API responds with status {status:d}"))
def then_status(response, status):
    """El codigo HTTP es ``status``."""
    assert response.status_code == status


@then('the health status is "ok" and the pid is the current process')
def then_health(response):
    """El estado es ok y el pid es el del proceso de las pruebas."""
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "pid": os.getpid()}


@then("the model received the previous conversation before the question")
def then_history_used(recording_model):
    """Los mensajes del historial llegan al modelo antes de la pregunta."""
    contents = [message["content"] for message in recording_model.calls[0]]
    assert contents[:2] == [item["content"] for item in HISTORY]
    assert contents[2] == "¿Y su departamento?"


@then("the model did not receive the previous conversation again")
def then_history_not_stored(recording_model, response):
    """La segunda peticion no arrastra el historial de la primera."""
    assert response.status_code == 200
    later = recording_model.calls[recording_model.first_request_calls:]
    assert later
    for call in later:
        texts = " ".join(message["content"] for message in call)
        assert "Jorge Díaz, líder técnico" not in texts
        assert "EMP-0004" not in texts


@then("the page contains the test ids \"question\", \"send\" and \"answer\"")
def then_page(response):
    """La pagina es HTML y trae los tres data-testid."""
    assert response.status_code == 200
    for test_id in ("question", "send", "answer"):
        assert f'data-testid="{test_id}"' in response.text
