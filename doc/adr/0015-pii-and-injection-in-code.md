# 0015. PII e inyección detectadas por código

## Contexto
Pedirle a un modelo que no revele datos personales o que ignore instrucciones maliciosas no es una garantía: el
mismo modelo puede ser engañado. Los datos personales no deben llegar a ningún modelo, log ni traza.

## Decisión
`app/pii.py` detecta con expresiones regulares correo, teléfono, CURP, RFC y tarjeta, y los reemplaza por marcadores
antes de cualquier modelo, log o traza, y otra vez en la respuesta. `app/guard.py` bloquea con una lista fija de frases
(sin distinguir mayúsculas ni acentos) antes del clasificador, sin llamar a ningún modelo. La auditoría registra solo
el tipo de PII y la frase que coincidió, nunca el valor ni la pregunta. Además, `directory.py` devuelve una lista blanca
de campos públicos, así que `phone` y `rfc` nunca llegan al modelo.

## Consecuencias
- Es determinista, barato y se prueba: ampliar la lista o un patrón es una línea y una prueba.
- Las regex pueden fallar con formatos raros; el orden de patrones y las pruebas por tipo limitan ese riesgo.
- La lista de frases no cubre todas las inyecciones: es una barrera previa, junto con el mínimo privilegio de datos.
- Un bloqueo no cuesta nada y no consume modelo.
