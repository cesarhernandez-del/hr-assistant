# 0003. Bucle del agente con tope

## Contexto
Un modelo podría pedir herramientas sin parar, con costo y latencia sin límite.

## Decisión
El agente da como máximo `AGENT_MAX_STEPS` vueltas (por omisión 3, mínimo 1). Si no hay respuesta al llegar al tope, devuelve el mensaje fijo `No pude completar la respuesta. Intenta con una pregunta más concreta.`

## Consecuencias
- El costo y el tiempo por petición tienen un máximo conocido.
- Preguntas que necesiten más vueltas fallan con un mensaje claro; el tope se ajusta por configuración.
