# 0012. Límite de peticiones en el proceso, con reloj inyectado

## Contexto
Cada pregunta al modelo cuesta, y un cliente con errores o abusivo puede agotar la cuota. La API es sin estado
(ADR 0001) y se publica como una sola instancia gratuita.

## Decisión
`RateLimiter` guarda en memoria las marcas de tiempo por cliente y aplica una ventana deslizante de 60 segundos
contra `RATE_LIMIT_PER_MINUTE`. Se evalúa después de autenticar, de modo que una clave inválida no gasta cupo.
Al exceder, responde 429 con `Retry-After` en segundos. El reloj es el inyectado (`clock.py`), no el del sistema.

## Consecuencias
- Las pruebas son deterministas: se avanza un reloj falso, sin esperas.
- El límite es por proceso, igual que las métricas; con varias instancias el límite efectivo se multiplica.
  Pasar a varias instancias exigiría un almacén compartido y un nuevo ADR.
- La memoria crece con los clientes configurados, que son pocos; las marcas viejas se descartan al consultar.
- El estado vive en el limitador de la aplicación, no en una variable global (cada `create_app()` tiene el suyo).
