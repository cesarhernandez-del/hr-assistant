"""Pasos de los escenarios de observabilidad (pytest-bdd)."""

import uuid

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/observability.feature")


class ExplodingModel:
    """Modelo que falla con un mensaje que nunca debe llegar al log."""

    def complete(self, messages):
        """Siempre truena."""
        raise RuntimeError("secret boom")


@pytest.fixture(name="state")
def state_fixture():
    """Guarda la respuesta y las metricas entre pasos."""
    return {}


@given("an observed assistant", target_fixture="observed")
def given_observed_assistant(make_observed):
    """Aplicacion con reloj, logger y metricas inyectados."""
    return make_observed()


@given(
    "an assistant whose model fails with a secret message",
    target_fixture="observed",
)
def given_failing_assistant(make_observed):
    """Aplicacion cuyo modelo lanza una excepcion."""
    return make_observed(model=ExplodingModel())


@given(
    "an observed assistant where each request takes 3 seconds",
    target_fixture="observed",
)
def given_slow_assistant(make_observed):
    """Aplicacion con un reloj que mide 3 segundos por peticion."""
    return make_observed(step_seconds=3)


@when(parsers.parse('I call with request id "{request_id}" asking "{question}"'))
def send_with_request_id(observed, state, question, request_id):
    """Pregunta con un X-Request-ID elegido por el cliente."""
    state["response"] = observed.client.post(
        "/ask", json={"question": question},
        headers={"X-Request-ID": request_id},
    )


@when(parsers.parse('I send "{question}"'))
def send_question(observed, state, question):
    """Pregunta sin encabezado de id."""
    state["response"] = observed.client.post("/ask", json={"question": question})


@when("I read the metrics")
def read_metrics(observed, state):
    """Consulta GET /metrics."""
    state["metrics"] = observed.client.get("/metrics").json()


@then("the X-Request-ID header is a valid UUID")
def header_is_uuid(state):
    """El id generado tiene forma de UUID."""
    assert uuid.UUID(state["response"].headers["X-Request-ID"])


@then(parsers.parse('the X-Request-ID header is "{value}"'))
def header_is_value(state, value):
    """El encabezado conserva el id del cliente."""
    assert state["response"].headers["X-Request-ID"] == value


@then("the response body request_id equals the header")
def body_matches_header(state):
    """El cuerpo repite el id del encabezado."""
    response = state["response"]
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@then(parsers.parse('the response body request_id is "{value}"'))
def body_request_id_is(state, value):
    """El cuerpo trae el id del cliente."""
    assert state["response"].json()["request_id"] == value


@then(parsers.parse('every log line carries the request id "{value}"'))
def every_line_has_request_id(observed, value):
    """Todos los eventos del log llevan el mismo id."""
    events = observed.events()
    assert events
    assert all(event["request_id"] == value for event in events)


@then(parsers.parse("the log has a request event for POST /ask with status {code:d}"))
def log_has_request_event(observed, state, code):
    """Existe el evento request con metodo, ruta y estado."""
    events = observed.events("request")
    assert len(events) == 1
    assert events[0]["method"] == "POST"
    assert events[0]["path"] == "/ask"
    assert events[0]["status"] == code
    state["request_event"] = events[0]


@then(parsers.parse("that request event has a latency of {ms:d} ms"))
def request_event_latency(state, ms):
    """La latencia sale del reloj inyectado."""
    assert state["request_event"]["latency_ms"] == pytest.approx(ms)


@then(
    parsers.parse(
        'the log has an agent_run event with {steps:d} steps and stopped "{why}"'
    )
)
def log_has_agent_run(observed, steps, why):
    """El evento agent_run trae solo conteos, no texto."""
    events = observed.events("agent_run")
    assert len(events) == 1
    event = events[0]
    assert event["steps"] == steps
    assert event["stopped"] == why
    assert event["question_chars"] > 0
    assert event["history_messages"] == 0
    assert event["input_tokens"] > 0
    assert event["output_tokens"] > 0
    assert "get_employee" in str(event["tools"])


@then(parsers.parse('the log does not contain "{text}"'))
def log_lacks_text(observed, text):
    """El texto no aparece en ninguna linea del log."""
    assert text not in observed.stream.getvalue()


@then(
    parsers.parse(
        'the log has an audit event for tool "{tool}" with employee {employee}'
    )
)
def log_has_audit(observed, tool, employee):
    """El evento audit registra la herramienta y sus argumentos."""
    events = observed.events("audit")
    assert len(events) == 1
    assert events[0]["action"] == "tool_call"
    assert events[0]["tool"] == tool
    assert employee in str(events[0]["args"])


@then(parsers.parse("the response status is {code:d}"))
def response_status(state, code):
    """Codigo HTTP de la respuesta."""
    assert state["response"].status_code == code


@then(parsers.parse('the response detail is "{detail}"'))
def response_detail(state, detail):
    """Mensaje generico de la respuesta de error."""
    assert state["response"].json()["detail"] == detail


@then(parsers.parse('the log has an error event of type "{error_type}"'))
def log_has_error(observed, error_type):
    """El evento error nombra el tipo de excepcion."""
    events = observed.events("error")
    assert len(events) == 1
    assert error_type in events[0].values()


@then(
    parsers.parse(
        "the metrics show at least {count:d} requests and an error rate of {rate:d}"
    )
)
def metrics_counts(state, count, rate):
    """Conteo de peticiones y tasa de error."""
    assert state["metrics"]["requests"] >= count
    assert state["metrics"]["error_rate"] == rate


@then("the metrics show p50, p95, token counts and the pid")
def metrics_shape(state):
    """Forma completa del cuerpo de /metrics."""
    metrics = state["metrics"]
    assert set(metrics["latency_ms"]) == {"p50", "p95"}
    assert metrics["tokens"]["input"] > 0
    assert metrics["tokens"]["output"] > 0
    assert isinstance(metrics["pid"], int)
    assert metrics["slo"]["p95_ms_target"] == 2000


@then("the service level objective is met")
def slo_met(state):
    """El p95 esta por debajo de la meta."""
    assert state["metrics"]["slo"]["met"] is True


@then("the service level objective is not met")
def slo_not_met(state):
    """El p95 supera la meta."""
    assert state["metrics"]["slo"]["met"] is False
