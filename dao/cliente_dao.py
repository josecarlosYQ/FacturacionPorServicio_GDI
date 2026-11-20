"""DAO de clientes: CRUD y consulta por distrito (con provincia y departamento)."""
from typing import Optional

from core.errors import DAOError
from core.models import Cliente
from core.validators import validar_entero_rango, validar_ruc, validar_texto
from dao.base_dao import BaseDAO

_BASE_SELECT = """
    SELECT c.ruc_cliente, c.nombre_cliente, c.direccion_cliente, c.id_distrito,
           di.nombre AS distrito, p.nombre AS provincia, dep.nombre AS departamento
    FROM cliente c
    JOIN distrito di      ON di.id_distrito = c.id_distrito
    JOIN provincia p      ON p.id_provincia = di.id_provincia
    JOIN departamento dep ON dep.id_departamento = p.id_departamento
"""


class ClienteDAO(BaseDAO):

    @staticmethod
    def _validar(c: Cliente) -> Cliente:
        return Cliente(
            ruc_cliente=validar_ruc(c.ruc_cliente, "RUC del cliente"),
            nombre_cliente=validar_texto(c.nombre_cliente, "nombre del cliente", 50),
            direccion_cliente=validar_texto(c.direccion_cliente, "dirección", 50),
            id_distrito=validar_entero_rango(c.id_distrito, "id_distrito", 1, 65535),
        )

    # ------------------------------------------------------------------ CREATE
    def crear(self, cliente: Cliente) -> None:
        c = self._validar(cliente)
        self._ejecutar(
            "INSERT INTO cliente (ruc_cliente, nombre_cliente, direccion_cliente, id_distrito) "
            "VALUES (%s, %s, %s, %s)",
            (c.ruc_cliente, c.nombre_cliente, c.direccion_cliente, c.id_distrito),
            "No se pudo registrar el cliente",
        )

    # -------------------------------------------------------------------- READ
    def obtener(self, ruc_cliente: str) -> Optional[dict]:
        ruc = validar_ruc(ruc_cliente, "RUC del cliente")
        return self._consultar_uno(
            _BASE_SELECT + " WHERE c.ruc_cliente = %s", (ruc,), "No se pudo consultar el cliente"
        )

    def listar(self, texto: Optional[str] = None) -> list[dict]:
        """Lista todos los clientes; si hay texto filtra por nombre o RUC (parcial)."""
        if texto and texto.strip():
            patron = f"%{texto.strip()}%"
            return self._consultar(
                _BASE_SELECT + " WHERE c.nombre_cliente LIKE %s OR c.ruc_cliente LIKE %s ORDER BY c.nombre_cliente",
                (patron, patron),
                "No se pudo listar los clientes",
            )
        return self._consultar(_BASE_SELECT + " ORDER BY c.nombre_cliente", contexto="No se pudo listar los clientes")

    def listar_por_distrito(self, nombre_distrito: str) -> list[dict]:
        """Consulta 9 del script: clientes de un distrito con provincia y departamento."""
        nombre = validar_texto(nombre_distrito, "distrito", 30)
        return self._consultar(
            _BASE_SELECT + " WHERE di.nombre = %s ORDER BY c.nombre_cliente",
            (nombre,),
            "No se pudo consultar clientes por distrito",
        )

    # ------------------------------------------------------------------ UPDATE
    def actualizar(self, cliente: Cliente) -> None:
        c = self._validar(cliente)
        filas = self._ejecutar(
            "UPDATE cliente SET nombre_cliente = %s, direccion_cliente = %s, id_distrito = %s "
            "WHERE ruc_cliente = %s",
            (c.nombre_cliente, c.direccion_cliente, c.id_distrito, c.ruc_cliente),
            "No se pudo actualizar el cliente",
        )
        self._exigir_afectadas(filas, f"No existe un cliente con RUC {c.ruc_cliente}.")

    # ------------------------------------------------------------------ DELETE
    def eliminar(self, ruc_cliente: str) -> None:
        ruc = validar_ruc(ruc_cliente, "RUC del cliente")
        filas = self._ejecutar(
            "DELETE FROM cliente WHERE ruc_cliente = %s", (ruc,), "No se pudo eliminar el cliente"
        )
        if filas == 0:
            raise DAOError(f"No existe un cliente con RUC {ruc}.")
