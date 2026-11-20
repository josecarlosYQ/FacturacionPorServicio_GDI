"""Instalación de la base de datos: ejecuta el script SQL completo desde Python.

El script usa DELIMITER (comando del cliente mysql, no de MySQL), por eso no se puede pasar
tal cual a mysql-connector: aquí se divide en sentencias respetando los cambios de delimitador.
El script es idempotente (CREATE IF NOT EXISTS + INSERT IGNORE), de modo que ejecutarlo sobre
una base ya instalada no borra ni duplica datos.
"""
import logging
import os
import re

import mysql.connector
from mysql.connector.constants import ClientFlag

from core.config import DBConfig
from core.errors import ConfigError, DAOError, traducir_error_mysql
from core.paths import ruta_recurso

log = logging.getLogger("facturacion.setup")
NOMBRE_SCRIPT = "script_facturacion_servicios.sql"
BD_POR_DEFECTO = "facturacion_servicios"
TABLAS_MAESTRAS = ("moneda", "forma_pago", "detraccion", "departamento", "provincia", "distrito")


def ruta_script() -> str:
    ruta = ruta_recurso("sql", NOMBRE_SCRIPT)
    if not os.path.isfile(ruta):
        raise ConfigError(f"No se encontró el script SQL:\n  {ruta}")
    return ruta


def leer_script() -> str:
    with open(ruta_script(), "r", encoding="utf-8-sig") as f:
        return f.read()


def nombre_bd_del_script(texto: str) -> str:
    m = re.search(r"CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", texto, re.IGNORECASE)
    return m.group(1) if m else BD_POR_DEFECTO


def dividir_sentencias(texto: str) -> list[str]:
    """Divide el script en sentencias, interpretando 'DELIMITER x' y quitando comentarios de línea."""
    delimitador = ";"
    sentencias, buffer = [], []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not buffer and (not limpia or limpia.startswith("--")):
            continue
        if not buffer and limpia.upper().startswith("DELIMITER "):
            delimitador = limpia.split(None, 1)[1].strip()
            continue
        if limpia.startswith("--"):
            continue
        buffer.append(linea)
        if limpia.endswith(delimitador):
            sentencia = "\n".join(buffer).strip()
            sentencia = sentencia[: -len(delimitador)].strip()
            if sentencia:
                sentencias.append(sentencia)
            buffer = []
    resto = "\n".join(buffer).strip()
    if resto:
        sentencias.append(resto)
    return sentencias


def _conectar(config: DBConfig, con_bd: bool):
    kwargs = dict(
        host=config.host, port=config.port, user=config.user, password=config.password,
        charset="utf8mb4", autocommit=True, connection_timeout=10, use_pure=True,
        client_flags=[ClientFlag.FOUND_ROWS],
    )
    if con_bd:
        kwargs["database"] = config.database
    return mysql.connector.connect(**kwargs)


def probar_conexion(config: DBConfig, con_bd: bool = True) -> None:
    """Abre y cierra una conexión. Lanza DAOError (mensaje claro) si falla."""
    try:
        _conectar(config, con_bd).close()
    except mysql.connector.Error as err:
        raise traducir_error_mysql(err, "No se pudo conectar a MySQL") from err


def instalar_base_datos(config: DBConfig, progreso=None) -> str:
    """Conecta SIN base de datos, ejecuta el script completo y devuelve el nombre de la BD creada."""
    texto = leer_script()
    nombre_bd = nombre_bd_del_script(texto)
    sentencias = dividir_sentencias(texto)
    conn = None
    try:
        conn = _conectar(config, con_bd=False)
        cur = conn.cursor()
        for i, sql in enumerate(sentencias, 1):
            try:
                cur.execute(sql)
                while cur.nextset():
                    pass
            except mysql.connector.Error as err:
                log.error("Falló la sentencia %d del script: %s", i, sql[:120])
                raise traducir_error_mysql(err, f"Error al ejecutar el script SQL (sentencia {i})") from err
            if progreso:
                progreso(i, len(sentencias))
        cur.close()
    except mysql.connector.Error as err:
        raise traducir_error_mysql(err, "No se pudo conectar a MySQL") from err
    finally:
        if conn is not None:
            try:
                conn.close()
            except mysql.connector.Error:
                pass
    log.info("Base de datos '%s' instalada/actualizada (%d sentencias)", nombre_bd, len(sentencias))
    return nombre_bd


def catalogos_completos(config: DBConfig) -> bool:
    """True si la BD existe, tiene todas las tablas y los catálogos maestros no están vacíos."""
    try:
        conn = _conectar(config, con_bd=True)
    except mysql.connector.Error:
        return False
    try:
        cur = conn.cursor()
        for t in TABLAS_MAESTRAS + ("empresa", "cliente", "servicio", "factura", "detalle_factura"):
            cur.execute(f"SELECT COUNT(*) FROM {t}")  # nombres fijos de la lista de arriba
            n = cur.fetchone()[0]
            if t in TABLAS_MAESTRAS and n == 0:
                return False
        return True
    except mysql.connector.Error:
        return False
    finally:
        conn.close()
