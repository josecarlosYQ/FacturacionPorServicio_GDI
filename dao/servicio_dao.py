"""DAO de servicios (catálogo). En este esquema el 'producto' facturable es la tabla `servicio`."""
from decimal import Decimal
from typing import Optional

from core.models import Servicio
from core.utils import a_decimal
from core.validators import validar_entero_rango, validar_importe_positivo, validar_texto
from dao.base_dao import BaseDAO

MAX_CODIGO = 255  # TINYINT UNSIGNED


class ServicioDAO(BaseDAO):

    @staticmethod
    def _validar(s: Servicio) -> Servicio:
        valor = validar_importe_positivo(a_decimal(s.valor_unitario_servicio, "valor unitario"), "valor unitario")
        return Servicio(
            codigo_servicio=validar_entero_rango(s.codigo_servicio, "código de servicio", 1, MAX_CODIGO),
            descripcion_servicio=validar_texto(s.descripcion_servicio, "descripción", 100),
            valor_unitario_servicio=valor,
        )

    def siguiente_codigo(self) -> int:
        """El código no es AUTO_INCREMENT en el esquema: se propone MAX + 1."""
        fila = self._consultar_uno(
            "SELECT COALESCE(MAX(codigo_servicio), 0) + 1 AS siguiente FROM servicio",
            contexto="No se pudo calcular el siguiente código",
        )
        return int(fila["siguiente"])

    def crear(self, servicio: Servicio) -> None:
        s = self._validar(servicio)
        self._ejecutar(
            "INSERT INTO servicio (codigo_servicio, descripcion_servicio, valor_unitario_servicio) "
            "VALUES (%s, %s, %s)",
            (s.codigo_servicio, s.descripcion_servicio, s.valor_unitario_servicio),
            "No se pudo registrar el servicio",
        )

    def obtener(self, codigo_servicio: int) -> Optional[dict]:
        codigo = validar_entero_rango(codigo_servicio, "código de servicio", 1, MAX_CODIGO)
        return self._consultar_uno(
            "SELECT codigo_servicio, descripcion_servicio, valor_unitario_servicio "
            "FROM servicio WHERE codigo_servicio = %s",
            (codigo,),
            "No se pudo consultar el servicio",
        )

    def listar(self) -> list[dict]:
        return self._consultar(
            "SELECT codigo_servicio, descripcion_servicio, valor_unitario_servicio "
            "FROM servicio ORDER BY codigo_servicio",
            contexto="No se pudo listar los servicios",
        )

    def actualizar(self, servicio: Servicio) -> None:
        """Cambiar el valor unitario NO altera facturas ya emitidas (guardan precio_unitario_aplicado)."""
        s = self._validar(servicio)
        filas = self._ejecutar(
            "UPDATE servicio SET descripcion_servicio = %s, valor_unitario_servicio = %s "
            "WHERE codigo_servicio = %s",
            (s.descripcion_servicio, s.valor_unitario_servicio, s.codigo_servicio),
            "No se pudo actualizar el servicio",
        )
        self._exigir_afectadas(filas, f"No existe el servicio con código {s.codigo_servicio}.")

    def eliminar(self, codigo_servicio: int) -> None:
        codigo = validar_entero_rango(codigo_servicio, "código de servicio", 1, MAX_CODIGO)
        filas = self._ejecutar(
            "DELETE FROM servicio WHERE codigo_servicio = %s", (codigo,), "No se pudo eliminar el servicio"
        )
        self._exigir_afectadas(filas, f"No existe el servicio con código {codigo}.")
