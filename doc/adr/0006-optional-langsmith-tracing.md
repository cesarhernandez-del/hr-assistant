# 0006. Trazas de LangSmith opcionales y con datos ocultos

## Contexto
Las trazas ayudan a ver cada corrida, llamada al modelo y herramienta, pero mandan datos a un servicio externo y requieren una clave.

## Decisión
Se usa `@traceable` a través de un módulo `tracing.py`. Solo se activa con `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY`; sin ellos, el decorador no hace nada y no hay conexión. `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` por omisión. El `request_id` va en los metadatos. La clave se lee del entorno y nunca se escribe en log ni código.

## Consecuencias
- El producto funciona igual sin LangSmith y las pruebas no necesitan red.
- Por omisión no salen textos de empleados del sistema.
- Ver el contenido en las trazas exige cambiar la configuración de forma explícita.
