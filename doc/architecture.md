# Arquitectura del HR Assistant

API FastAPI sin estado, un agente con dos herramientas de solo lectura y un modelo detrás de una interfaz.
La sesión 2 agrega observabilidad: id por petición, log JSON, métricas por proceso y trazas opcionales.
La sesión 3 agrega el modelo real por AI Gateway (que le enseña el protocolo al modelo), enrutamiento, ventana de
historial, tope de salida, caché y costo por respuesta.
La sesión 4 agrega clave por cliente, límite de peticiones, compliance como código, contenedor, CI y Render.
Decisiones en `adr/`.

```mermaid
flowchart LR
    Web[Página web index.html con campo api-key] -->|POST /ask, X-API-Key, history| MW[Middleware request_id y latencia]
    Web -->|GET /| MW
    MW --> Main[main.py create_app]
    Main -->|al arrancar| Config[config.py y check_compliance]
    Config -.->|ConfigError: no arranca| Main
    Main -->|require_client| Auth[auth.py parse y authenticate]
    Auth -->|cliente| Ctx
    Auth -.->|401| MW
    Main -->|cupo por cliente| Rate[ratelimit.py ventana 60 s]
    Rate -->|reloj inyectado| Clock
    Rate -.->|429 Retry-After| MW
    Main -->|ventana y ruta| Router[router.py]
    Main -->|crea por petición| RM[llm.py RequestModel]
    Main --> Agent[agent.py bucle con tope]
    Agent -->|complete messages| RM
    RM -->|complete model, messages| Fake[llm.py FakeBackend]
    RM -->|complete model, messages| GW[gateway.py GatewayBackend]
    GW -->|antepone mensaje system| Sys[SYSTEM_PROMPT constante]
    GW -->|HTTPS, cache ttl| CF[(Cloudflare AI Gateway)]
    CF -->|texto del modelo| Ext[extract_json primer objeto JSON]
    Ext --> GW
    RM -->|tokens no cacheados| Price[pricing.py]
    Price --> Prices[(data/model_prices.json)]
    Agent -->|get_employee, search_by_department| Dir[directory.py]
    Dir --> Data[(data/employees.json)]
    Main -->|GET /health sin clave| Health[status y pid]
    Main -->|GET /metrics con clave| Metrics[metrics.py por proceso y costo]
    MW --> Ctx[request_context.py request_id y client]
    MW --> Clock[clock.py reloj inyectado]
    MW -->|request, error con client| Log[logging_json.py stdout]
    Main -->|agent_run| Log
    Agent -->|audit con client| Log
    GW -.->|ModelUnavailable, 502| Main
    Agent -.->|traceable con client| Trace[tracing.py LangSmith]
    RM -.->|traceable opcional| Trace
    MW --> Metrics

    subgraph Publicación
        Repo[Repositorio GitHub] --> CI[ci.yml: style, unit, e2e, docker]
        CI -->|checksPass| Render[Render: Dockerfile y render.yaml]
        Render -->|/health| Smoke[scripts/smoke.py]
    end
```

## Módulos

- `config.py`: variables de entorno validadas, incluidas las de observabilidad, costos y producción; `check_compliance`.
- `auth.py`: lectura de `API_KEYS` y autenticación por cliente, sin escribir nunca la clave.
- `ratelimit.py`: ventana deslizante de 60 s por cliente con el reloj inyectado.
- `directory.py`: lectura de empleados.
- `router.py`: regla en código que elige el modelo y recorta el historial.
- `pricing.py`: precios por modelo y costo en USD.
- `gateway.py`: llamada a AI Gateway, mensaje de sistema, extracción tolerante del JSON, caché y errores como `ModelUnavailable`.
- `llm.py`: interfaz del modelo, modelo simulado y `RequestModel` por petición.
- `agent.py`: bucle de herramientas con tope; informa `stopped` y herramientas con argumentos.
- `clock.py`: reloj inyectado para hora y latencias.
- `request_context.py`: id de la petición y cliente en `ContextVar`.
- `logging_json.py`: una línea JSON por evento, con `client` si existe, sin texto de preguntas ni respuestas.
- `metrics.py`: contadores, p50, p95, SLO y costo acumulado del proceso.
- `tracing.py`: trazas de LangSmith, apagadas sin clave, con el cliente en los metadatos.
- `main.py`: rutas, middleware, dependencia de autenticación y ensamblado de dependencias.
- `static/index.html`: interfaz para el personal de RH, con campo de clave en `sessionStorage` y el `request_id` visible.
