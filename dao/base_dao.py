"""Clase base de los DAO: ejecución parametrizada y traducción de errores de MySQL."""
from typing import Any, Callable, Optional, Sequence

import mysql.connector

from core.database import Database
from core.errors import DAOError, traducir_error_mysql


class BaseDAO:
    def __init__(self, db: Database):
        self._db = db

    # ------------------------------------------------------------------ lectura
    def _consultar(self, sql: str, params: Optional[Sequence[Any]] = None, contexto: str = "") -> list[dict]:
        """SELECT parametrizado. Devuelve lista de dicts."""
        try:
            cur = self._db.connection().cursor(dictionary=True)
            try:
                cur.execute(sql, params) if params else cur.execute(sql)
                return cur.fetchall()
            finally:
                cur.close()
        except mysql.connector.Error as err:
            raise traducir_error_mysql(err, contexto) from err

    def _consultar_uno(self, sql: str, params: Optional[Sequence[Any]] = None, contexto: str = "") -> Optional[dict]:
        filas = self._consultar(sql, params, contexto)
        return filas[0] if filas else None

    # ---------------------------------------------------------------- escritura
    def _ejecutar(self, sql: str, params: Optional[Sequence[Any]] = None, contexto: str = "") -> int:
        """INSERT/UPDATE/DELETE de una sola sentencia (atómica por sí misma). Devuelve filas afectadas."""
        try:
            cur = self._db.connection().cursor()
            try:
                cur.execute(sql, params) if params else cur.execute(sql)
                return cur.rowcount
            finally:
                cur.close()
        except mysql.connector.Error as err:
            raise traducir_error_mysql(err, contexto) from err

    def _en_transaccion(self, trabajo: Callable[[Any], Any], contexto: str = "") -> Any:
        """Ejecuta trabajo(cursor) dentro de start_transaction/commit con rollback ante cualquier fallo."""
        conn = self._db.connection()
        cur = None
        try:
            conn.start_transaction()
            cur = conn.cursor(dictionary=True, buffered=True)
            resultado = trabajo(cur)
            conn.commit()
            return resultado
        except mysql.connector.Error as err:
            self._rollback_seguro(conn)
            raise traducir_error_mysql(err, contexto) from err
        except BaseException:
            self._rollback_seguro(conn)
            raise
        finally:
            if cur is not None:
                try:
                    cur.close()
                except mysql.connector.Error:
                    pass

    @staticmethod
    def _rollback_seguro(conn) -> None:
        try:
            conn.rollback()
        except mysql.connector.Error:
            # Si la conexión ya murió, el servidor descarta la transacción por sí solo.
            pass

    @staticmethod
    def _exigir_afectadas(filas: int, mensaje: str) -> None:
        if filas == 0:
            raise DAOError(mensaje)
