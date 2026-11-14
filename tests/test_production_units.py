"""Pruebas unitarias de la sesion 4: claves, limite, compliance y publicacion."""

import importlib.util
import re
import sys
import types
from pathlib import Path

import httpx
import pytest

from app.auth import authenticate, parse_api_keys
from app.config import ConfigError, check_compliance, load_settings
from app.ratelimit import RateLimiter
from app.request_context import bind_client, reset_client

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PRODUCT_ROOT / "app" / "static" / "index.html"
GATEWAY = {
    "MODEL_PROVIDER": "gateway",
    "CF_ACCOUNT_ID": "acct",
    "CF_API_TOKEN": "token",
}
KEY_16 = "k" * 16


def compliance_message(env):
    """Devuelve el mensaje de rechazo (en minusculas) o ``""`` si pasa."""
    try:
        check_compliance(load_settings(env))
    except ConfigError as error:
        return str(error)
    return ""


# --- auth ---------------------------------------------------------------


def test_api_keys_are_parsed_per_client_even_with_colons_and_spaces():
    keys = parse_api_keys(" alice:key-one , bob:ke:y-two ")

    assert keys == {"alice": "key-one", "bob": "ke:y-two"}
    empty = parse_api_keys("")
    assert isinstance(empty, dict)
    assert not empty


def test_a_malformed_api_keys_error_never_shows_the_value():
    raw = "alice:good-key-123,secretvaluewithoutcolon"

    with pytest.raises(ConfigError) as caught:
        parse_api_keys(raw)

    message = str(caught.value)
    assert "entry 2" in message
    assert "length 23" in message
    assert "secretvaluewithoutcolon" not in message
    for bad in (":only-a-key", "client:", "a:one,a:two"):
        with pytest.raises(ConfigError):
            parse_api_keys(bad)


def test_authenticate_returns_the_client_only_for_the_exact_key():
    keys = {"alice": "key-one", "bob": "key-two"}

    assert authenticate("key-two", keys) == "bob"
    assert authenticate("key-twp", keys) is None
    assert authenticate(None, keys) is None
    assert authenticate("", keys) is None
    assert authenticate("key-one", {}) is None


# --- rate limit ---------------------------------------------------------


def test_the_request_after_the_limit_waits_the_seconds_that_remain(manual_clock):
    limiter = RateLimiter(2, manual_clock)

    assert limiter.check("alice") == 0
    assert limiter.check("alice") == 0
    assert limiter.check("alice") == 60
    manual_clock.advance(20)
    assert limiter.check("alice") == 40
    manual_clock.advance(39.5)
    assert limiter.check("alice") == 1
    manual_clock.advance(0.5)
    assert limiter.check("alice") == 0


def test_the_window_slides_and_clients_do_not_share_it(manual_clock):
    limiter = RateLimiter(2, manual_clock)
    limiter.check("alice")
    manual_clock.advance(30)
    limiter.check("alice")
    manual_clock.advance(1)

    assert limiter.check("alice") == 29
    assert limiter.check("bob") == 0
    manual_clock.advance(29)
    assert limiter.check("alice") == 0
    assert RateLimiter(1, manual_clock).check("bob") == 0


# --- configuration and compliance ---------------------------------------


def test_new_settings_have_safe_defaults_and_hide_the_keys():
    defaults = load_settings({})
    configured = load_settings({"API_KEYS": f"alice:{KEY_16}"})

    assert defaults.environment == "development"
    assert defaults.api_keys == {}
    assert defaults.rate_limit_per_minute == 30
    assert configured.api_keys == {"alice": KEY_16}
    assert KEY_16 not in repr(configured)


def test_production_collects_every_unsafe_setting_without_showing_keys():
    unsafe = {
        "ENVIRONMENT": "production",
        "API_KEYS": "alice:short-key-1234",
        "LANGSMITH_TRACING": "true",
        "HIDE_INPUTS": "false",
    }
    message = compliance_message(unsafe)

    assert "fake" in message.lower()
    assert "16" in message
    assert "HIDE_INPUTS" in message
    assert "short-key-1234" not in message
    assert "API_KEYS" in compliance_message(
        {"ENVIRONMENT": "production", **GATEWAY, "API_KEYS": ""}
    )
    hiding_outputs = {
        "ENVIRONMENT": "production", **GATEWAY, "API_KEYS": f"a:{KEY_16}",
        "LANGSMITH_TRACING": "true", "HIDE_OUTPUTS": "false",
    }
    assert "HIDE_OUTPUTS" in compliance_message(hiding_outputs)


def test_compliance_accepts_a_16_character_key_and_only_applies_in_production():
    safe = {
        "ENVIRONMENT": "production", **GATEWAY, "API_KEYS": f"a:{KEY_16}",
        "LANGSMITH_TRACING": "true", "HIDE_INPUTS": "true", "HIDE_OUTPUTS": "true",
    }
    too_short = {**safe, "API_KEYS": f"a:{KEY_16[:-1]}"}
    development = {**too_short, "ENVIRONMENT": "development", "MODEL_PROVIDER": "fake"}

    assert compliance_message(safe) == ""
    assert "16" in compliance_message(too_short)
    assert compliance_message(development) == ""


# --- tracing metadata ---------------------------------------------------


def test_trace_metadata_carries_the_client_and_never_the_key(monkeypatch):
    seen = []

    def fake_traceable(**_options):
        def decorator(func):
            def traced(*args, langsmith_extra=None, **kwargs):
                seen.append(langsmith_extra)
                return func(*args, **kwargs)

            return traced

        return decorator

    monkeypatch.setitem(
        sys.modules, "langsmith", types.SimpleNamespace(traceable=fake_traceable)
    )
    from app.tracing import Tracer  # pylint: disable=import-outside-toplevel

    token = bind_client("alice")
    try:
        Tracer(True, True, True).traceable("agent_run")(lambda text: text)("hi")
    finally:
        reset_client(token)

    assert seen[0]["metadata"]["client"] == "alice"
    assert "alice-key" not in str(seen)


# --- web page -----------------------------------------------------------


def test_page_asks_for_the_key_and_keeps_it_only_in_session_storage():
    html = PAGE.read_text(encoding="utf-8")
    field = re.search(r'<input[^>]*data-testid="api-key"[^>]*>', html)

    assert field is not None
    assert 'type="password"' in field.group(0)
    assert "sessionStorage" in html
    assert "localStorage" not in html
    assert "X-API-Key" in html
    assert "Clave inválida" in html
    assert "Demasiadas preguntas" in html


# --- smoke script -------------------------------------------------------


def load_smoke():
    """Carga ``scripts/smoke.py`` por su ruta."""
    path = PRODUCT_ROOT / "scripts" / "smoke.py"
    spec = importlib.util.spec_from_file_location("smoke_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def smoke_client(ask_with_key_status):
    """Cliente httpx con un servidor falso que responde por ruta y clave."""

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.headers.get("X-API-Key") == "good-key":
            return httpx.Response(ask_with_key_status, json={})
        return httpx.Response(401, json={"detail": "invalid or missing API key"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_smoke_prints_ok_for_each_check_and_fail_when_one_breaks(capsys):
    smoke = load_smoke()

    assert smoke.smoke("http://svc", "good-key", smoke_client(200)) is True
    assert capsys.readouterr().out.count("[OK]") == 3
    assert smoke.smoke("http://svc", "good-key", smoke_client(502)) is False
    output = capsys.readouterr().out
    assert output.count("[OK]") == 2
    assert output.count("[FAIL]") == 1


def test_smoke_without_the_key_variable_fails_with_a_clear_message(
    monkeypatch, capsys
):
    monkeypatch.delenv("SMOKE_API_KEY", raising=False)

    assert load_smoke().main(["http://svc"]) != 0
    assert "SMOKE_API_KEY" in capsys.readouterr().out


# --- publication files --------------------------------------------------


def test_container_runs_as_a_normal_user_and_leaves_secrets_out():
    dockerfile = (PRODUCT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    ignored = {
        line.strip().rstrip("/")
        for line in (PRODUCT_ROOT / ".dockerignore").read_text("utf-8").splitlines()
    }
    users = re.findall(r"^USER\s+(\S+)", dockerfile, re.MULTILINE)

    assert "FROM python:3.12-slim" in dockerfile
    assert users and users[-1] not in ("root", "0")
    assert "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}" in dockerfile
    assert {".env", "tests", "e2e"} <= ignored
    assert "__pycache__" in " ".join(ignored)


def test_ci_chains_style_unit_e2e_and_docker_on_push_and_pull_request():
    path = PRODUCT_ROOT / ".github" / "workflows" / "ci.yml"
    text = path.read_text(encoding="utf-8")
    jobs = re.findall(r"^  (style|unit|e2e|docker):\s*$", text, re.MULTILINE)

    assert jobs == ["style", "unit", "e2e", "docker"]
    assert len(re.findall(r"^    needs:", text, re.MULTILINE)) == 3
    assert "push" in text and "pull_request" in text
    assert "docker build" in text


def test_render_blueprint_publishes_only_after_checks_and_holds_no_secrets():
    text = (PRODUCT_ROOT / "render.yaml").read_text(encoding="utf-8")

    for line in ("runtime: docker", "plan: free", "healthCheckPath: /health",
                 "autoDeployTrigger: checksPass"):
        assert line in text
    for name in ("API_KEYS", "CF_ACCOUNT_ID", "CF_API_TOKEN"):
        assert re.search(rf"key: {name}\s*\n\s*sync: false", text)
    assert "LANGSMITH_API_KEY" not in text
