# Lista de compliance

Reglas que el producto revisa solo. Con `ENVIRONMENT=production`, `check_compliance`
(en `app/config.py`) se llama al armar la aplicación y, si falla alguna regla, el proceso
no arranca. El error junta todas las violaciones y nunca incluye el valor de una clave.

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| Con `production`, `MODEL_PROVIDER` no puede ser `fake` | `check_compliance` en `app/config.py` | `tests/test_production_units.py` y escenario «Production refuses an unsafe configuration» |
| Con `production`, `API_KEYS` no puede estar vacía | `check_compliance` en `app/config.py` | Mismo escenario y `test_production_collects_every_unsafe_setting_without_showing_keys` |
| Con `production`, cada clave tiene al menos 16 caracteres | `check_compliance` (`MIN_KEY_CHARS`) en `app/config.py` | `test_compliance_accepts_a_16_character_key_and_only_applies_in_production` |
| Con `production` y trazas encendidas, `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` | `check_compliance` en `app/config.py`; el ocultado real, en `app/tracing.py` | Pruebas unitarias de compliance y de metadatos de la traza |
| `API_KEYS` bien formada (`cliente:clave`); el error dice la entrada y su largo, nunca el valor | `parse_api_keys` en `app/auth.py` | `test_a_malformed_api_keys_error_never_shows_the_value` y escenario de `API_KEYS` mal formada |
| `POST /ask` y `GET /metrics` exigen `X-API-Key`; sin clave o inválida responden `401` | `require_client` en `app/main.py` | Escenarios «Asking without a valid key» y «Only ask and metrics need a key» |
| Las claves se comparan en tiempo constante | `authenticate` con `hmac.compare_digest` en `app/auth.py` | `test_authenticate_returns_the_client_only_for_the_exact_key` |
| La clave nunca se escribe en el log, la traza ni un error | `app/logging_json.py` (solo `client`), `app/tracing.py` (solo `client`), `repr=False` en `Settings.api_keys` | Escenario «The key is never written to the log or to a response» |
| Cada cliente tiene un límite de peticiones por minuto; al pasarlo, `429` con `Retry-After` | `RateLimiter` en `app/ratelimit.py` y `require_client` | Escenarios de límite y pruebas del limitador con reloj manual |
| El nombre del cliente va en el log, la auditoría y la traza | `app/request_context.py`, `app/logging_json.py`, `app/tracing.py` | Escenario «The client name reaches the log and the audit» |
| La página guarda la clave solo en `sessionStorage` | `app/static/index.html` | `test_page_asks_for_the_key_and_keeps_it_only_in_session_storage` |
| Los secretos no están en el repositorio ni en la imagen | `render.yaml` (`sync: false`), `.dockerignore`, `.env.example` sin valores | Pruebas de estructura de los archivos de publicación y revisión de `security` |

## Controles de la sesión 5 (multiagente y datos personales)

Los controles de PII e inyección son código determinista, no instrucciones a un modelo.

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| Correo, teléfono, CURP, RFC y tarjeta se enmascaran (`[EMAIL]`, `[PHONE]`, `[CURP]`, `[RFC]`, `[CARD]`) en la pregunta antes de cualquier modelo, log o traza | `app/pii.py` | Pruebas unitarias de PII y `test_contract_05.py` |
| La respuesta se enmascara igual antes de devolverla; `pii_detected` lista solo tipos | `app/pii.py` y el flujo de `POST /ask` | Pruebas unitarias y de contrato |
| Ningún valor de PII en el log, la auditoría, la traza ni `/metrics`; `pii_masked` lleva `where` y `types` | `app/pii.py`, `app/logging_json.py`, `app/tracing.py` | Escenarios de PII y revisión de `qa` |
| Frases de inyección bloqueadas antes del clasificador, sin llamar a ningún modelo (costo cero); `injection_blocked` guarda solo la frase | `app/guard.py` | Pruebas unitarias del filtro y de contrato; cada frase nueva lleva su prueba |
| Mínimo privilegio: las herramientas devuelven solo `id`, `name`, `department`, `role`, `start_date` y `status`; `phone` y `rfc` no llegan al modelo | Herramientas del agente de directorio en `app/` | Pruebas unitarias de las herramientas |
| Preguntas `sensitive` y `out_of_scope` se responden con mensaje exacto y sin herramientas | Flujo del clasificador en `app/` | `test_contract_05.py` |
| El clasificador valida su salida: cualquier JSON ajeno se trata como `out_of_scope` | Agente `classifier` en `app/` | Pruebas unitarias del clasificador |
| El revisor valida la respuesta; un solo reintento y luego mensaje fijo; salida inválida cuenta como `ok` y se registra `reviewer_invalid` | Agente `reviewer` en `app/` | Pruebas unitarias y de contrato |
| Resiliencia: timeout (`MODEL_TIMEOUT_SECONDS`), un reintento tras `MODEL_RETRY_BACKOFF_SECONDS` ante red, `429` o `5xx`, respaldo con `MODEL_SMALL` y `502` si también falla | Cliente del gateway en `app/` | Pruebas con `FAKE_FAIL_LARGE=true` y fallas simuladas |
| `FAKE_FAIL_LARGE` solo existe con `MODEL_PROVIDER=fake`; en producción se ignora | `app/config.py` | Prueba de compliance en producción |
| `/metrics` no expone claves ni PII; `cost_by_client` va por nombre de cliente | `app/metrics.py` | Pruebas de `/metrics` |
| `FAKE_REVIEWER_RETRY_ONCE` solo existe con `MODEL_PROVIDER=fake` | `app/config.py`, `app/llm.py` | Pruebas de configuración y del revisor simulado |
| El motivo del revisor queda registrado: `review_retries` en la respuesta y en `agent_run`; `review_reason` enmascarado con `app/pii.py` y recortado a 200 caracteres | `app/orchestrator.py` (`_safe_reason`) | Pruebas unitarias del orquestador y de contrato |
| El tramo `reviewer` de LangSmith lleva `verdict` y `reason` (enmascarado y recortado); excepción declarada a `HIDE_OUTPUTS`, porque el motivo describe la respuesta y no repite pregunta ni datos privados | `app/orchestrator.py`, `app/tracing.py` | Pruebas de metadatos de la traza |
| `latency_ms` y `slo` se calculan solo con `POST /ask`; `ask_requests` cuenta esas peticiones; `requests` y `error_rate` cuentan todas | `Metrics.record_request` en `app/metrics.py` | Pruebas de `/metrics` (con `/health` de por medio la latencia no baja) |

## Verificación por control (sesión 5)

Resumen de cada control del reto y qué evidencia lo respalda.

| Control | Qué garantiza | Evidencia |
| --- | --- | --- |
| PII | Ningún dato personal llega a un modelo, al log, a la auditoría, a la traza ni a `/metrics`; solo su tipo | `app/pii.py`, `pii_detected`, evento `pii_masked` |
| Inyección | Frases de lista fija bloqueadas en código antes de cualquier modelo; costo cero | `app/guard.py`, evento `injection_blocked` (solo la frase) |
| Mínimo privilegio | `phone` y `rfc` existen en los datos pero las herramientas solo entregan campos públicos | `app/directory.py`, pruebas de herramientas |
| Revisor y su motivo | Un reintento como máximo; el motivo queda en `agent_run` y en la traza, sin PII y de a lo más 200 caracteres | `app/reviewer.py`, `app/orchestrator.py`, `review_reason` |
| Resiliencia | Tope de tiempo, un reintento, respaldo con `MODEL_SMALL`, `502` si también falla | `app/resilience.py`, `app/gateway.py`, evento `model_fallback` |
| SLO sobre `/ask` | La latencia no se diluye con `/health`; `ask_requests` muestra la base del cálculo | `app/metrics.py` |

Nota: `latency_ms` cambió de significado respecto de la sesión 2 (antes contaba todas las
peticiones; ahora solo `POST /ask`). Está registrado en `README.md`.
