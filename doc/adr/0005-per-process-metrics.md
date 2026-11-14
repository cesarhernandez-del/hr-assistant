# 0005. Métricas en memoria por proceso

## Contexto
Se necesita medir latencia, errores, tokens y el SLO, pero la API es sin estado y se escala con más copias. No se permite agregar librerías ni servicios externos.

## Decisión
`GET /metrics` informa solo lo del proceso que responde (incluye `pid`), con contadores y una ventana acotada de latencias en memoria. `slo.met` es verdadero si el p95 es menor que `SLO_P95_MS`. Las métricas se crean en `create_app()` y no se comparten entre peticiones de otros procesos.

## Consecuencias
- Es simple y no rompe la regla de no guardar estado de negocio: las métricas son del proceso, no de la conversación.
- Con varias copias cada una muestra su parte; agregarlas queda para una sesión futura (por ejemplo un recolector externo).
- Un reinicio pone los contadores en cero.
