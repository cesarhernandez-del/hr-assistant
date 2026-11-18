"""Steps for the reviewer, fallback and latency scenarios (spec 05)."""

import pytest
from conftest import KEY_ENV, FakeClock, build_observed
from pytest_bdd import given, parsers, scenarios, then, when

from app.config import load_settings

scenarios("features/multiagent_review.feature")

LONG_PAUSE_SECONDS = 3
SHORT_PAUSE_SECONDS = 0.001


class SwitchClock(FakeClock):
    """Clock whose step can change between requests."""

    def __init__(self):
        super().__init__(SHORT_PAUSE_SECONDS)
        self._seconds = 0.0

    def perf(self):
        """Advance by the current step on every call."""
        self._seconds += self.step_seconds
        return self._seconds


@pytest.fixture(name="env")
def env_fixture():
    """Environment of the app under test, without real waiting."""
    return {"MODEL_RETRY_BACKOFF_SECONDS": "0"}


@pytest.fixture(name="outcome")
def outcome_fixture():
    """Holder for the responses received."""
    return {"bodies": []}


@given(
    parsers.parse('the app runs with "{name}" set to "{value}"'),
    target_fixture="observed",
)
def app_with_setting(make_costed, env, name, value):
    """Build the app with one extra environment variable."""
    env[name] = value
    return make_costed(env=dict(env))


@given("the app measures time with a switchable clock", target_fixture="observed")
def app_with_switchable_clock(directory):
    """Build the app with a clock whose step is controlled by the test."""
    return build_observed(load_settings(KEY_ENV), directory, SwitchClock())


def _ask(observed, outcome, question):
    response = observed.client.post("/ask", json={"question": question})
    assert response.status_code == 200
    outcome["bodies"].append(response.json())


@when(parsers.parse('I ask "{question}" twice'))
def ask_twice(observed, outcome, question):
    """Send the same question two times."""
    _ask(observed, outcome, question)
    _ask(observed, outcome, question)


@when(parsers.parse('I ask "{question}"'))
def ask_question(observed, outcome, question):
    """Send the question to POST /ask."""
    _ask(observed, outcome, question)


@when("the load balancer calls health 20 times")
def call_health(observed):
    """Fast health checks, one millisecond each."""
    observed.clock.step_seconds = SHORT_PAUSE_SECONDS
    for _ in range(20):
        assert observed.client.get("/health").status_code == 200


@when(parsers.parse("I ask {count:d} slow questions"))
def ask_slow_questions(observed, outcome, count):
    """Questions that take three seconds each."""
    observed.clock.step_seconds = LONG_PAUSE_SECONDS
    for _ in range(count):
        _ask(observed, outcome, "Quien es EMP-0001?")


@then(parsers.parse("the review retries are {count:d}"))
def check_review_retries(outcome, count):
    """The response reports how many corrections were requested."""
    assert outcome["bodies"][-1]["review_retries"] == count


@then(parsers.parse("every response reports {count:d} review retries"))
def check_every_review_retries(outcome, count):
    """Each question repeats the same behavior."""
    assert [b["review_retries"] for b in outcome["bodies"]] == [count] * 2


@then(parsers.parse('the agents used are "{agents}"'))
def check_agents(outcome, agents):
    """Agents are listed in the order they really ran."""
    assert outcome["bodies"][-1]["agents_used"] == agents.split(", ")


@then(parsers.parse('the run log records the review reason "{reason}"'))
def check_review_reason(observed, reason):
    """The agent_run event keeps the reviewer reason."""
    run = observed.events("agent_run")[-1]
    assert run["review_reason"] == reason
    assert run["review_retries"] == (1 if reason else 0)


@then("the run log records no review reason")
def check_no_review_reason(observed):
    """An answer approved at the first try leaves an empty reason."""
    run = observed.events("agent_run")[-1]
    assert run["review_reason"] == ""
    assert run["review_retries"] == 0


@then(parsers.parse("the response fallback is {value}"))
def check_fallback(outcome, value):
    """The response says whether the backup model answered."""
    assert outcome["bodies"][-1]["fallback"] is (value == "true")


@then("the log has a model_fallback event")
def check_fallback_event(observed):
    """The failure of the large model is visible in the log."""
    assert len(observed.events("model_fallback")) >= 1


@then("the log has no model_fallback event")
def check_no_fallback_event(observed):
    """No failure, no event."""
    assert not observed.events("model_fallback")


@then(parsers.parse("the metrics count {asks:d} ask requests and {total:d} requests"))
def check_ask_requests(observed, asks, total):
    """Only POST /ask enters the latency count; requests count everything."""
    snapshot = observed.client.get("/metrics").json()
    assert snapshot["ask_requests"] == asks
    assert snapshot["requests"] >= total


@then(parsers.parse("the metrics p50 latency is at least {ms:d} milliseconds"))
def check_p50(observed, ms):
    """Health checks of one millisecond do not lower the percentile."""
    snapshot = observed.client.get("/metrics").json()
    assert snapshot["latency_ms"]["p50"] >= ms - 1


@then(parsers.parse('pii detected is "{types}"'))
def check_pii(outcome, types):
    """Types found, sorted and without repeats."""
    assert outcome["bodies"][-1]["pii_detected"] == types.split(", ")


@then(parsers.parse('the text "{text}" is not in the log'))
def check_not_in_log(observed, text):
    """The original value never reaches the log."""
    assert text not in observed.stream.getvalue()
