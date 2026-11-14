# 0011. Una clave por cliente, con falla cerrada

## Contexto
La API se publica en internet y cuesta dinero por cada pregunta. Hace falta saber quién pregunta, poder
revocar a un cliente sin afectar a otros y no filtrar nunca una clave.

## Decisión
`API_KEYS` (`cliente:clave,...`) se parsea al arrancar a un mapa cliente a clave. `POST /ask` y `GET /metrics`
exigen `X-API-Key`; se compara con `hmac.compare_digest`. El nombre del cliente viaja en el contexto de la
petición y entra al log, la auditoría y la traza. La clave nunca se registra. Si `API_KEYS` está mal formada, el
proceso no arranca y el error dice la entrada y su largo, no su valor. Sin claves configuradas, los puntos
protegidos responden 401.

## Consecuencias
- Se puede atribuir costo y uso a cada cliente y revocar una clave cambiando una variable.
- Rotar una clave exige reiniciar el servicio; es aceptable en esta escala.
- Las pruebas de sesiones anteriores deben mandar clave.
- Las claves viven en el entorno y no hay base de datos de claves.
