"""Unit tests for the directory whitelist, the classifier and new settings."""

import pytest
from conftest import KEY_ENV, ScriptedModel

from app.classifier import classify
from app.config import ConfigError, load_settings
from app.directory import Directory

PUBLIC_FIELDS = {"id", "name", "department", "role", "start_date", "status"}
EMPLOYEE_WITH_PRIVATE_DATA = {
    "id": "EMP-0009",
    "name": "Rosa Vega",
    "department": "Finanzas",
    "role": "Contadora",
    "start_date": "2020-01-01",
    "status": "activo",
    "phone": "5512345678",
    "rfc": "VERO800101AB1",
}


def test_directory_returns_only_public_fields():
    directory = Directory([EMPLOYEE_WITH_PRIVATE_DATA])
    one = directory.get_employee("EMP-0009")
    many = directory.search_by_department("Finanzas")
    assert set(one) == PUBLIC_FIELDS
    assert all(set(item) == PUBLIC_FIELDS for item in many)


@pytest.mark.parametrize(
    "reply_text",
    ["not json at all", '{"intent": "weather"}', "[]", ""],
)
def test_classifier_treats_invalid_replies_as_out_of_scope(reply_text):
    assert classify(ScriptedModel(reply_text), "hola") == "out_of_scope"


def test_classifier_accepts_a_valid_intent():
    model = ScriptedModel('{"intent": "directory"}')
    assert classify(model, "Quien es EMP-0001?") == "directory"


def test_new_settings_have_the_documented_defaults():
    settings = load_settings(KEY_ENV)
    assert settings.reviewer_enabled is True
    assert settings.model_timeout_seconds == 20
    assert settings.model_retry_backoff_seconds == 1


@pytest.mark.parametrize(
    "name,value",
    [("MODEL_TIMEOUT_SECONDS", "0"), ("MODEL_RETRY_BACKOFF_SECONDS", "-1")],
)
def test_invalid_timeout_or_backoff_is_rejected(name, value):
    with pytest.raises(ConfigError):
        load_settings({**KEY_ENV, name: value})
