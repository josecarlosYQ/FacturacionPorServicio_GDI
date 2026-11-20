"""Excepciones propias y traducción de errores de MySQL a mensajes para el usuario."""
import mysql.connector


class FacturacionError(Exception):
    """Base de los errores controlados de la aplicación."""


class ConfigError(FacturacionError):
    """config.json ausente, ilegible o incompleto."""


class ValidationError(FacturacionError):
    """Datos de entrada inválidos (detectados antes de tocar la base de datos)."""


class DAOError(FacturacionError):
    """Fallo de acceso a datos con mensaje apto para el usuario final."""

    def __init__(self, mensaje: str, errno: int | None = None):
        super().__init__(mensaje)
        self.errno = errno


def traducir_error_mysql(err: mysql.connector.Error, contexto: str = "") -> DAOError:
    """Convierte un mysql.connector.Error en un DAOError con texto claro."""
    errno = getattr(err, "errno", None)
    prefijo = f"{contexto}: " if contexto else ""
    detalle = (getattr(err, "msg", None) or str(err))

    if errno == 1062:
        msg = "ya existe un registro con esa clave."
    elif errno == 1451:
        msg = "no se puede eliminar/modificar porque tiene registros relacionados."
    elif errno == 1452:
        msg = "hace referencia a un dato que no existe (cliente, servicio, distrito, moneda, etc.)."
    elif errno == 3819:
        msg = f"un dato no cumple las restricciones de la base de datos ({detalle})."
    elif errno in (1264, 1366, 1406):
        msg = f"un valor está fuera del rango o formato permitido ({detalle})."
    elif errno in (2003, 2006, 2013, 2055):
        msg = "se perdió la conexión con el servidor MySQL."
    else:
        msg = f"error de base de datos ({errno}): {detalle}"
    return DAOError(prefijo + msg, errno)
