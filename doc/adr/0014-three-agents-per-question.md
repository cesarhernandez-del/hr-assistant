# 0014. Tres agentes por pregunta

## Contexto
Un solo agente recibe cualquier pregunta, llama herramientas aunque la pregunta sea sensible o ajena al directorio, y
nadie comprueba su respuesta. Con datos de personas, eso es un riesgo y un gasto innecesario.

## Decisión
Cada pregunta pasa por `classifier`, `directory` y `reviewer`, coordinados por `Orchestrator` (`app/orchestrator.py`).
El clasificador y el revisor usan siempre `MODEL_SMALL` y responden un JSON mínimo que el código valida: lo inválido
degrada a `out_of_scope` (clasificador) u `ok` con `reviewer_invalid` (revisor). El agente de directorio es el de las
sesiones 1 a 4, sin cambios. El revisor relanza al agente de directorio una sola vez; un segundo `retry` da el mensaje
exacto del contrato. `REVIEWER_ENABLED=false` lo apaga. La respuesta informa `intent`, `agents_used` y
`review_retries`. El motivo del revisor se registra en `agent_run` (`review_reason`) y en los metadatos de su tramo,
enmascarado con `pii.py` y recortado a 200 caracteres.

## Consecuencias
- Las preguntas sensibles o ajenas se resuelven con una sola llamada barata y sin herramientas.
- Una pregunta de directorio cuesta tres agentes; se mide en `cost_usd` y en `evaluate`.
- El modelo propone y el código decide: ninguna salida de modelo se usa sin validar.
- Hay más tramos que mirar: cada agente es un tramo con nombre en la traza.
- Se sabe por qué el revisor pidió `retry` aunque `HIDE_OUTPUTS` oculte su salida; es una excepción declarada y acotada.
