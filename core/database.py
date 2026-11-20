"""Conexión a MySQL (capa de conexión del patrón DAO)."""
import mysql.connector
from mysql.connector.constants import ClientFlag

from core.config import DBConfig
from core.errors import traducir_error_mysql


class Database:
    """Administra una única conexión reutilizable (aplicación de escritorio monousuario).

    La conexión se abre con autocommit=True: las lecturas y sentencias sueltas no dejan
    transacciones abiertas, y las operaciones compuestas usan start_transaction()
    de forma explícita (ver FacturaDAO).
    """

    def __init__(self, config: DBConfig):
        self._config = config
        self._conn = None

    def connection(self):
        """Devuelve una conexión viva, reconectando si hace falta."""
        try:
            if self._conn is None or not self._conn.is_connected():
                self._conn = mysql.connector.connect(
                    host=self._config.host,
                    port=self._config.port,
                    user=self._config.user,
                    password=self._config.password,
                    database=self._config.database,
                    charset="utf8mb4",
                    autocommit=True,
                    connection_timeout=10,
                    client_flags=[ClientFlag.FOUND_ROWS],  # rowcount = filas encontradas (aunque no cambien)
                    use_pure=True,  # Python puro: evita problemas de DLLs al empaquetar con PyInstaller
                )
            return self._conn
        except mysql.connector.Error as err:
            self._conn = None
            raise traducir_error_mysql(err, "No se pudo conectar a la base de datos") from err

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except mysql.connector.Error:
                pass
            self._conn = None
