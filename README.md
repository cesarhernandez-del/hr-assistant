# HR Assistant

Asistente de RR. HH. con un agente de bucle acotado y dos herramientas de solo
lectura (`get_employee` y `search_by_department`) sobre un directorio de
empleados. Incluye una API web (FastAPI), una página para preguntar y
observabilidad: un id por petición, log JSON, métricas y trazas opcionales en
LangSmith.

## Cómo correrlo

```
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Pruebas, desde `product/`:

```
pytest --cov=app
```

## Endpoints

- `GET /`: página web; muestra el `request_id` de cada respuesta.
- `GET /health`: estado del proceso.
- `POST /ask`: recibe `question` e `history`; responde con `request_id`.
- `GET /metrics`: `pid`, `requests`, `ask_requests`, `error_rate`, `latency_ms` (p50,
  p95, solo de `POST /ask`), `tokens` y `slo` de este proceso.

Toda respuesta trae el encabezado `X-Request-ID` (el del cliente si lo manda,
o un UUID). Un fallo interno responde `500` con
`{"detail": "internal error", "request_id": ...}`.

## Log

Una línea JSON por evento en la salida estándar, con `ts` (UTC), `service`,
`event` y `request_id`. Eventos: `request`, `agent_run`, `audit` y `error`. El
log nunca lleva el texto de preguntas ni de respuestas.

## Variables de entorno

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Modelo a usar |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del agente |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas |
| `LANGSMITH_API_KEY` | (vacía) | Clave de LangSmith, solo del entorno |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | No mandar textos a LangSmith |

Sin `LANGSMITH_API_KEY` el producto funciona igual y no se conecta a nada.

## Costos (sesión 3)

Con `MODEL_PROVIDER=gateway` se usa Cloudflare Workers AI a través de AI
Gateway (cliente `httpx`); faltar `CF_ACCOUNT_ID`, `CF_GATEWAY_ID` o
`CF_API_TOKEN` impide arrancar. Si la llamada falla, `POST /ask` responde
`502 {"detail": "model unavailable", "request_id": ...}`. Con `fake` hay dos
modelos simulados con el nombre y el precio de `MODEL_SMALL` y `MODEL_LARGE`.

Cuatro palancas: enrutamiento por regla (`ROUTING`, `ROUTER_MAX_CHARS`),
ventana de historial (`HISTORY_WINDOW`), tope de salida (`MODEL_MAX_TOKENS`) y
caché del gateway (`CACHE_TTL_SECONDS`). `POST /ask` agrega `model`, `route`,
`cached_calls` y `cost_usd`; `/metrics` agrega `cost_usd` acumulado. Los
precios salen de `data/model_prices.json` (USD por millón de tokens).

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `CF_ACCOUNT_ID` / `CF_GATEWAY_ID` / `CF_API_TOKEN` | (vacía) / `default` / (vacía) | Cuenta, gateway y token (secreto, solo del entorno) |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento por pregunta |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz |
| `HISTORY_WINDOW` | `6` | Mensajes de historial que se mandan |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida |
| `MODEL_TEMPERATURE` | `0` | Temperatura del modelo |
| `CACHE_TTL_SECONDS` | `0` | Caché del gateway (0: apagada) |
| `PRICES_PATH` | `data/model_prices.json` | Precios por modelo |

## Producción segura (sesión 4)

`POST /ask` y `GET /metrics` exigen el encabezado `X-API-Key`; sin clave o con una
inválida responden `401 {"detail": "invalid or missing API key"}`. `GET /`,
`GET /health` y `/docs` quedan abiertos. Más de `RATE_LIMIT_PER_MINUTE` peticiones de
un cliente en un minuto responden `429 {"detail": "rate limit exceeded"}` con
`Retry-After`. El nombre del cliente va en el log (`client`), la auditoría y los
metadatos de la traza; la clave nunca se escribe en ningún lado.

`API_KEYS` tiene la forma `cliente:clave,cliente2:clave2`. Si está mal formada, el
producto no arranca y el error dice la entrada y su largo, nunca su valor.

Con `ENVIRONMENT=production` el producto se niega a arrancar si `MODEL_PROVIDER` es
`fake`, si `API_KEYS` está vacía o tiene una clave de menos de 16 caracteres, o si las
trazas están encendidas y `HIDE_INPUTS` o `HIDE_OUTPUTS` no valen `true`. Las reglas y
su comprobación están en `doc/compliance-checklist.md`.

La página tiene un campo de clave; la guarda en `sessionStorage` (se borra al cerrar
la pestaña) y la manda en `X-API-Key`. Muestra «Clave inválida» con `401` y
«Demasiadas preguntas; espera N segundos» con `429`.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Con `production` se aplican las reglas de compliance |
| `API_KEYS` | (vacía) | Clientes y claves (secreto, solo del entorno) |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto |

`.env.example` lista todas las variables sin valores secretos.

## Multiagente y datos personales (sesión 5)

Cada pregunta pasa por tres agentes: `classifier` (decide `directory`, `out_of_scope` o
`sensitive`), `directory` (el agente de las sesiones 1 a 4) y `reviewer` (comprueba la
respuesta contra los resultados de las herramientas). `POST /ask` agrega `intent`,
`agents_used`, `pii_detected` y `fallback`.

Controles:

- **PII:** `app/pii.py` enmascara por código (expresiones regulares) correo, teléfono,
  CURP, RFC y tarjeta como `[EMAIL]`, `[PHONE]`, `[CURP]`, `[RFC]` y `[CARD]`, en la
  pregunta antes de cualquier modelo, log o traza, y en la respuesta antes de
  devolverla. La auditoría (`pii_masked`) y `pii_detected` llevan solo el tipo, nunca el
  valor.
- **Inyección de prompts:** `app/guard.py` bloquea, antes del clasificador, preguntas con
  frases de una lista fija (sin distinguir mayúsculas ni acentos). Responde el mensaje
  de `sensitive`, no llama a ningún modelo y la auditoría (`injection_blocked`) guarda
  solo la frase que coincidió.
- **Mínimo privilegio en los datos:** `get_employee` y `search_by_department` devuelven
  solo `id`, `name`, `department`, `role`, `start_date` y `status`; `phone` y `rfc`
  nunca llegan al modelo. Las preguntas sensibles se rechazan sin llamar herramientas.
- **Revisor:** con `retry` el agente de directorio se relanza una sola vez; si el revisor
  insiste, la respuesta es «No pude verificar la respuesta. Intenta con una pregunta más
  concreta.». Una salida del revisor que no sea JSON válido se trata como `ok` y se
  registra `reviewer_invalid`. Se apaga con `REVIEWER_ENABLED=false`. El clasificador
  trata como `out_of_scope` cualquier salida inválida: el código valida, el modelo solo
  propone.
- **Resiliencia:** cada llamada al gateway tiene tope de `MODEL_TIMEOUT_SECONDS`; ante
  timeout, error de red, `429` o `5xx` se reintenta una vez tras
  `MODEL_RETRY_BACKOFF_SECONDS`; si el modelo grande sigue fallando se usa `MODEL_SMALL`
  (`fallback: true`, evento `model_fallback`); si también falla, `502`.

- **Motivo del revisor registrado:** `POST /ask` y el evento `agent_run` llevan
  `review_retries` (0 o 1); `agent_run` agrega `review_reason`, el motivo enmascarado con
  `app/pii.py` y recortado a 200 caracteres (vacío si aprobó a la primera). El tramo
  `reviewer` de LangSmith agrega `verdict` y `reason` a sus metadatos, con la misma
  máscara y recorte. Es una excepción declarada a `HIDE_OUTPUTS`: el motivo describe la
  respuesta, no repite la pregunta ni datos privados.
- **SLO medido solo sobre `/ask`:** el balanceador consulta `/health` cada pocos segundos
  y esas peticiones de un milisegundo esconden la latencia real de las preguntas.

`/metrics` agrega `intents`, `pii_masked`, `injections_blocked`, `fallbacks`,
`cache_hit_rate` y `cost_by_client` (por nombre de cliente, nunca por clave).

### Cambio de significado de `latency_ms`

Desde esta sesión `latency_ms` (`p50` y `p95`) y `slo` de `/metrics` se calculan **solo
con `POST /ask`**; antes contaban todas las peticiones. `/metrics` agrega `ask_requests`,
el número de peticiones a `POST /ask` que entran en ese cálculo. `requests` y
`error_rate` siguen contando todas las peticiones, como en la sesión 2. Quien compare
latencias anteriores con las nuevas debe tener en cuenta este cambio.

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `REVIEWER_ENABLED` | `true` | Enciende el agente revisor |
| `MODEL_TIMEOUT_SECONDS` | `20` | Tiempo máximo de cada llamada al gateway |
| `MODEL_RETRY_BACKOFF_SECONDS` | `1` | Espera antes del único reintento |
| `FAKE_FAIL_LARGE` | `false` | Solo con `fake`: hace fallar al modelo grande; ignorada en producción |
| `FAKE_REVIEWER_RETRY_ONCE` | `false` | Solo con `fake`: el revisor pide una corrección por pregunta |
