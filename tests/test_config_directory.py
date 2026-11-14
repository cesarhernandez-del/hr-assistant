"""Pruebas unitarias de la configuracion y del directorio de empleados."""

import pytest

from app.config import ConfigError, load_settings


def test_defaults_are_used_when_no_variables_are_set():
    settings = load_settings({})

    assert settings.model_provider == "fake"
    assert settings.agent_max_steps == 3
    assert settings.max_question_chars == 2000
    assert str(settings.employees_path) == "data/employees.json"


def test_invalid_values_prevent_startup_with_a_clear_message():
    invalid = [
        ({"AGENT_MAX_STEPS": "0"}, "AGENT_MAX_STEPS"),
        ({"AGENT_MAX_STEPS": "many"}, "AGENT_MAX_STEPS"),
        ({"MAX_QUESTION_CHARS": "-5"}, "MAX_QUESTION_CHARS"),
        ({"MODEL_PROVIDER": "unknown"}, "MODEL_PROVIDER"),
    ]
    for env, name in invalid:
        with pytest.raises(ConfigError, match=name):
            load_settings(env)


def test_employee_lookup_finds_existing_and_reports_missing(directory):
    found = directory.get_employee("EMP-0004")

    assert found["name"] == "Jorge Díaz"
    assert directory.get_employee("EMP-9999") is None


def test_department_search_ignores_case_and_unknown_is_empty(directory):
    names = [e["name"] for e in directory.search_by_department("tecnología")]

    assert names == ["Ana López", "Marta Ruiz", "Jorge Díaz"]
    assert directory.search_by_department("Marketing") == []
