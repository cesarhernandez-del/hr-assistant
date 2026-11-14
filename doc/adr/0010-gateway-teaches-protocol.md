# 0010. El proveedor gateway enseña el protocolo al modelo real

## Contexto
El agente espera un único objeto JSON (`tool` o `answer`), pero un modelo real no conoce ese protocolo y
suele envolver el JSON en bloques de código o texto. El modelo simulado ya cumple el protocolo. Cambiar el
agente para tolerar al modelo real lo ataría a un proveedor (ADR 0002).

## Decisión
`GatewayBackend` antepone en cada llamada un mensaje `system` en español, guardado en una constante del código
sin datos de personas. Describe las herramientas, el formato JSON de salida y el prefijo
`Resultado de la herramienta: `. El mensaje no es parte del historial: no cuenta para `HISTORY_WINDOW` y el agente
no lo ve. Al volver, el backend extrae el primer objeto JSON completo del texto (con o sin bloque
```` ```json ````); si no hay ninguno, devuelve el texto tal cual y el agente lo trata como respuesta inválida.
El texto del mensaje no se registra en el log ni en métricas; su costo se cuenta por `usage`.

## Consecuencias
- `agent.py` y `FakeBackend` no cambian; la adaptación vive en un solo módulo.
- Cada llamada paga los tokens del mensaje de sistema, y la evaluación debe medirlos con precio real.
- La extracción debe contar llaves con cuidado (cadenas y escapes); se prueba con casos adversos.
- Un cambio del texto del mensaje cambia la caché del gateway; es esperado.
