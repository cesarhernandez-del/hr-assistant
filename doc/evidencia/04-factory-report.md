# Reporte de la fábrica: sesión 5 (multiagente y datos personales)

## Estado

**LISTA.** La prueba de humo en producción pasó. La corrió la persona en su terminal (la clave no pasa por la
fábrica) y reportó `[OK]`; este reporte se apoya en esa confirmación, no en una ejecución propia de la fábrica.

## Entrega

- URL pública: https://hr-assistant-nme3.onrender.com
- Pull Request: https://github.com/cesarhernandez-del/hr-assistant/pull/1 (rama `reto-m4` hacia `main`)
- La fusión a `main` la hace la persona; la fábrica no la hace.

## Correcciones, vueltas y ciclos

- Correcciones del paso 5: 1 de 2. `qa` falló por 2 avisos en pruebas (orden de imports y lista de frases
  duplicada entre `test_guard.py` y `app/guard.py`); se corrigieron con `qa-unit`, que además agregó las pruebas de
  `resilience`, `reviewer`, `metrics` y `FakeBackend` que faltaban.
- Vueltas de `qa-style`: 1 de 2, con `APROBADO`.
- Ciclos de triage: 1 de 2. `/ask` con clave daba 401; el diagnóstico fue `persona` y la causa era una clave mal
  pegada en `SMOKE_API_KEY`. No hubo cambios de código.
- Alerta del paso 3: ninguna. `unit` falló (rojo) con las pruebas nuevas, como se esperaba.

## Tabla de `evaluate`

| Configuración | Calidad | Costo (USD) | Tokens de entrada |
|---------------|---------|-------------|-------------------|
| Línea base    | 100 %   | 0.000903    | 2742              |
| Con palancas  | 100 %   | 0.000177    | 2210              |

## Verificaciones

`unit` 228 pruebas (cobertura 97,5 %), `contract` 32, `qa` 10.00/10, `e2e` 6, `evaluate` OK, `production` OK (persona).

## Pendientes y avisos

- Con un `model=` o `backend=` inyectado, `create_app` corre solo el agente de directorio (modo de compatibilidad con
  las sesiones 1 a 4). No afecta a producción.
- `test_guard.py` ya no compara contra una lista fija de frases de inyección: borrar una frase de `app/guard.py` no
  rompe ninguna prueba.
- `product/.env.example` no incluye las variables nuevas (tienen valor por omisión).
- Mejora opcional de `qa-style`: `httpx.Client(timeout=30.0)` en `app/main.py` es un valor fijo.
- La identidad de los commits es la automática del equipo; se puede corregir con `git commit --amend --reset-author`.

## Bitácora

1. Plan: `architect` escribió `output/plan.md` y los ADR 0014 a 0016.
2. Aprobación del plan: la persona dijo si, y con eso aceptó las tres propuestas del plan.
3. Pruebas primero: `qa-unit`; `unit` en rojo.
4. Especialistas en paralelo: `developer` y `qa-e2e`.
5. Compuertas: `qa` falló una vez; corrección con `qa-unit`; luego `unit`, `contract`, `qa`, `e2e` y `evaluate` en OK.
6. Documentos de seguridad: `security` actualizó README y checklist; `qa` en OK.
7. `qa-style`: `APROBADO` en la primera vuelta.
8. Aprobación para publicar: la persona dijo si.
9. Publicar: `scripts/publish.py hr-assistant --branch reto-m4` en OK; Pull Request #1 abierto.
10. Humo y triage: un ciclo; `persona`; resuelto por la persona.
11. Pipeline y reporte.

Pipeline: [output/pipeline.md](pipeline.md)
