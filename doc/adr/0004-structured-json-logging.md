# 0004. Log JSON con id de petición y sin contenido

## Contexto
Para saber qué pasó con una petición hace falta correlacionar eventos. Las preguntas y respuestas pueden contener datos personales de empleados.

## Decisión
Cada petición lleva un `request_id` (el de `X-Request-ID` o un UUID) guardado en una `ContextVar`. Se emite una línea JSON por evento (`request`, `agent_run`, `audit`, `error`) en la salida estándar, con `ts` UTC, `service` y `request_id`. Nunca se registra el texto de la pregunta ni de la respuesta, y el error solo lleva el tipo. La hora sale de un reloj inyectado.

## Consecuencias
- Con un id se reconstruye toda la petición con una búsqueda en el log.
- Las pruebas son deterministas y pueden comprobar que no hay texto sensible.
- No se puede depurar leyendo preguntas; hay que apoyarse en conteos y en `audit`.
