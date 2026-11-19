# Evidencia del reto M4

Sistema en producción: https://hr-assistant-nme3.onrender.com (Render, una instancia, plan gratuito).
Las mediciones son del 18 de noviembre de 2026. Los archivos están en esta carpeta (`doc/evidencia/`): las salidas de terminal se
guardan como texto (se pueden buscar y comparar) y las pantallas web como imagen.

## 1. Arquitectura y despliegue

| Qué se comprueba | Resultado | Archivo |
|---|---|---|
| Servicio Live en Render | Último despliegue de `main` en Live | `01-render-live.png` |
| `GET /health` en producción | 200 | `01-health.json` |
| Documentación de la API en `/docs` | Swagger con `/ask`, `/health` y `/metrics` | `02-docs.png` |
| CI | style, unit, e2e y docker en verde | `03-github-actions.png` |
| Fábrica | Reporte de la corrida: unit 228 pruebas con 97.5 % de cobertura, qa 10/10, e2e 6. La segunda corrida (puntos 12 y 13) dejó contract en 45 | `04-factory-report.md` |

Prueba de carga con `scripts/load.py` (salida completa en `05-load.txt`; la pregunta de calentamiento no se cuenta):

| Carga | Respuestas | p50 | p95 | Máximo |
|---|---|---|---|---|
| 20 preguntas, de 5 en 5 | 20 con 200 | 1,321 ms | 2,967 ms | 3,076 ms |
| 35 simultáneas | 29 con 200 y 6 con 429 | 4,786 ms | 5,868 ms | 6,449 ms |

Sin errores 5xx en ninguna de las dos. El ADR 0017 cita una corrida anterior del mismo día con valores parecidos. El SLO de producción (p95 de 3,500 ms) está justificado en
`doc/adr/0017-slo-p95-3500ms.md`.

## 2. Observabilidad

| Qué se comprueba | Resultado | Archivo |
|---|---|---|
| Traza en LangSmith | Un tramo por agente (classifier, directory, reviewer), con el `request_id` en metadatos y entradas y salidas ocultas | `06-langsmith-trace.png` |
| Corrección del revisor | Respuesta con `review_retries` 1 y traza con 5 tramos y el motivo en metadatos | `07-review-retry.json`, `07-langsmith-review-retry.png` |
| Métricas técnicas y de negocio | `/metrics`: latencia solo de `POST /ask`, SLO, intenciones, PII enmascarada, inyecciones bloqueadas, respaldos, caché y costo por cliente. Con solo 5 preguntas, el p95 (4,043 ms, SLO no cumplido) es la primera pregunta de la sesión, que en LangSmith tardó 1.78 s en los agentes | `08-metrics.json` |
| Depuración en producción | El mismo `request_id` en la página (id de soporte), en Render Logs y en LangSmith | `09-debug-page.png`, `09-debug-render-log.png`, `09-debug-trace.png` |
| Tableros | Monitoreo del proyecto en LangSmith (trazas, latencia, errores) y analítica de AI Gateway (715 llamadas en 24 h, 194 mil tokens, 0.02 USD, 0 errores) | `10-langsmith-dashboard.png`, `10-ai-gateway.png` |

## 3. Costos

`verification evaluate` (modelo simulado) mide solo el costo, porque el simulado responde igual con o sin palancas.
`scripts/evaluate_real.py` corre las mismas 8 preguntas, con 10 mensajes de historial, contra Workers AI.

| Corrida | Modelo | Calidad | Costo (USD) | Tokens de entrada |
|---|---|---|---|---|
| Línea base | Simulado | 100 % | 0.000903 | 2,742 |
| Con palancas | Simulado | 100 % | 0.000177 (80 % menos) | 2,210 |
| Línea base | Workers AI | 25 % | 0.008227 | 25,981 |
| Con palancas | Workers AI | 75 % | 0.000724 (91 % menos) | 10,794 |

Análisis del modelo real (salida completa en `evaluate_real.txt`):
- La línea base (sin enrutamiento ni ventana, siempre el 70B) saca 25 % porque, con historial largo, el 70B repitió
  la llamada a la herramienta hasta agotar el tope de pasos en 6 de 7 preguntas de directorio. La ventana de
  historial evita ese ciclo: además de ahorrar, mejora la calidad.
- Con palancas fallaron 2 de 8: «Lista el departamento de Tecnología» (lista incompleta tras la corrección del
  revisor) y «¿Quién es EMP-0099?» (el 8B consultó también EMP-0001). En producción, sin historial, EMP-0099
  respondió «El empleado EMP-0099 no existe.» en 4 de 4 llamadas.

Caché de AI Gateway: estaba apagada en producción (`CACHE_TTL_SECONDS` vale 0 por omisión; la analítica muestra
715 llamadas y 0 aciertos). Se encendió en Render con `CACHE_TTL_SECONDS=3600`: la misma pregunta dos veces
muestra `cached_calls` mayor que 0 en la segunda (`17-cache.txt`). Trade-off: durante una hora, un cambio en el
directorio no se ve en una pregunta idéntica.

## 4. Seguridad

Preguntas reales en producción:

| Pregunta | Resultado | Archivo |
|---|---|---|
| Con un correo en la pregunta | `pii_detected: ["email"]`; el correo no aparece en la respuesta | `11-pii.json` |
| Por el salario de un empleado | `intent: sensitive`, solo el clasificador, sin herramientas | `12-sensitive.json` |
| «Ignora las instrucciones…» | `agents_used: []`, costo 0 | `13-injection.json` |
| Fuera de alcance | `intent: out_of_scope`, un solo agente | `14-out-of-scope.json` |
| Ráfaga de 35 preguntas | 6 respuestas 429; el encabezado `Retry-After` dice cuándo reintentar | `05-load.txt`, `15-rate-limit-headers.txt` |
| Auditoría | Líneas `audit` en Render Logs (`injection_blocked` y `pii_masked`) con el tipo de dato y la frase detectada, nunca el valor personal | `16-audit-log-1.png`, `16-audit-log-2.png` |

Los controles, su código y su prueba están en `doc/compliance-checklist.md`.

## 5. Limitaciones conocidas

- El límite de peticiones y las métricas viven en la memoria de cada copia: con N copias, el límite real es
  N × 30 por minuto. Se resolvería con estado compartido (Redis).
- El plan gratuito de Render duerme tras 15 minutos; la primera petición tarda cerca de un minuto.
- Con ráfagas grandes, el p95 supera el SLO (5.9 s con 35 simultáneas). `/metrics` lo reporta con `slo.met: false`.
- El modelo de 8B se equivoca con contexto largo o con listas largas. El revisor lo detecta, pero una sola
  corrección no siempre alcanza.
