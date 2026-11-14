"""Pruebas de la configuracion nueva, el enrutador y la ventana de historial."""

from pathlib import Path

import pytest
from conftest import GATEWAY_ENV, LARGE_MODEL, SMALL_MODEL

from app.config import ConfigError, load_settings
from app.router import choose_route, window_history


def test_cost_settings_have_the_documented_defaults():
    settings = load_settings({})
    assert settings.model_small == SMALL_MODEL
    assert settings.model_large == LARGE_MODEL
    assert settings.routing is True
    assert settings.router_max_chars == 80
    assert settings.history_window == 6
    assert settings.model_max_tokens == 300
    assert settings.model_temperature == 0
    assert settings.cache_ttl_seconds == 0
    assert settings.cf_gateway_id == "default"
    assert settings.prices_path == Path("data/model_prices.json")


@pytest.mark.parametrize(
    "missing", ["CF_ACCOUNT_ID", "CF_GATEWAY_ID", "CF_API_TOKEN"]
)
def test_gateway_without_a_cloudflare_variable_does_not_start(missing):
    env = {**GATEWAY_ENV, missing: ""}
    with pytest.raises(ConfigError):
        load_settings(env)


@pytest.mark.parametrize(
    "name, value",
    [
        ("ROUTING", "maybe"),
        ("HISTORY_WINDOW", "-1"),
        ("MODEL_MAX_TOKENS", "0"),
        ("MODEL_TEMPERATURE", "hot"),
    ],
)
def test_invalid_cost_values_are_rejected(name, value):
    with pytest.raises(ConfigError):
        load_settings({name: value})


def test_api_token_is_not_shown_in_settings_repr():
    settings = load_settings(GATEWAY_ENV)
    assert GATEWAY_ENV["CF_API_TOKEN"] not in repr(settings)


@pytest.mark.parametrize(
    "keyword", ["compara", "resume", "explica", "por qué", "analiza", "todos"]
)
def test_each_keyword_routes_to_the_large_model(keyword):
    settings = load_settings({})
    model, reason = choose_route(f"Por favor {keyword.upper()} esto", settings)
    assert model == LARGE_MODEL
    assert reason == f"keyword:{keyword}"


def test_router_limit_is_exactly_the_configured_length():
    settings = load_settings({})
    assert choose_route("a" * 80, settings) == (SMALL_MODEL, "simple")
    assert choose_route("a" * 81, settings) == (LARGE_MODEL, "too_long")


def test_routing_off_sends_every_question_to_the_large_model():
    settings = load_settings({"ROUTING": "false"})
    assert choose_route("¿Quién es EMP-0004?", settings) == (
        LARGE_MODEL,
        "routing_off",
    )


@pytest.mark.parametrize(
    "size, expected",
    [(10, [0, 1, 2, 3, 4]), (5, [0, 1, 2, 3, 4]), (2, [3, 4]), (0, [])],
    ids=["larger", "equal", "smaller", "zero"],
)
def test_window_keeps_only_the_last_messages(size, expected):
    history = [{"role": "user", "content": str(i)} for i in range(5)]
    kept = window_history(history, size)
    assert [int(message["content"]) for message in kept] == expected
    assert not window_history([], 3)
