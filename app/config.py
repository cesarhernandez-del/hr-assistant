"""Lectura y validación de la configuración desde variables de entorno."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping

from app.auth import parse_api_keys
from app.errors import ConfigError

SUPPORTED_PROVIDERS = ("fake", "gateway")
ENVIRONMENTS = ("development", "production")
MIN_KEY_CHARS = 16
DEFAULT_SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
DEFAULT_LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


@dataclass(frozen=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    """Configuración validada del asistente.

    :param model_provider: Nombre del modelo a usar.
    :param agent_max_steps: Tope de vueltas del bucle del agente.
    :param max_question_chars: Largo máximo de la pregunta.
    :param employees_path: Ruta del archivo de empleados.
    :param service_name: Campo ``service`` del log.
    :param slo_p95_ms: Meta de latencia p95 en milisegundos.
    :param langsmith_tracing: Si se encienden las trazas de LangSmith.
    :param hide_inputs: Si no se mandan las entradas a LangSmith.
    :param hide_outputs: Si no se mandan las salidas a LangSmith.
    """

    model_provider: str = "fake"
    agent_max_steps: int = 3
    max_question_chars: int = 2000
    employees_path: Path = Path("data/employees.json")
    service_name: str = "hr-assistant"
    slo_p95_ms: int = 2000
    langsmith_tracing: bool = False
    hide_inputs: bool = True
    hide_outputs: bool = True
    cf_account_id: str = ""
    cf_gateway_id: str = "default"
    cf_api_token: str = field(default="", repr=False)
    model_small: str = DEFAULT_SMALL
    model_large: str = DEFAULT_LARGE
    routing: bool = True
    router_max_chars: int = 80
    history_window: int = 6
    model_max_tokens: int = 300
    model_temperature: float = 0
    cache_ttl_seconds: int = 0
    prices_path: Path = Path("data/model_prices.json")
    environment: str = "development"
    api_keys: Dict[str, str] = field(default_factory=dict, repr=False)
    rate_limit_per_minute: int = 30


def _non_negative_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero mayor o igual a cero de ``env``.

    :param env: Variables de entorno.
    :type env: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión.
    :type default: int
    :return: El entero leído.
    :rtype: int
    :raises ConfigError: Si no es un entero mayor o igual a 0.
    """
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from error
    if value < 0:
        raise ConfigError(f"{name} must be at least 0, got {value}")
    return value


def _temperature(env: Mapping[str, str]) -> float:
    """Lee ``MODEL_TEMPERATURE`` como número entre 0 y 2.

    :param env: Variables de entorno.
    :type env: Mapping[str, str]
    :return: La temperatura leída.
    :rtype: float
    :raises ConfigError: Si no es un número en el rango.
    """
    raw = env.get("MODEL_TEMPERATURE", "0")
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigError(
            f"MODEL_TEMPERATURE must be a number, got {raw!r}"
        ) from error
    if not 0 <= value <= 2:
        raise ConfigError(f"MODEL_TEMPERATURE must be between 0 and 2, got {value}")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    """Lee un booleano (``true`` o ``false``) de ``env``.

    :param env: Variables de entorno.
    :type env: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión.
    :type default: bool
    :return: El booleano leído.
    :rtype: bool
    :raises ConfigError: Si el valor no es ``true`` ni ``false``.
    """
    raw = env.get(name)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered not in ("true", "false"):
        raise ConfigError(f"{name} must be true or false, got {raw!r}")
    return lowered == "true"


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero positivo de ``env``.

    :param env: Variables de entorno.
    :type env: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión.
    :type default: int
    :return: El entero leído.
    :rtype: int
    :raises ConfigError: Si no es un entero mayor o igual a 1.
    """
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from error
    if value < 1:
        raise ConfigError(f"{name} must be at least 1, got {value}")
    return value


def check_compliance(settings: Settings) -> None:
    """Rechaza la configuración insegura cuando ``ENVIRONMENT=production``.

    Junta todas las violaciones en un solo error. Nunca incluye una clave:
    solo el nombre del cliente y la regla.

    :param settings: Configuración validada.
    :type settings: Settings
    :raises ConfigError: Si alguna regla de producción no se cumple.
    """
    if settings.environment != "production":
        return
    problems = []
    if settings.model_provider == "fake":
        problems.append("MODEL_PROVIDER must not be fake")
    if not settings.api_keys:
        problems.append("API_KEYS must not be empty")
    for client, key in settings.api_keys.items():
        if len(key) < MIN_KEY_CHARS:
            problems.append(
                f"API_KEYS key of client {client!r} must have at least "
                f"{MIN_KEY_CHARS} characters"
            )
    if settings.langsmith_tracing:
        if not settings.hide_inputs:
            problems.append("HIDE_INPUTS must be true when tracing is on")
        if not settings.hide_outputs:
            problems.append("HIDE_OUTPUTS must be true when tracing is on")
    if problems:
        raise ConfigError("production compliance failed: " + "; ".join(problems))


def _require_gateway_values(settings: Settings) -> None:
    """Exige los valores de Cloudflare cuando el proveedor es ``gateway``.

    En producción, las reglas de compliance se revisan primero para que el
    mensaje nombre la violación de seguridad más importante.

    :param settings: Configuración ya armada.
    :type settings: Settings
    :raises ConfigError: Si falta algún valor de Cloudflare.
    """
    if settings.model_provider != "gateway":
        return
    names = {
        "CF_ACCOUNT_ID": settings.cf_account_id,
        "CF_GATEWAY_ID": settings.cf_gateway_id,
        "CF_API_TOKEN": settings.cf_api_token,
    }
    for env_name, value in names.items():
        if not value.strip():
            check_compliance(settings)
            raise ConfigError(f"{env_name} is required with gateway")


def load_settings(env: Mapping[str, str]) -> Settings:
    """Construye la configuración a partir de ``env``.

    :param env: Variables de entorno (por ejemplo ``os.environ``).
    :type env: Mapping[str, str]
    :return: Configuración validada.
    :rtype: Settings
    :raises ConfigError: Si algún valor es inválido.
    """
    provider = env.get("MODEL_PROVIDER", "fake")
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigError(
            f"MODEL_PROVIDER must be one of {SUPPORTED_PROVIDERS}, got {provider!r}"
        )
    cloudflare = {
        "cf_account_id": env.get("CF_ACCOUNT_ID", ""),
        "cf_gateway_id": env.get("CF_GATEWAY_ID", "default"),
        "cf_api_token": env.get("CF_API_TOKEN", ""),
    }
    environment = env.get("ENVIRONMENT", "development")
    if environment not in ENVIRONMENTS:
        raise ConfigError(
            f"ENVIRONMENT must be one of {ENVIRONMENTS}, got {environment!r}"
        )
    settings = Settings(
        **cloudflare,
        environment=environment,
        api_keys=parse_api_keys(env.get("API_KEYS", "")),
        rate_limit_per_minute=_positive_int(env, "RATE_LIMIT_PER_MINUTE", 30),
        model_small=env.get("MODEL_SMALL", DEFAULT_SMALL),
        model_large=env.get("MODEL_LARGE", DEFAULT_LARGE),
        routing=_boolean(env, "ROUTING", True),
        router_max_chars=_positive_int(env, "ROUTER_MAX_CHARS", 80),
        history_window=_non_negative_int(env, "HISTORY_WINDOW", 6),
        model_max_tokens=_positive_int(env, "MODEL_MAX_TOKENS", 300),
        model_temperature=_temperature(env),
        cache_ttl_seconds=_non_negative_int(env, "CACHE_TTL_SECONDS", 0),
        prices_path=Path(env.get("PRICES_PATH", "data/model_prices.json")),
        model_provider=provider,
        agent_max_steps=_positive_int(env, "AGENT_MAX_STEPS", 3),
        max_question_chars=_positive_int(env, "MAX_QUESTION_CHARS", 2000),
        employees_path=Path(env.get("EMPLOYEES_PATH", "data/employees.json")),
        service_name=env.get("SERVICE_NAME", "hr-assistant"),
        slo_p95_ms=_positive_int(env, "SLO_P95_MS", 2000),
        langsmith_tracing=_boolean(env, "LANGSMITH_TRACING", False),
        hide_inputs=_boolean(env, "HIDE_INPUTS", True),
        hide_outputs=_boolean(env, "HIDE_OUTPUTS", True),
    )
    _require_gateway_values(settings)
    return settings
