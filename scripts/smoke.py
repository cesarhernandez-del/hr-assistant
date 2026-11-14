"""Prueba de humo contra un despliegue: ``python scripts/smoke.py <url>``.

La clave se lee de la variable ``SMOKE_API_KEY``, nunca de un argumento.
"""

import os
import sys

import httpx

TIMEOUT_SECONDS = 30


def check(name: str, ok: bool) -> bool:
    """Imprime [OK] o [FAIL] para una comprobacion y devuelve el resultado."""
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    return ok


def smoke(url: str, api_key: str, client: httpx.Client) -> bool:
    """Hace las tres comprobaciones con el cliente dado; True si todas pasan."""
    base = url.rstrip("/")
    body = {"question": "How many employees are in engineering?", "history": []}
    health = client.get(f"{base}/health").status_code
    no_key = client.post(f"{base}/ask", json=body).status_code
    with_key = client.post(
        f"{base}/ask", json=body, headers={"X-API-Key": api_key}
    ).status_code
    results = [
        check(f"/health responde 200 (recibido {health})", health == 200),
        check(f"/ask sin clave responde 401 (recibido {no_key})", no_key == 401),
        check(f"/ask con clave responde 200 (recibido {with_key})", with_key == 200),
    ]
    return all(results)


def main(args: list[str]) -> int:
    """Punto de entrada: devuelve 0 si todo pasa y distinto de 0 si algo falla."""
    if len(args) != 1:
        print("Uso: SMOKE_API_KEY=... python scripts/smoke.py <url>")
        return 2
    api_key = os.environ.get("SMOKE_API_KEY", "")
    if not api_key:
        print("[FAIL] falta la variable SMOKE_API_KEY")
        return 2
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            return 0 if smoke(args[0], api_key, client) else 1
    except httpx.HTTPError as error:
        print(f"[FAIL] no se pudo conectar: {type(error).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
