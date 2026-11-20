"""DAO de reportes: implementa las consultas analíticas del script SQL (3, 4, 5, 6, 7, 8 y 10).

Nota sobre monedas: la columna `total` de cada factura está en SU moneda (Soles o Dólares).
Sumar importes de monedas distintas mezcla unidades, por eso los reportes que acumulan importes
(por cliente, servicios, por mes) aceptan un filtro opcional `id_moneda`. Sin filtro se comportan
exactamente como las consultas del script.
"""
from datetime import date
from typing import Optional

from core.validators import validar_entero_rango, validar_rango_fechas
from dao.base_dao import BaseDAO


class ReporteDAO(BaseDAO):

    @staticmethod
    def _moneda(id_moneda: Optional[int]) -> Optional[int]:
        return None if id_moneda is None else validar_entero_rango(id_moneda, "moneda", 1, 255)

    # ---- Consulta 3
    def total_facturado_por_cliente(self, id_moneda: Optional[int] = None) -> list[dict]:
        id_moneda = self._moneda(id_moneda)
        # El filtro va en el ON (no en WHERE) para conservar clientes sin facturas (LEFT JOIN).
        extra = " AND f.id_moneda = %s" if id_moneda is not None else ""
        return self._consultar(
            f"""
            SELECT c.ruc_cliente, c.nombre_cliente,
                   COUNT(f.numero_factura) AS cantidad_facturas,
                   COALESCE(SUM(f.total), 0) AS total_facturado
            FROM cliente c
            LEFT JOIN factura f ON f.ruc_cliente = c.ruc_cliente{extra}
            GROUP BY c.ruc_cliente, c.nombre_cliente
            ORDER BY total_facturado DESC, c.nombre_cliente
            """,
            (id_moneda,) if id_moneda is not None else None,
            "No se pudo generar el total facturado por cliente",
        )

    # ---- Consulta 4
    def servicios_mas_solicitados(self, limite: Optional[int] = None, id_moneda: Optional[int] = None) -> list[dict]:
        id_moneda = self._moneda(id_moneda)
        params: list = []
        sql = """
            SELECT s.codigo_servicio, s.descripcion_servicio,
                   SUM(df.cantidad) AS unidades_solicitadas,
                   SUM(df.valor_venta) AS importe_vendido
            FROM servicio s
            JOIN detalle_factura df ON df.codigo_servicio = s.codigo_servicio
            JOIN factura f          ON f.numero_factura   = df.numero_factura
        """
        if id_moneda is not None:
            sql += " WHERE f.id_moneda = %s"
            params.append(id_moneda)
        sql += " GROUP BY s.codigo_servicio, s.descripcion_servicio ORDER BY importe_vendido DESC"
        if limite is not None:
            sql += " LIMIT %s"
            params.append(validar_entero_rango(limite, "límite", 1, 1000))
        return self._consultar(sql, params or None, "No se pudo generar el ranking de servicios")

    # ---- Consulta 5
    def ventas_por_rango_fechas(self, desde: date, hasta: date) -> list[dict]:
        validar_rango_fechas(desde, hasta)
        return self._consultar(
            """
            SELECT f.numero_factura, f.fecha_emision, c.nombre_cliente, m.descripcion AS moneda,
                   f.subtotal, f.igv_calculado, f.total
            FROM factura f
            JOIN cliente c ON c.ruc_cliente = f.ruc_cliente
            JOIN moneda m  ON m.id_moneda   = f.id_moneda
            WHERE f.fecha_emision BETWEEN %s AND %s
            ORDER BY f.fecha_emision, f.numero_factura
            """,
            (desde, hasta),
            "No se pudo consultar las ventas por rango de fechas",
        )

    # ---- Consulta 6
    def facturas_con_detraccion(self, solo_con_monto: bool = False) -> list[dict]:
        """Facturas con detracción asociada. solo_con_monto=True excluye las de 0 % ('No aplica')."""
        sql = """
            SELECT f.numero_factura, c.nombre_cliente, d.servicio_detraccion,
                   d.detraccion_porcentaje, f.total, f.monto_detraccion,
                   (f.total - f.monto_detraccion) AS neto_referencial
            FROM factura f
            JOIN cliente c    ON c.ruc_cliente    = f.ruc_cliente
            JOIN detraccion d ON d.id_detraccion  = f.id_detraccion
        """
        if solo_con_monto:
            sql += " WHERE f.monto_detraccion > 0"
        sql += " ORDER BY f.fecha_emision, f.numero_factura"
        return self._consultar(sql, contexto="No se pudo consultar las facturas con detracción")

    # ---- Consulta 7
    def resumen_por_moneda(self) -> list[dict]:
        return self._consultar(
            """
            SELECT m.descripcion AS moneda, COUNT(*) AS cantidad_facturas,
                   SUM(f.subtotal) AS subtotal_acumulado,
                   SUM(f.igv_calculado) AS igv_acumulado,
                   SUM(f.total) AS total_acumulado
            FROM factura f
            JOIN moneda m ON m.id_moneda = f.id_moneda
            GROUP BY m.id_moneda, m.descripcion
            ORDER BY m.id_moneda
            """,
            contexto="No se pudo generar el resumen por moneda",
        )

    # ---- Consulta 8
    def resumen_por_forma_pago(self) -> list[dict]:
        """Total por forma de pago, separado por moneda para no mezclar Soles con Dólares."""
        return self._consultar(
            """
            SELECT fp.descripcion AS forma_pago, m.descripcion AS moneda,
                   COUNT(*) AS cantidad_facturas, SUM(f.total) AS total_facturado
            FROM factura f
            JOIN forma_pago fp ON fp.id_forma_pago = f.id_forma_pago
            JOIN moneda m      ON m.id_moneda      = f.id_moneda
            GROUP BY fp.id_forma_pago, fp.descripcion, m.id_moneda, m.descripcion
            ORDER BY fp.id_forma_pago, m.id_moneda
            """,
            contexto="No se pudo generar el resumen por forma de pago",
        )

    # ---- Consulta 10
    def ventas_e_igv_por_mes(self, id_moneda: Optional[int] = None) -> list[dict]:
        id_moneda = self._moneda(id_moneda)
        donde = " WHERE id_moneda = %s" if id_moneda is not None else ""
        # CONCAT/LPAD en lugar de DATE_FORMAT('%Y-%m'): evita escapar '%' en consultas con parámetros.
        return self._consultar(
            f"""
            SELECT CONCAT(YEAR(fecha_emision), '-', LPAD(MONTH(fecha_emision), 2, '0')) AS periodo,
                   COUNT(*) AS cantidad_facturas,
                   SUM(subtotal) AS subtotal,
                   SUM(igv_calculado) AS igv,
                   SUM(total) AS total_ventas
            FROM factura{donde}
            GROUP BY periodo
            ORDER BY periodo
            """,
            (id_moneda,) if id_moneda is not None else None,
            "No se pudo generar el reporte mensual",
        )
