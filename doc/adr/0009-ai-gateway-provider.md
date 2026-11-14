# 0009. Modelo real por AI Gateway con fallo explícito

## Contexto
El producto debe usar un modelo real de Workers AI sin atar al agente a un proveedor, aprovechar la caché del
gateway y no ocultar fallos del servicio externo ni filtrar el token.

## Decisión
`MODEL_PROVIDER=gateway` agrega `GatewayBackend`, que llama por `httpx` a AI Gateway con el token en
`Authorization`, el tope `MODEL_MAX_TOKENS`, la temperatura y, con `CACHE_TTL_SECONDS` mayor que 0, el encabezado
`cf-aig-cache-ttl`. Lee los tokens de `usage` y la caché de `cf-aig-cache-status`. Cualquier fallo se convierte en
`ModelUnavailable`, que la API responde como `502 {"detail": "model unavailable", "request_id": ...}`. Con
`gateway`, faltar una variable `CF_*` impide arrancar; el token nunca se registra.

## Consecuencias
- Cambiar entre `fake` y `gateway` no toca el agente (ADR 0002).
- Los fallos son visibles y con `request_id`; no se inventan respuestas ni costos.
- La caché queda apagada por omisión porque puede servir respuestas repetidas.
- Las pruebas del gateway usan un transporte simulado de `httpx`, sin red.
