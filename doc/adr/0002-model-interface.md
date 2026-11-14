# 0002. Modelo detrás de una interfaz

## Contexto
Hoy solo existe un modelo simulado, pero más adelante se querrá usar un modelo real sin reescribir el agente.

## Decisión
El agente depende solo de `complete(messages)`, que devuelve un objeto JSON (`tool` o `answer`). El proveedor se elige con `MODEL_PROVIDER`; en esta sesión solo existe `fake`, determinista y sin red.

## Consecuencias
- Las pruebas son deterministas y gratuitas.
- Cambiar de modelo no toca `agent.py`.
- Un modelo real podría devolver JSON inválido, por lo que el agente debe manejarlo.
