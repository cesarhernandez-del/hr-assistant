"""Errores compartidos entre los módulos de configuración y autenticación."""


class ConfigError(ValueError):
    """Error de configuración: un valor inválido impide arrancar."""
