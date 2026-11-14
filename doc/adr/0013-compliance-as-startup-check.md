# 0013. Compliance como validación de arranque

## Contexto
Las reglas de seguridad de producción (modelo real, claves largas, trazas sin entradas ni salidas) suelen vivir en un
documento que nadie vuelve a leer. Una configuración insegura en Render llegaría a usuarios reales.

## Decisión
Con `ENVIRONMENT=production`, `check_compliance(settings)` corre al armar la aplicación y lanza `ConfigError` con
todas las violaciones juntas: proveedor `fake`, `API_KEYS` vacía o con claves de menos de 16 caracteres, y trazas
encendidas sin `HIDE_INPUTS` y `HIDE_OUTPUTS` en `true`. Los mensajes nunca incluyen valores de claves.
`doc/compliance-checklist.md` lista cada regla, su lugar en el código y su prueba. Con `development` no bloquea.

## Consecuencias
- Una configuración insegura no arranca: el despliegue falla antes de recibir tráfico.
- Cada regla nueva exige código, prueba y fila en la tabla; `security` revisa que coincidan.
- Desarrollo y CI siguen usando `fake` sin fricción.
- Un error de configuración en Render se ve en los logs de arranque, no en tiempo de ejecución.
