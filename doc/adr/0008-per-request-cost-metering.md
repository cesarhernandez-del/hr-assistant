# 0008. Costo medido por petición con un modelo de vida corta

## Contexto
El costo depende del modelo elegido y de los tokens de cada llamada. Los contadores acumulados del modelo de la
sesión 1 son del proceso y, con peticiones concurrentes, mezclarían tokens y costos entre peticiones. El modelo
simulado también debe tener precio para medir sin red.

## Decisión
El backend (`fake` o `gateway`) no guarda contadores: `complete(model, messages)` devuelve texto, tokens y si fue
cacheada. Cada petición crea un `RequestModel` que fija modelo y tope de salida, acumula sus tokens y llamadas
cacheadas y expone `complete(messages)`, de modo que `agent.py` no cambia. El costo se calcula con
`data/model_prices.json` por el nombre del modelo (los simulados se llaman como `MODEL_SMALL` y `MODEL_LARGE`);
una llamada con `cf-aig-cache-status: HIT` cuesta 0. `/metrics` suma el costo del proceso.

## Consecuencias
- El costo por respuesta es correcto aunque haya peticiones simultáneas y no hay estado global nuevo.
- Las palancas se miden con el modelo simulado, sin gastar cuota.
- Un modelo sin precio es un error explícito y no un costo 0 silencioso.
- El costo acumulado de `/metrics` sigue siendo por proceso, como el resto de las métricas (ADR 0005).
