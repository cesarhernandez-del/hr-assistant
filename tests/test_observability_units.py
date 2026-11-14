"""Pruebas unitarias de la logica de observabilidad (sesion 2).

Interfaz que se espera del producto:

- ``Settings``: ``service_name``, ``slo_p95_ms``, ``langsmith_tracing``,
  ``hide_inputs`` y ``hide_outputs``.
- ``app.clock.SystemClock``: ``now()`` (UTC con zona) y ``perf()`` (float).
- ``app.request_context.resolve_request_id(header_value)`` -> str.
- ``app.logging_json.JsonLogger(service, clock, stream).emit(event, **fields)``.
- ``app.metrics.Metrics(slo_p95_ms)``: ``record_request(latency_ms, failed)``,
  ``record_tokens(input_tokens, output_tokens)`` y ``snapshot()``.
- ``app.tracing.build_tracer(settings, env)``: objeto con ``enabled`` y
  ``traceable(name=...)`` (identidad si esta apagado).
- ``app.agent.Agent(model, directory, max_steps, on_tool=None)``: el resultado
  incluye ``stopped`` y ``on_tool(name, args)`` se llama por cada herramienta.
"""

import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from conftest import PRODUCT_ROOT, FakeClock

from app.agent import Agent
from app.clock import SystemClock
from app.config import ConfigError, load_settings
from app.logging_json import JsonLogger
from app.metrics import Metrics
from app.request_context import resolve_request_id
from app.tracing import build_tracer


def _json(**payload):
    """Convierte un diccionario en la respuesta JSON de un modelo."""
    return json.dumps(payload)


# --- config -----------------------------------------------------------------


def test_observability_settings_have_safe_defaults():
    settings = load_settings({})
    assert settings.service_name == "hr-assistant"
    assert settings.slo_p95_ms == 2000
    assert settings.langsmith_tracing is False
    assert settings.hide_inputs is True
    assert settings.hide_outputs is True


@pytest.mark.parametrize(
    "env",
    [{"HIDE_INPUTS": "maybe"}, {"LANGSMITH_TRACING": "si"}, {"SLO_P95_MS": "0"}],
)
def test_invalid_observability_values_are_rejected(env):
    with pytest.raises(ConfigError):
        load_settings(env)


# --- clock and request id -----------------------------------------------------


def test_system_clock_returns_utc_time():
    clock = SystemClock()
    assert clock.now().utcoffset() == timedelta(0)
    assert clock.perf() <= clock.perf()


def test_client_request_id_is_used_as_is():
    assert resolve_request_id("demo-123") == "demo-123"


@pytest.mark.parametrize("raw", [None, "", "bad\nid", "x" * 500])
def test_missing_or_unsafe_request_id_becomes_a_uuid(raw):
    assert uuid.UUID(resolve_request_id(raw))


# --- json log -----------------------------------------------------------------


def test_log_line_has_required_fields_and_utc_timestamp():
    stream = io.StringIO()
    logger = JsonLogger("hr-assistant", FakeClock(), stream)
    logger.emit("request", status=200)
    logger.emit("error", error_type="ValueError")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert {"ts", "service", "event", "request_id"} <= set(first)
    assert first["service"] == "hr-assistant"
    assert first["status"] == 200
    parsed = datetime.fromisoformat(first["ts"].replace("Z", "+00:00"))
    assert parsed == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


# --- metrics ------------------------------------------------------------------


def test_metrics_percentiles_from_known_latencies():
    metrics = Metrics(slo_p95_ms=2000)
    for latency in range(1, 101):
        metrics.record_request(latency_ms=float(latency), failed=False)
    snapshot = metrics.snapshot()
    assert snapshot["requests"] == 100
    assert snapshot["latency_ms"]["p50"] == pytest.approx(50, abs=1)
    assert snapshot["latency_ms"]["p95"] == pytest.approx(95, abs=1)


def test_metrics_without_data_do_not_divide_by_zero():
    snapshot = Metrics(slo_p95_ms=2000).snapshot()
    assert snapshot["requests"] == 0
    assert snapshot["error_rate"] == 0
    assert snapshot["latency_ms"] == {"p50": 0, "p95": 0}
    assert snapshot["tokens"] == {"input": 0, "output": 0}


def test_error_rate_and_tokens_are_accumulated():
    metrics = Metrics(slo_p95_ms=2000)
    for failed in (True, False, False, False):
        metrics.record_request(latency_ms=10.0, failed=failed)
    metrics.record_tokens(input_tokens=5, output_tokens=2)
    metrics.record_tokens(input_tokens=3, output_tokens=1)
    snapshot = metrics.snapshot()
    assert snapshot["error_rate"] == pytest.approx(0.25)
    assert snapshot["tokens"] == {"input": 8, "output": 3}


def test_slo_is_not_met_when_p95_equals_the_target():
    at_limit = Metrics(slo_p95_ms=2000)
    below = Metrics(slo_p95_ms=2000)
    for _ in range(10):
        at_limit.record_request(latency_ms=2000.0, failed=False)
        below.record_request(latency_ms=1999.0, failed=False)
    assert at_limit.snapshot()["slo"] == {"p95_ms_target": 2000, "met": False}
    assert below.snapshot()["slo"]["met"] is True


# --- tracing ------------------------------------------------------------------


def test_tracing_is_off_without_an_api_key():
    env = {"LANGSMITH_TRACING": "true"}
    tracer = build_tracer(load_settings(env), env)

    def sample():
        return "ok"

    assert tracer.enabled is False
    assert tracer.traceable(name="agent_run")(sample) is sample


def test_api_key_never_reaches_the_log(make_observed, monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-super-secret-key")
    observed = make_observed()
    observed.client.post("/ask", json={"question": "Who is EMP-0004?"})
    assert "ls-super-secret-key" not in observed.stream.getvalue()


# --- agent --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("replies", "max_steps", "expected"),
    [
        ([_json(answer="hola")], 3, "answer"),
        ([_json(tool="get_employee", args={"employee_id": "EMP-0001"})], 2,
         "max_steps"),
        (["this is not json"], 3, "invalid"),
    ],
    ids=["answer", "max_steps", "invalid"],
)
def test_agent_reports_why_it_stopped(
    scripted_model, directory, replies, max_steps, expected
):
    agent = Agent(scripted_model(*replies), directory, max_steps)
    assert agent.run("pregunta")["stopped"] == expected


def test_agent_notifies_every_tool_call(scripted_model, directory):
    calls = []
    model = scripted_model(
        _json(tool="get_employee", args={"employee_id": "EMP-0004"}),
        _json(tool="search_by_department", args={"department": "Ventas"}),
        _json(answer="listo"),
    )
    agent = Agent(model, directory, 5, on_tool=lambda n, a: calls.append((n, a)))
    result = agent.run("pregunta")
    assert calls == [
        ("get_employee", {"employee_id": "EMP-0004"}),
        ("search_by_department", {"department": "Ventas"}),
    ]
    assert result["tools_used"] == ["get_employee", "search_by_department"]


# --- web page -----------------------------------------------------------------


def test_page_shows_request_id_without_inner_html():
    page = (PRODUCT_ROOT / "app" / "static" / "index.html").read_text("utf-8")
    assert "request_id" in page
    assert "innerHTML" not in page
