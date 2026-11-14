"""Pasos de los escenarios de produccion segura (pytest-bdd).

Contrato de mensajes que estas pruebas esperan al no arrancar:

- ``API_KEYS`` mal formada: el mensaje dice ``entry N`` (posicion desde 1) y
  ``length L`` (largo de la entrada), nunca el valor.
- Compliance: el mensaje nombra la regla (``fake``, ``API_KEYS``, ``16``).
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from app.config import ConfigError, load_settings
from app.main import create_app

scenarios("features/production.feature")

KEYS = {
    "alice": "alice-key-0123456789abcdef",
    "bob": "bob-key-fedcba9876543210",
}


@pytest.fixture(name="state")
def state_fixture():
    """Guarda las respuestas y el resultado del arranque entre pasos."""
    return {"responses": []}


def _remember(state, response):
    """Guarda la respuesta como la ultima y en la lista completa."""
    state["response"] = response
    state["responses"].append(response)


def _ask(secured, state, question, key):
    """Pregunta con la clave dada (o sin encabezado si ``key`` es None)."""
    headers = {"X-API-Key": key} if key is not None else {}
    body = {"question": question}
    _remember(state, secured.client.post("/ask", json=body, headers=headers))


@given("a secured assistant", target_fixture="secured")
def given_secured(make_secured):
    """Aplicacion con los clientes alice y bob."""
    return make_secured()


@given(
    parsers.parse("a secured assistant with a limit of {limit:d} requests per minute"),
    target_fixture="secured",
)
def given_limited(make_secured, limit):
    """Aplicacion con un limite bajo y un reloj manual."""
    return make_secured(env={"RATE_LIMIT_PER_MINUTE": str(limit)})


@when(parsers.parse('I ask "{question}" without a key'))
def ask_without_key(secured, state, question):
    """Pregunta sin encabezado X-API-Key."""
    _ask(secured, state, question, None)


@when(parsers.parse('I ask "{question}" with the key "{key}"'))
def ask_with_key(secured, state, question, key):
    """Pregunta con una clave escrita en el escenario."""
    _ask(secured, state, question, key)


@when(parsers.parse('I ask "{question}" with the key "{key}" {count:d} times'))
def ask_with_key_many_times(secured, state, question, key, count):
    """Repite una pregunta con la misma clave."""
    for _ in range(count):
        _ask(secured, state, question, key)


@when(parsers.parse('"{client}" asks "{question}"'))
def client_asks(secured, state, client, question):
    """Pregunta con la clave del cliente indicado."""
    _ask(secured, state, question, KEYS[client])


@when(parsers.parse('"{client}" asks {count:d} times in a row'))
def client_asks_many_times(secured, state, client, count):
    """Pregunta varias veces seguidas con la clave del cliente."""
    for _ in range(count):
        _ask(secured, state, "Who is EMP-0004?", KEYS[client])


@when("I read the metrics without a key")
def metrics_without_key(secured, state):
    """GET /metrics sin clave."""
    _remember(state, secured.client.get("/metrics"))


@when(parsers.parse('I read the metrics as "{client}"'))
def metrics_with_key(secured, state, client):
    """GET /metrics con la clave del cliente."""
    response = secured.client.get("/metrics", headers={"X-API-Key": KEYS[client]})
    _remember(state, response)


@when("I open the root page, health and docs without a key")
def open_pages(secured, state):
    """GET de las tres rutas abiertas, sin clave."""
    state["open_codes"] = [
        secured.client.get(path).status_code for path in ("/", "/health", "/docs")
    ]


@when(parsers.parse("the clock advances {seconds:d} seconds"))
def advance_clock(secured, seconds):
    """Mueve el reloj inyectado."""
    secured.clock.advance(seconds)


@when(parsers.parse("I start the assistant with the environment {settings}"))
def start_assistant(directory, state, settings):
    """Arma la aplicacion con las variables dadas y guarda el error si hay."""
    env = dict(pair.split("=", 1) for pair in settings.split())
    state["error"] = None
    try:
        create_app(settings=load_settings(env), directory=directory)
    except ConfigError as error:
        state["error"] = str(error)


@then(parsers.parse("the response status is {code:d}"))
def response_status(state, code):
    """Codigo HTTP de la ultima respuesta."""
    assert state["response"].status_code == code


@then(parsers.parse('the response detail is "{detail}"'))
def response_detail(state, detail):
    """Mensaje exacto del error."""
    assert state["response"].json()["detail"] == detail


@then(parsers.parse("all three open pages answer {code:d}"))
def open_pages_answer(state, code):
    """Las rutas abiertas responden sin clave."""
    assert state["open_codes"] == [code, code, code]


@then(parsers.parse('the agent_run events belong to "{first}" and then "{second}"'))
def agent_runs_have_clients(secured, first, second):
    """Cada corrida del agente lleva el cliente que pregunto."""
    clients = [event["client"] for event in secured.events("agent_run")]
    assert clients == [first, second]


@then(parsers.parse('the audit event for employee {employee} belongs to "{client}"'))
def audit_has_client(secured, employee, client):
    """La auditoria de la herramienta lleva el cliente."""
    events = [e for e in secured.events("audit") if employee in str(e["args"])]
    assert len(events) == 1
    assert events[0]["client"] == client


@then(parsers.parse('the key of "{client}" is not in the log'))
def key_not_in_log(secured, client):
    """Ni la clave real ni la inventada aparecen en el log."""
    log = secured.stream.getvalue()
    assert log
    assert KEYS[client] not in log
    assert "alice-key-0123456789abcdeX" not in log


@then(parsers.parse('the key of "{client}" is not in any response'))
def key_not_in_responses(state, client):
    """Ningun cuerpo ni encabezado de respuesta trae la clave."""
    for response in state["responses"]:
        assert KEYS[client] not in response.text
        assert KEYS[client] not in str(dict(response.headers))


@then(parsers.parse("the Retry-After header is between {low:d} and {high:d}"))
def retry_after_in_range(state, low, high):
    """El encabezado Retry-After es un entero de segundos en el rango."""
    assert low <= int(state["response"].headers["Retry-After"]) <= high


@then(parsers.parse("the start is refused with a message about {reason}"))
def start_refused(state, reason):
    """El arranque falla con un ConfigError que nombra la regla."""
    assert state["error"] is not None
    assert reason.lower() in state["error"].lower()


@then(parsers.parse("the message gives the length {length:d}"))
def message_gives_length(state, length):
    """El mensaje trae el largo de la entrada que falla."""
    assert f"length {length}" in state["error"]


@then(parsers.parse('the message does not contain "{text}"'))
def message_lacks_text(state, text):
    """El valor secreto no aparece en el mensaje."""
    assert text not in state["error"]
