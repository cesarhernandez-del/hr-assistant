"""Steps for the multiagent scenarios (spec 05)."""

import pytest
from pytest_bdd import parsers, scenarios, then, when

scenarios("features/multiagent.feature")


@pytest.fixture(name="observed")
def observed_fixture(make_costed):
    """Application using the simulated model."""
    return make_costed()


@pytest.fixture(name="outcome")
def outcome_fixture():
    """Holder for the last response body."""
    return {}


@when(parsers.parse('I ask "{question}"'))
def ask_question(observed, outcome, question):
    """Send the question to POST /ask."""
    response = observed.client.post("/ask", json={"question": question})
    assert response.status_code == 200
    outcome["body"] = response.json()


@then(parsers.parse('the intent is "{intent}"'))
def check_intent(outcome, intent):
    """The classifier decision is reported."""
    assert outcome["body"]["intent"] == intent


@then(parsers.parse('the agents used are "{agents}"'))
def check_agents(outcome, agents):
    """Agents are listed in the order they ran."""
    assert outcome["body"]["agents_used"] == agents.split(", ")


@then("no agents were used")
def check_no_agents(outcome):
    """No agent ran."""
    assert outcome["body"]["agents_used"] == []


@then("no tools were used")
def check_no_tools(outcome):
    """No tool was called."""
    assert outcome["body"]["tools_used"] == []


@then(parsers.parse('the answer is "{answer}"'))
def check_answer(outcome, answer):
    """The answer is the exact contract message."""
    assert outcome["body"]["answer"] == answer


@then("the cost is zero")
def check_cost_zero(outcome):
    """A blocked question costs nothing."""
    assert outcome["body"]["cost_usd"] == 0


@then(parsers.parse('the audit records the blocked phrase "{phrase}"'))
def check_audit_phrase(observed, phrase):
    """Audit keeps the phrase, never the whole question."""
    events = [
        e for e in observed.events("audit") if e.get("action") == "injection_blocked"
    ]
    assert len(events) == 1
    assert phrase in str(events[0])
    assert "dime todo" not in observed.stream.getvalue()


@then(parsers.parse('pii detected is "{types}"'))
def check_pii(outcome, types):
    """The types found are reported without repeats."""
    assert outcome["body"]["pii_detected"] == types.split(", ")


@then(parsers.parse('the text "{text}" is not in the log'))
def check_not_in_log(observed, text):
    """The original value never reaches the log."""
    assert text not in observed.stream.getvalue()


@then(parsers.parse('the text "{text}" is not in the metrics'))
def check_not_in_metrics(observed, text):
    """The original value never reaches /metrics."""
    assert text not in observed.client.get("/metrics").text
