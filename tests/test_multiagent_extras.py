"""Unit tests for spec 05: PII, guard, orchestrator, fake backend and config.

Interface expected from the product (the developer implements it):

- ``Settings.fake_reviewer_retry_once`` read from ``FAKE_REVIEWER_RETRY_ONCE``.
- ``FakeBackend(departments, fail_model=None, reviewer_retry_once=False)``.
- ``Orchestrator.run`` also returns ``review_retries`` and ``review_reason``.
- ``Metrics.snapshot()`` also returns ``ask_requests``.
"""

import io
import json

import pytest
from conftest import DEPARTMENTS, KEY_ENV, PRODUCT_ROOT, FakeClock

from app.classifier import CLASSIFIER_SYSTEM
from app.config import ConfigError, load_settings
from app.directory import Directory
from app.guard import check_injection
from app.llm import Completion, FakeBackend, FakeModel
from app.logging_json import JsonLogger
from app.metrics import Metrics
from app.orchestrator import (
    OUT_OF_SCOPE_ANSWER,
    UNVERIFIED_ANSWER,
    Orchestrator,
)
from app.pii import mask
from app.pricing import load_prices
from app.reviewer import REVIEWER_SYSTEM
from app.tracing import Tracer

PUBLIC_FIELDS = {"id", "name", "department", "role", "start_date", "status"}
QUESTION = "Quien es EMP-0001?"


class ScriptedBackend:
    """Backend with scripted classifier and reviewer replies."""

    def __init__(self, classifier, reviewer):
        self.classifier = classifier
        self.reviewer = list(reviewer)
        self.directory_calls = 0
        self.reviewer_calls = 0

    def complete(self, model, messages):
        """Answer as the agent named in the system message."""
        del model
        system = messages[0]["content"]
        if system == CLASSIFIER_SYSTEM:
            return Completion(self.classifier, 1, 1)
        if system == REVIEWER_SYSTEM:
            index = min(self.reviewer_calls, len(self.reviewer) - 1)
            self.reviewer_calls += 1
            return Completion(self.reviewer[index], 1, 1)
        self.directory_calls += 1
        return Completion(FakeModel(DEPARTMENTS).complete(messages), 1, 1)


@pytest.fixture(name="run_orchestrator")
def run_orchestrator_factory(directory, prices_file):
    """Return a function that runs a question against a scripted backend."""

    def run(backend, question=QUESTION):
        settings = load_settings({**KEY_ENV, "ROUTING": "false"})
        logger = JsonLogger(settings.service_name, FakeClock(), io.StringIO())
        orchestrator = Orchestrator(
            settings,
            directory,
            backend,
            load_prices(prices_file),
            Tracer(False, True, True),
            logger,
        )
        return orchestrator.run(question)

    return run


# PII


def test_company_rfc_with_three_letters_is_masked():
    text, types = mask("RFC de la empresa ABC800101AB1")
    assert text == "RFC de la empresa [RFC]"
    assert types == ["rfc"]


def test_employee_ids_and_short_numbers_are_not_personal_data():
    question = "Datos de EMP-0001 en el piso 123456789"
    assert mask(question) == (question, [])


def test_lowercase_curp_is_masked():
    text, types = mask("mi curp es gomc800101hdfrrs09")
    assert text == "mi curp es [CURP]"
    assert types == ["curp"]


def test_masking_twice_changes_nothing():
    once, _ = mask("a@x.com y 5512345678")
    assert mask(once) == (once, [])


# Guard


def test_similar_words_without_the_full_phrase_are_not_blocked():
    assert check_injection("Quien trabaja en el system de turnos?") is None
    assert check_injection("Dame el prompt de ventas de EMP-0002") is None


# Orchestrator


def test_directory_question_with_an_approving_reviewer_runs_three_agents(
    run_orchestrator,
):
    backend = ScriptedBackend('{"intent": "directory"}', ['{"verdict": "ok"}'])
    result = run_orchestrator(backend)
    assert result["agents_used"] == ["classifier", "directory", "reviewer"]
    assert result["review_retries"] == 0
    assert result["review_reason"] == ""


def test_garbage_classifier_reply_ends_as_out_of_scope_without_tools(
    run_orchestrator,
):
    backend = ScriptedBackend("I think it is about HR", ['{"verdict": "ok"}'])
    result = run_orchestrator(backend)
    assert result["intent"] == "out_of_scope"
    assert result["answer"] == OUT_OF_SCOPE_ANSWER
    assert result["tools_used"] == []
    assert backend.directory_calls == 0


def test_two_retry_verdicts_give_the_exact_unverified_message(run_orchestrator):
    retry = '{"verdict": "retry", "reason": "wrong"}'
    backend = ScriptedBackend('{"intent": "directory"}', [retry])
    result = run_orchestrator(backend)
    assert result["answer"] == UNVERIFIED_ANSWER
    assert result["agents_used"].count("directory") == 2
    assert backend.reviewer_calls == 2


def test_reviewer_reason_is_masked_and_cut_to_200_characters(run_orchestrator):
    reason = "Falta confirmar a ana@empresa.com " + "x" * 300
    first = json.dumps({"verdict": "retry", "reason": reason})
    backend = ScriptedBackend('{"intent": "directory"}', [first, '{"verdict": "ok"}'])
    result = run_orchestrator(backend)
    assert result["review_retries"] == 1
    assert "ana@empresa.com" not in result["review_reason"]
    assert result["review_reason"].startswith("Falta confirmar a [EMAIL]")
    assert len(result["review_reason"]) <= 200


def test_invalid_reviewer_reply_is_approved_and_flagged(run_orchestrator):
    backend = ScriptedBackend('{"intent": "directory"}', ["not json"])
    result = run_orchestrator(backend)
    assert result["reviewer_invalid"] is True
    assert result["review_retries"] == 0
    assert result["agents_used"].count("directory") == 1


# Fake backend


def test_fake_reviewer_retries_once_per_question():
    backend = FakeBackend(DEPARTMENTS, reviewer_retry_once=True)

    def verdict(question):
        content = json.dumps(
            {"question": question, "answer": "Ana", "tool_results": []}
        )
        messages = [
            {"role": "system", "content": REVIEWER_SYSTEM},
            {"role": "user", "content": content},
        ]
        return json.loads(backend.complete("any", messages).text)

    assert verdict("one") == {
        "verdict": "retry",
        "reason": "Falta el puesto del empleado.",
    }
    assert verdict("one") == {"verdict": "ok"}
    assert verdict("two")["verdict"] == "retry"


def test_fake_reviewer_approves_without_the_switch():
    backend = FakeBackend(DEPARTMENTS)
    content = json.dumps({"question": "q", "answer": "Ana", "tool_results": []})
    messages = [
        {"role": "system", "content": REVIEWER_SYSTEM},
        {"role": "user", "content": content},
    ]
    assert json.loads(backend.complete("any", messages).text) == {"verdict": "ok"}


# Configuration


def test_fake_switches_are_read_with_the_fake_provider():
    settings = load_settings(
        {**KEY_ENV, "FAKE_FAIL_LARGE": "true", "FAKE_REVIEWER_RETRY_ONCE": "true"}
    )
    assert settings.fake_fail_large is True
    assert settings.fake_reviewer_retry_once is True


def test_fake_switches_are_ignored_with_the_gateway_provider(gateway_settings):
    settings = gateway_settings(
        FAKE_FAIL_LARGE="true", FAKE_REVIEWER_RETRY_ONCE="true"
    )
    assert settings.fake_fail_large is False
    assert settings.fake_reviewer_retry_once is False


def test_reviewer_switch_must_be_true_or_false():
    with pytest.raises(ConfigError):
        load_settings({**KEY_ENV, "REVIEWER_ENABLED": "maybe"})


# Data and metrics


def test_shipped_employees_have_private_fields_that_tools_never_return():
    path = PRODUCT_ROOT / "data" / "employees.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert all("phone" in item and "rfc" in item for item in raw)
    directory = Directory.from_file(path)
    assert set(directory.get_employee("EMP-0001")) == PUBLIC_FIELDS


def test_metrics_with_no_questions_have_zero_percentiles_and_a_defined_slo():
    metrics = Metrics(2000)
    snapshot = metrics.snapshot()
    assert snapshot["ask_requests"] == 0
    assert snapshot["latency_ms"] == {"p50": 0, "p95": 0}
    assert isinstance(snapshot["slo"]["met"], bool)
