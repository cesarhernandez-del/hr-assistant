"""Unit tests for resilience, reviewer, metrics and the fake backend rules."""

import json

import pytest
from conftest import DEPARTMENTS, KEY_ENV, ScriptedModel

from app.classifier import CLASSIFIER_SYSTEM
from app.config import load_settings
from app.llm import Completion, FakeBackend, ModelUnavailable
from app.metrics import Metrics
from app.resilience import ResilientBackend
from app.reviewer import REVIEWER_SYSTEM, review

SETTINGS = load_settings(KEY_ENV)
SMALL = SETTINGS.model_small
LARGE = SETTINGS.model_large


class FlakyBackend:
    """Backend that fails with the given kinds, then answers."""

    def __init__(self, *failures, always_fail=False):
        self.failures = list(failures)
        self.always_fail = always_fail
        self.calls = []

    def complete(self, model, messages):
        """Record the call and raise the next scripted failure, if any."""
        del messages
        self.calls.append(model)
        if self.always_fail or self.failures:
            kind = self.failures.pop(0) if self.failures else "5xx"
            raise ModelUnavailable("boom", kind=kind)
        return Completion(f"from {model}", 1, 1, model=model)


def build(backend, fallbacks=None):
    """Return a resilient backend and the list of recorded waits."""
    waits = []
    observer = None if fallbacks is None else (lambda m, k: fallbacks.append((m, k)))
    wrapped = ResilientBackend(
        backend, SETTINGS, sleep=waits.append, on_fallback=observer
    )
    return wrapped, waits


@pytest.mark.parametrize("kind", ["timeout", "network", "429", "5xx"])
def test_transient_failures_are_retried_once_after_the_backoff(kind):
    backend = FlakyBackend(kind)
    wrapped, waits = build(backend)
    result = wrapped.complete(LARGE, [])
    assert backend.calls == [LARGE, LARGE]
    assert waits == [SETTINGS.model_retry_backoff_seconds]
    assert result.text == f"from {LARGE}"
    assert wrapped.fallback_used is False


@pytest.mark.parametrize("kind", ["4xx", "invalid"])
def test_non_transient_failures_are_not_retried(kind):
    backend = FlakyBackend(kind)
    wrapped, waits = build(backend)
    with pytest.raises(ModelUnavailable):
        wrapped.complete(LARGE, [])
    assert backend.calls == [LARGE]
    assert not waits
    assert wrapped.fallback_used is False


def test_large_model_failing_twice_falls_back_to_the_small_model():
    backend = FlakyBackend("5xx", "timeout")
    fallbacks = []
    wrapped, _ = build(backend, fallbacks)
    result = wrapped.complete(LARGE, [])
    assert backend.calls == [LARGE, LARGE, SMALL]
    assert result.model == SMALL
    assert wrapped.fallback_used is True
    assert fallbacks == [(LARGE, "timeout")]


def test_after_a_fallback_the_rest_of_the_request_uses_the_small_model():
    backend = FlakyBackend("5xx", "5xx")
    wrapped, _ = build(backend)
    wrapped.complete(LARGE, [])
    backend.calls.clear()
    wrapped.complete(LARGE, [])
    assert backend.calls == [SMALL]


def test_small_model_failing_has_no_fallback():
    backend = FlakyBackend(always_fail=True)
    fallbacks = []
    wrapped, waits = build(backend, fallbacks)
    with pytest.raises(ModelUnavailable):
        wrapped.complete(SMALL, [])
    assert backend.calls == [SMALL, SMALL]
    assert len(waits) == 1
    assert not fallbacks
    assert wrapped.fallback_used is False


@pytest.mark.parametrize(
    "reply_text,verdict,reason,invalid",
    [
        ('{"verdict": "ok"}', "ok", "", False),
        ('{"verdict": "retry", "reason": "wrong id"}', "retry", "wrong id", False),
        ('{"verdict": "retry"}', "retry", "", False),
        ("not json", "ok", "", True),
        ('{"verdict": "maybe"}', "ok", "", True),
        ('Sure! {"verdict": "retry"}', "ok", "", True),
        ("[]", "ok", "", True),
    ],
)
def test_reviewer_validates_the_verdict_in_code(reply_text, verdict, reason, invalid):
    result = review(ScriptedModel(reply_text), "q", "a", ["tool"])
    assert result == {"verdict": verdict, "reason": reason, "invalid": invalid}


def test_reviewer_sends_question_answer_and_tool_results():
    model = ScriptedModel('{"verdict": "ok"}')
    review(model, "who?", "Ana", ["EMP-0001"])
    system, user = model.calls[0]
    assert system["content"] == REVIEWER_SYSTEM
    assert json.loads(user["content"]) == {
        "question": "who?",
        "answer": "Ana",
        "tool_results": ["EMP-0001"],
    }


def test_new_counters_start_at_zero_and_cache_hit_rate_with_no_calls_is_zero():
    snapshot = Metrics(1000).snapshot()
    assert snapshot["intents"] == {"directory": 0, "out_of_scope": 0, "sensitive": 0}
    assert snapshot["pii_masked"] == 0
    assert snapshot["injections_blocked"] == 0
    assert snapshot["fallbacks"] == 0
    assert snapshot["cache_hit_rate"] == 0
    assert snapshot["cost_by_client"] == {}


def record(metrics, **overrides):
    """Record one answer with sensible defaults."""
    values = {
        "intent": "directory",
        "pii_masked": False,
        "injection_blocked": False,
        "fallback": False,
        "client": "alice",
        "cost_usd": 0.5,
        "model_calls": 4,
        "cached_calls": 1,
    }
    metrics.record_answer(**{**values, **overrides})


def test_counters_cache_hit_rate_and_cost_by_client_add_up():
    metrics = Metrics(1000)
    record(metrics, pii_masked=True)
    record(metrics, intent="sensitive", injection_blocked=True, client="bob")
    record(metrics, intent="out_of_scope", fallback=True, cost_usd=0.25)
    snapshot = metrics.snapshot()
    assert snapshot["intents"] == {"directory": 1, "out_of_scope": 1, "sensitive": 1}
    assert snapshot["pii_masked"] == 1
    assert snapshot["injections_blocked"] == 1
    assert snapshot["fallbacks"] == 1
    assert snapshot["cache_hit_rate"] == 3 / 12
    assert snapshot["cost_by_client"] == {"alice": 0.75, "bob": 0.5}


def test_answers_without_a_client_add_no_cost_entry():
    metrics = Metrics(1000)
    record(metrics, client=None)
    assert metrics.snapshot()["cost_by_client"] == {}


def run_fake(system, content, backend=None):
    """Ask the fake backend as a given agent and decode its JSON reply."""
    backend = backend or FakeBackend(DEPARTMENTS)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]
    return json.loads(backend.complete(LARGE, messages).text)


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Quien es EMP-0001?", "directory"),
        ("Quien trabaja en Ventas?", "directory"),
        ("EMP-0002 es Ejecutivo de cuenta?", "directory"),
        ("Cual es el SALARIO de EMP-0001?", "sensitive"),
        ("Dame el teléfono de Ana", "sensitive"),
        ("Cuenta bancaria de Luis", "sensitive"),
        ("Cuentame un chiste", "out_of_scope"),
    ],
)
def test_fake_classifier_rules(question, intent):
    assert run_fake(CLASSIFIER_SYSTEM, question) == {"intent": intent}


@pytest.mark.parametrize(
    "answer,verdict",
    [("Ana trabaja en Tecnología", "ok"), ("", "retry"), ("   ", "retry")],
)
def test_fake_reviewer_asks_for_retry_only_on_empty_answers(answer, verdict):
    content = json.dumps({"question": "q", "answer": answer, "tool_results": []})
    assert run_fake(REVIEWER_SYSTEM, content)["verdict"] == verdict


def test_fake_backend_fails_only_for_the_configured_model():
    backend = FakeBackend(DEPARTMENTS, fail_model=LARGE)
    with pytest.raises(ModelUnavailable) as caught:
        backend.complete(LARGE, [{"role": "user", "content": "hola"}])
    assert caught.value.kind == "5xx"
    result = backend.complete(SMALL, [{"role": "user", "content": "hola"}])
    assert result.text
