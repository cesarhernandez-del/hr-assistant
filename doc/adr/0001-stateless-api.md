# 0001. API sin estado

## Contexto
El HR Assistant debe poder escalar corriendo más copias del mismo proceso.

## Decisión
La API no guarda nada entre peticiones. El historial lo guarda el navegador y se envía en cada `POST /ask` como `history`. Las dependencias se inyectan en `create_app()`.

## Consecuencias
- Escalar horizontalmente es trivial; cualquier copia puede atender cualquier petición.
- Cada petición es más grande, porque lleva el historial.
- Hay que validar el historial que manda el cliente, porque no es de confianza.
