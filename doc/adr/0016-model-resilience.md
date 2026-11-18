# 0016. Resiliencia hacia el modelo

## Contexto
El gateway puede tardar, devolver 429 o 5xx, o caerse un instante. Con tres agentes por pregunta hay tres veces más
llamadas que pueden fallar, y un fallo aislado no debería romper la respuesta.

## Decisión
`ResilientBackend` (`app/resilience.py`) envuelve el backend. Cada llamada tiene un tope de `MODEL_TIMEOUT_SECONDS`.
Ante timeout, error de red, 429 o 5xx se reintenta una vez tras `MODEL_RETRY_BACKOFF_SECONDS`, con la espera inyectada
para las pruebas. Si el modelo grande sigue fallando, se repite con `MODEL_SMALL`, y la respuesta lleva `fallback: true`
con un evento `model_fallback` (modelo y tipo de error, sin mensajes). Si el pequeño falla, `502` como en la sesión 3.
Los errores 4xx distintos de 429 no se reintentan. Con el modelo simulado, `FAKE_FAIL_LARGE=true` prueba el respaldo sin red.

## Consecuencias
- Un fallo pasajero ya no llega a la persona; el costo es una espera de hasta un segundo.
- El respaldo puede dar respuestas de menor calidad: queda visible en `fallback`, el log y `/metrics` (`fallbacks`).
- El peor caso queda acotado: un reintento por llamada y un respaldo, sin bucles.
- Si el enrutador ya eligió el modelo pequeño no hay respaldo; tras el reintento responde `502`.
