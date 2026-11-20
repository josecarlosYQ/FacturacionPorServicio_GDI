"""DAO de catálogos de solo lectura: moneda, forma_pago, detraccion, empresa y ubicación geográfica."""
from typing import Optional

from dao.base_dao import BaseDAO


class CatalogoDAO(BaseDAO):

    def listar_monedas(self) -> list[dict]:
        return self._consultar(
            "SELECT id_moneda, descripcion FROM moneda ORDER BY id_moneda",
            contexto="No se pudo listar las monedas",
        )

    def listar_formas_pago(self) -> list[dict]:
        return self._consultar(
            "SELECT id_forma_pago, descripcion FROM forma_pago ORDER BY id_forma_pago",
            contexto="No se pudo listar las formas de pago",
        )

    def listar_detracciones(self) -> list[dict]:
        return self._consultar(
            "SELECT id_detraccion, detraccion_porcentaje, servicio_detraccion "
            "FROM detraccion ORDER BY id_detraccion",
            contexto="No se pudo listar las detracciones",
        )

    def obtener_detraccion(self, id_detraccion: int) -> Optional[dict]:
        return self._consultar_uno(
            "SELECT id_detraccion, detraccion_porcentaje, servicio_detraccion "
            "FROM detraccion WHERE id_detraccion = %s",
            (id_detraccion,),
            "No se pudo consultar la detracción",
        )

    def listar_empresas(self) -> list[dict]:
        return self._consultar(
            "SELECT ruc_empresa, razon_social_empresa, direccion_empresa FROM empresa ORDER BY razon_social_empresa",
            contexto="No se pudo listar las empresas emisoras",
        )

    def listar_distritos(self) -> list[dict]:
        return self._consultar(
            """
            SELECT di.id_distrito, di.nombre AS distrito, p.nombre AS provincia, dep.nombre AS departamento
            FROM distrito di
            JOIN provincia p      ON p.id_provincia = di.id_provincia
            JOIN departamento dep ON dep.id_departamento = p.id_departamento
            ORDER BY dep.nombre, p.nombre, di.nombre
            """,
            contexto="No se pudo listar los distritos",
        )

    # ------------------------------------------------------------- ubigeo en cascada
    def listar_departamentos(self) -> list[dict]:
        return self._consultar(
            "SELECT id_departamento, nombre FROM departamento ORDER BY nombre",
            contexto="No se pudo listar los departamentos",
        )

    def listar_provincias(self, id_departamento: int) -> list[dict]:
        return self._consultar(
            "SELECT id_provincia, nombre FROM provincia WHERE id_departamento = %s ORDER BY nombre",
            (id_departamento,), "No se pudo listar las provincias",
        )

    def listar_distritos_de(self, id_provincia: int) -> list[dict]:
        return self._consultar(
            "SELECT id_distrito, nombre FROM distrito WHERE id_provincia = %s ORDER BY nombre",
            (id_provincia,), "No se pudo listar los distritos",
        )

    def ubicacion_de_distrito(self, id_distrito: int) -> Optional[dict]:
        """Devuelve ids de distrito, provincia y departamento (para preseleccionar los combos)."""
        return self._consultar_uno(
            "SELECT di.id_distrito, p.id_provincia, p.id_departamento "
            "FROM distrito di JOIN provincia p ON p.id_provincia = di.id_provincia "
            "WHERE di.id_distrito = %s",
            (id_distrito,), "No se pudo consultar la ubicación",
        )
