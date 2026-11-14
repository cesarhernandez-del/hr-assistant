"""Pruebas de precios, gateway, modelo por peticion y metricas de costo."""

import pytest
from conftest import DEPARTMENTS, GatewayStub, LARGE_MODEL, SMALL_MODEL

from app.gateway import SYSTEM_PROMPT, GatewayBackend
from app.llm import FakeBackend, ModelUnavailable, RequestModel
from app.metrics import Metrics
from app.pricing import PricingError, load_prices

MESSAGES = [{"role": "user", "content": "¿Quién es EMP-0004?"}]


def test_cost_uses_the_price_per_million_tokens(prices_file):
    prices = load_prices(prices_file)
    assert prices.cost(SMALL_MODEL, 1000, 500) == pytest.approx(0.000237)
    assert prices.cost(LARGE_MODEL, 1_000_000, 1_000_000) == pytest.approx(2.546)
    assert prices.cost("fake", 1000, 1000) == 0


def test_unknown_model_has_no_silent_zero_cost(prices_file):
    with pytest.raises(PricingError):
        load_prices(prices_file).cost("mystery-model", 10, 10)


def test_invalid_price_file_is_a_clear_error(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    with pytest.raises(PricingError):
        load_prices(broken)


def test_gateway_sends_url_token_and_exact_body(gateway_settings):
    stub = GatewayStub()
    settings = gateway_settings(MODEL_MAX_TOKENS="123")
    GatewayBackend(settings, stub.client()).complete(SMALL_MODEL, MESSAGES)
    request = stub.calls[0]
    assert str(request.url) == (
        "https://gateway.ai.cloudflare.com/v1/acct123/gw1"
        "/workers-ai/v1/chat/completions"
    )
    assert request.headers["authorization"] == "Bearer super-secret-token"
    assert stub.sent_json() == {
        "model": SMALL_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *MESSAGES],
        "max_tokens": 123,
        "temperature": 0,
    }


@pytest.mark.parametrize(
    "ttl, expected", [("60", "60"), ("0", None)], ids=["on", "off"]
)
def test_cache_ttl_header_is_sent_only_when_positive(gateway_settings, ttl, expected):
    stub = GatewayStub()
    settings = gateway_settings(CACHE_TTL_SECONDS=ttl)
    GatewayBackend(settings, stub.client()).complete(SMALL_MODEL, MESSAGES)
    assert stub.calls[0].headers.get("cf-aig-cache-ttl") == expected


@pytest.mark.parametrize(
    "status, cached", [("HIT", True), ("MISS", False)], ids=["hit", "miss"]
)
def test_gateway_reads_usage_and_cache_status(gateway_settings, status, cached):
    stub = GatewayStub(cache=status)
    backend = GatewayBackend(gateway_settings(), stub.client())
    completion = backend.complete(SMALL_MODEL, MESSAGES)
    assert completion.input_tokens == 1000
    assert completion.output_tokens == 500
    assert completion.cached is cached
    assert "ok" in completion.text


@pytest.mark.parametrize(
    "stub",
    [
        GatewayStub(status=500),
        GatewayStub(network_error=True),
        GatewayStub(usage=False),
    ],
    ids=["status-500", "network-error", "no-usage"],
)
def test_gateway_failures_become_model_unavailable(gateway_settings, stub):
    backend = GatewayBackend(gateway_settings(), stub.client())
    with pytest.raises(ModelUnavailable):
        backend.complete(SMALL_MODEL, MESSAGES)


def test_fake_backend_answers_the_same_for_any_model_name():
    backend = FakeBackend(DEPARTMENTS)
    small = backend.complete(SMALL_MODEL, MESSAGES)
    large = backend.complete(LARGE_MODEL, MESSAGES)
    assert small.text == large.text
    assert small.cached is False


def test_request_model_meters_each_request_on_its_own(prices_file):
    prices = load_prices(prices_file)
    first = RequestModel(FakeBackend(DEPARTMENTS), SMALL_MODEL, prices)
    first.complete(MESSAGES)
    first.complete(MESSAGES)
    expected = prices.cost(SMALL_MODEL, first.input_tokens, first.output_tokens)
    assert first.input_tokens > 0
    assert first.cost_usd == pytest.approx(expected)
    second = RequestModel(FakeBackend(DEPARTMENTS), SMALL_MODEL, prices)
    assert (second.input_tokens, second.cost_usd) == (0, 0)


def test_request_model_does_not_charge_cached_calls(prices_file, gateway_settings):
    backend = GatewayBackend(
        gateway_settings(), GatewayStub(cache="HIT").client()
    )
    model = RequestModel(backend, SMALL_MODEL, load_prices(prices_file))
    model.complete(MESSAGES)
    assert model.cached_calls == 1
    assert model.cost_usd == 0


def test_metrics_accumulate_cost_and_start_at_zero():
    metrics = Metrics(2000)
    assert metrics.snapshot()["cost_usd"] == 0
    metrics.record_cost(0.5)
    metrics.record_cost(0.25)
    assert metrics.snapshot()["cost_usd"] == pytest.approx(0.75)
