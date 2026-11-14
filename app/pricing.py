"""Precios por modelo y costo de una llamada."""

import json
from pathlib import Path
from typing import Dict


class PricingError(ValueError):
    """El archivo de precios es inválido o falta el precio de un modelo."""


class Prices:
    """Tabla de precios en USD por millón de tokens.

    :param models: Precio ``input`` y ``output`` de cada modelo.
    :type models: dict
    """

    def __init__(self, models: Dict[str, Dict[str, float]]):
        self._models = models

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calcula el costo en USD de una llamada.

        :param model: Nombre del modelo.
        :type model: str
        :param input_tokens: Tokens de entrada.
        :type input_tokens: int
        :param output_tokens: Tokens de salida.
        :type output_tokens: int
        :return: Costo en USD.
        :rtype: float
        :raises PricingError: Si el modelo no tiene precio.
        """
        price = self._models.get(model)
        if price is None:
            raise PricingError(f"no price for model {model!r}")
        return (
            input_tokens * price["input"] + output_tokens * price["output"]
        ) / 1_000_000


def load_prices(path) -> Prices:
    """Lee el archivo de precios.

    :param path: Ruta del archivo JSON.
    :type path: str or Path
    :return: Tabla de precios.
    :rtype: Prices
    :raises PricingError: Si no se puede leer o tiene mal formato.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        models = {
            str(name): {"input": float(p["input"]), "output": float(p["output"])}
            for name, p in data["models"].items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise PricingError(f"invalid price file {path}") from error
    return Prices(models)
