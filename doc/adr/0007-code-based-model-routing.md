# 0007. Enrutamiento del modelo con una regla en código

## Contexto
La mayoría de las preguntas son consultas simples que un modelo pequeño resuelve a una fracción del costo del
grande. Hace falta elegir el modelo por pregunta sin añadir más costo ni latencia.

## Decisión
Una función pura `choose_route(question, settings)` elige `MODEL_LARGE` si `ROUTING=false`, si la pregunta pasa de
`ROUTER_MAX_CHARS` o si contiene una palabra clave («compara», «resume», «explica», «por qué», «analiza»,
«todos»); en otro caso `MODEL_SMALL`. Devuelve también el motivo, que sale como `route` en la respuesta. No se
usa un segundo modelo para clasificar.

## Consecuencias
- El enrutador no cuesta tokens, es determinista y se prueba con tablas de casos.
- Una pregunta compleja sin palabra clave puede ir al modelo pequeño; la evaluación de calidad lo detecta y se
  ajustan reglas o palabras.
- `ROUTING=false` da la línea base para medir el ahorro.
