"""Lectura de config.json (ubicado junto al ejecutable). Nunca hay credenciales en el código."""
import json
import os
from dataclasses import dataclass

from core.errors import ConfigError
from core.paths import ruta_externa

NOMBRE_ARCHIVO = "config.json"
_OBLIGATORIAS = ("host", "user", "password", "database")


@dataclass(frozen=True)
class DBConfig:
    host: str
    user: str
    password: str
    database: str
    port: int = 3306


def cargar_config(ruta: str | None = None) -> DBConfig:
    ruta = ruta or ruta_externa(NOMBRE_ARCHIVO)
    if not os.path.isfile(ruta):
        raise ConfigError(
            f"No se encontró el archivo de configuración:\n  {ruta}\n"
            f"Cree '{NOMBRE_ARCHIVO}' junto al programa (vea config.json.example)."
        )
    try:
        with open(ruta, "r", encoding="utf-8-sig") as f:
            datos = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"'{NOMBRE_ARCHIVO}' no es un JSON válido: {e}") from e
    except OSError as e:
        raise ConfigError(f"No se pudo leer '{ruta}': {e}") from e

    if not isinstance(datos, dict):
        raise ConfigError(f"'{NOMBRE_ARCHIVO}' debe contener un objeto JSON.")
    faltan = [k for k in _OBLIGATORIAS if k not in datos]
    if faltan:
        raise ConfigError(f"Faltan claves en '{NOMBRE_ARCHIVO}': {', '.join(faltan)}")
    try:
        puerto = int(datos.get("port", 3306))
    except (TypeError, ValueError) as e:
        raise ConfigError("'port' debe ser un número entero.") from e

    return DBConfig(
        host=str(datos["host"]),
        user=str(datos["user"]),
        password=str(datos["password"]),
        database=str(datos["database"]),
        port=puerto,
    )


def guardar_config(config: DBConfig, ruta: str | None = None) -> str:
    """Escribe config.json junto al ejecutable y devuelve la ruta usada."""
    ruta = ruta or ruta_externa(NOMBRE_ARCHIVO)
    datos = {
        "host": config.host, "port": config.port, "user": config.user,
        "password": config.password, "database": config.database,
    }
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
    except OSError as e:
        raise ConfigError(f"No se pudo guardar '{ruta}': {e}") from e
    return ruta
