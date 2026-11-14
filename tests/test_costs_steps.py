"""Pasos de los escenarios de costos (pytest-bdd)."""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import GATEWAY_ENV, GatewayStub, LARGE_MODEL, SMALL_MODEL

scenarios("features/costs.feature")


@pytest.fixture(name="state")
def state_fixture():
    """Guarda respuestas y asistentes entre pasos."""
    return {"responses": []}


@given("a costed assistant", target_fixture="observed")
def given_costed_assistant(make_costed):
    """Aplicacion con el modelo simulado y precios."""
    return make_costed()


@given(
    parsers.parse("a costed assistant with history window {size:d}"),
    target_fixture="observed",
)
def given_window_assistant(make_costed, size):
    """Aplicacion con una ventana de historial dada."""
    return make_costed({"HISTORY_WINDOW": str(size)})


@given(
    parsers.parse("a second costed assistant with history window {size:d}"),
    target_fixture="second",
)
def given_second_assistant(make_costed, size):
    """Segunda aplicacion para comparar ventanas."""
    return make_costed({"HISTORY_WINDOW": str(size)})


@given(
    parsers.parse('a gateway assistant whose cache status is "{status}"'),
    target_fixture="observed",
)
def given_cached_gateway(make_costed, status):
    """Aplicacion con un gateway falso que responde con ese estado de cache."""
    return make_costed(stub=GatewayStub(cache=status))


@given(
    parsers.parse("a gateway assistant that fails with status {code:d}"),
    target_fixture="observed",
)
def given_failing_gateway(make_costed, code):
    """Aplicacion con un gateway falso que falla."""
    return make_costed(stub=GatewayStub(status=code))


@when(parsers.parse('I ask "{question}"'))
def ask(observed, state, question):
    """Hace una pregunta sin historial."""
    state["responses"].append(
        observed.client.post("/ask", json={"question": question})
    )


@when(
    parsers.parse(
        'I ask "{question}" with a history of {count:d} messages on both'
    )
)
def ask_with_history(observed, second, state, question, count):
    """Hace la misma pregunta con el mismo historial en dos aplicaciones."""
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"mensaje {i}"}
        for i in range(count)
    ]
    body = {"question": question, "history": history}
    state["first"] = observed.client.post("/ask", json=body).json()
    state["second"] = second.client.post("/ask", json=body).json()


@then("the response model is the small model")
def model_is_small(state):
    """Se uso el modelo barato."""
    assert state["responses"][-1].json()["model"] == SMALL_MODEL


@then("the response model is the large model")
def model_is_large(state):
    """Se uso el modelo capaz."""
    assert state["responses"][-1].json()["model"] == LARGE_MODEL


@then("the response route is not empty")
def route_present(state):
    """La respuesta explica el motivo de la ruta."""
    assert state["responses"][-1].json()["route"]


@then(parsers.parse('the response route mentions "{word}"'))
def route_mentions(state, word):
    """El motivo nombra la palabra clave."""
    assert word in state["responses"][-1].json()["route"]


@then("the response cost is greater than zero")
def cost_positive(state):
    """La respuesta cuesta algo."""
    assert state["responses"][-1].json()["cost_usd"] > 0


@then("the response cost is zero")
def cost_zero(state):
    """La respuesta no cuesta nada."""
    assert state["responses"][-1].json()["cost_usd"] == 0


@then(parsers.parse("the response has at least {count:d} cached call"))
def has_cached_calls(state, count):
    """Hubo llamadas cacheadas."""
    assert state["responses"][-1].json()["cached_calls"] >= count


@then("the first assistant used fewer input tokens than the second")
def fewer_tokens(state):
    """La ventana corta manda menos tokens de entrada."""
    assert state["first"]["input_tokens"] < state["second"]["input_tokens"]


@then(parsers.parse("the response status is {code:d}"))
def status_is(state, code):
    """Codigo HTTP de la ultima respuesta."""
    assert state["responses"][-1].status_code == code


@then(parsers.parse('the response detail is "{detail}"'))
def detail_is(state, detail):
    """Mensaje de error de la ultima respuesta."""
    assert state["responses"][-1].json()["detail"] == detail


@then("the response has a request id")
def has_request_id(state):
    """El error trae el id de la peticion."""
    assert state["responses"][-1].json()["request_id"]


@then("neither the response nor the log contain the API token")
def token_not_leaked(observed, state):
    """El token no aparece ni en la respuesta ni en el log."""
    token = GATEWAY_ENV["CF_API_TOKEN"]
    assert token not in state["responses"][-1].text
    assert token not in observed.stream.getvalue()


@then("the metrics cost equals the sum of the answer costs")
def metrics_cost_matches(observed, state):
    """El costo acumulado es la suma de los costos de cada respuesta."""
    total = sum(r.json()["cost_usd"] for r in state["responses"])
    assert total > 0
    metrics = observed.client.get("/metrics").json()
    assert metrics["cost_usd"] == pytest.approx(total)
