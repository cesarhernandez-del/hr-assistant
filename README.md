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
- `GET /metrics`: `pid`, `requests`, `error_rate`, `latency_ms` (p50, p95),
  `tokens` y `slo` de este proceso.

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
