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
