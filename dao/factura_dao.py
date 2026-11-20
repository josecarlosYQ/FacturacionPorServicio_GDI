"""DAO de facturas.

Punto clave: `registrar()` inserta cabecera + detalles dentro de UNA transacción explícita
(start_transaction / commit / rollback). Los importes de cabecera (subtotal, IGV, total y
monto de detracción) los calculan los triggers trg_detalle_* mediante recalcular_factura(),
por eso Python NO los envía en el INSERT: solo los lee de vuelta antes del commit.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

import mysql.connector

from core.errors import DAOError, ValidationError, traducir_error_mysql
from core.models import ItemFactura, NuevaFactura
from core.utils import a_decimal
from core.validators import (
    validar_entero_rango,
    validar_importe_positivo,
    validar_numero_factura,
    validar_porcentaje,
    validar_ruc,
)
from dao.base_dao import BaseDAO

MAX_CANTIDAD = 255  # TINYINT UNSIGNED

_ESTADO_VENCIMIENTO = """
    CASE
      WHEN f.fecha_vencimiento IS NULL THEN 'Sin vencimiento'
      WHEN f.fecha_vencimiento < CURDATE() THEN 'Vencida'
      ELSE 'Pendiente de vencimiento'
    END AS estado_vencimiento
"""

# Campos de cabecera que se pueden modificar -> (columna, tipo de validación)
_CAMPOS_EDITABLES = {
    "fecha_emision": "fecha_emision",
    "fecha_vencimiento": "fecha_vencimiento",
    "igv_porcentaje": "igv_porcentaje",
    "id_detraccion": "id_detraccion",
    "id_moneda": "id_moneda",
    "id_forma_pago": "id_forma_pago",
    "ruc_cliente": "ruc_cliente",
}


class FacturaDAO(BaseDAO):

    # ================================================================ validación
    @staticmethod
    def _validar_item(item: ItemFactura) -> ItemFactura:
        precio = item.precio_unitario
        if precio is not None:
            precio = validar_importe_positivo(a_decimal(precio, "precio unitario"), "precio unitario")
        return ItemFactura(
            codigo_servicio=validar_entero_rango(item.codigo_servicio, "código de servicio", 1, 255),
            cantidad=validar_entero_rango(item.cantidad, "cantidad", 1, MAX_CANTIDAD),
            precio_unitario=precio,
        )

    @classmethod
    def _validar_nueva(cls, f: NuevaFactura) -> NuevaFactura:
        if not f.items:
            raise ValidationError("Una factura necesita al menos un ítem de detalle.")
        items = [cls._validar_item(i) for i in f.items]
        codigos = [i.codigo_servicio for i in items]
        repetidos = {c for c in codigos if codigos.count(c) > 1}
        if repetidos:
            raise ValidationError(
                f"El servicio {sorted(repetidos)} aparece más de una vez: la clave del detalle es "
                f"(servicio, factura). Sume las cantidades en una sola línea."
            )
        if f.fecha_vencimiento is not None and f.fecha_vencimiento < f.fecha_emision:
            raise ValidationError("La fecha de vencimiento no puede ser anterior a la de emisión.")
        return NuevaFactura(
            numero_factura=validar_numero_factura(f.numero_factura),
            fecha_emision=f.fecha_emision,
            id_moneda=validar_entero_rango(f.id_moneda, "moneda", 1, 255),
            id_forma_pago=validar_entero_rango(f.id_forma_pago, "forma de pago", 1, 255),
            ruc_empresa=validar_ruc(f.ruc_empresa, "RUC de la empresa"),
            ruc_cliente=validar_ruc(f.ruc_cliente, "RUC del cliente"),
            igv_porcentaje=validar_porcentaje(a_decimal(f.igv_porcentaje, "IGV"), "IGV"),
            fecha_vencimiento=f.fecha_vencimiento,
            id_detraccion=(
                None if f.id_detraccion is None
                else validar_entero_rango(f.id_detraccion, "detracción", 1, 65535)
            ),
            items=items,
        )

    # ====================================================== helpers (en transacción)
    @staticmethod
    def _precio_vigente(cur, codigo_servicio: int) -> Decimal:
        cur.execute(
            "SELECT valor_unitario_servicio FROM servicio WHERE codigo_servicio = %s", (codigo_servicio,)
        )
        fila = cur.fetchone()
        if fila is None:
            raise DAOError(f"El servicio con código {codigo_servicio} no existe.")
        return fila["valor_unitario_servicio"]

    @staticmethod
    def _insertar_detalle(cur, numero: str, item: ItemFactura) -> None:
        precio = item.precio_unitario
        if precio is None:
            precio = FacturaDAO._precio_vigente(cur, item.codigo_servicio)
        cur.execute(
            "INSERT INTO detalle_factura (codigo_servicio, numero_factura, cantidad, precio_unitario_aplicado) "
            "VALUES (%s, %s, %s, %s)",
            (item.codigo_servicio, numero, item.cantidad, precio),
        )

    @staticmethod
    def _resumen(cur, numero: str) -> dict:
        """Lee la cabecera tal como quedó tras ejecutarse los triggers."""
        cur.execute(
            "SELECT numero_factura, fecha_emision, fecha_vencimiento, igv_porcentaje, subtotal, "
            "igv_calculado, total, id_detraccion, monto_detraccion, id_moneda, id_forma_pago, "
            "ruc_empresa, ruc_cliente FROM factura WHERE numero_factura = %s",
            (numero,),
        )
        fila = cur.fetchone()
        if fila is None:
            raise DAOError(f"La factura {numero} no existe.")
        return fila

    # ===================================================================== CREATE
    def registrar(self, factura: NuevaFactura) -> dict:
        """Registra cabecera + ítems de forma ATÓMICA. Ante cualquier error hace rollback total."""
        f = self._validar_nueva(factura)
        conn = self._db.connection()
        cur = None
        paso = "cabecera"
        try:
            conn.start_transaction()
            cur = conn.cursor(dictionary=True, buffered=True)

            # 1) Cabecera: subtotal/igv/total/monto_detraccion quedan en 0.00 (los fijan los triggers)
            cur.execute(
                "INSERT INTO factura (numero_factura, igv_porcentaje, fecha_emision, fecha_vencimiento, "
                "id_detraccion, id_moneda, id_forma_pago, ruc_empresa, ruc_cliente) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    f.numero_factura, f.igv_porcentaje, f.fecha_emision, f.fecha_vencimiento,
                    f.id_detraccion, f.id_moneda, f.id_forma_pago, f.ruc_empresa, f.ruc_cliente,
                ),
            )

            # 2) Detalles: cada INSERT dispara trg_detalle_ai -> recalcular_factura()
            for item in f.items:
                paso = f"ítem del servicio {item.codigo_servicio}"
                self._insertar_detalle(cur, f.numero_factura, item)

            # 3) Totales ya recalculados por los triggers (misma transacción)
            paso = "lectura de totales"
            resumen = self._resumen(cur, f.numero_factura)

            conn.commit()
            resumen["cantidad_items"] = len(f.items)
            return resumen

        except mysql.connector.Error as err:
            self._rollback_seguro(conn)
            raise traducir_error_mysql(
                err, f"No se registró la factura {f.numero_factura} (falló {paso}; se revirtió todo)"
            ) from err
        except BaseException:
            self._rollback_seguro(conn)
            raise
        finally:
            if cur is not None:
                try:
                    cur.close()
                except mysql.connector.Error:
                    pass

    def siguiente_numero(self, serie: str = "F001") -> str:
        """Propone el siguiente correlativo de una serie (ej. F001-00000266)."""
        serie = (serie or "").strip().upper()
        if len(serie) != 4 or not serie.isalnum():
            raise ValidationError("La serie debe tener 4 caracteres alfanuméricos (ej. F001).")
        fila = self._consultar_uno(
            "SELECT COALESCE(MAX(CAST(SUBSTRING(numero_factura, 6) AS UNSIGNED)), 0) + 1 AS n "
            "FROM factura WHERE numero_factura LIKE %s",
            (f"{serie}-%",),
            "No se pudo calcular el siguiente número",
        )
        return f"{serie}-{int(fila['n']):08d}"

    # ======================================================================= READ
    def listar(self, ruc_cliente: Optional[str] = None) -> list[dict]:
        """Consulta 1 del script: facturas con cliente, emisor, importes y estado de vencimiento."""
        sql = f"""
            SELECT f.numero_factura, f.fecha_emision, f.fecha_vencimiento,
                   c.nombre_cliente, c.ruc_cliente, e.razon_social_empresa,
                   m.descripcion AS moneda,
                   f.subtotal, f.igv_calculado, f.total,
                   {_ESTADO_VENCIMIENTO}
            FROM factura f
            JOIN cliente c ON c.ruc_cliente = f.ruc_cliente
            JOIN empresa e ON e.ruc_empresa = f.ruc_empresa
            JOIN moneda  m ON m.id_moneda   = f.id_moneda
        """
        params = None
        if ruc_cliente:
            sql += " WHERE f.ruc_cliente = %s"
            params = (validar_ruc(ruc_cliente, "RUC del cliente"),)
        sql += " ORDER BY f.fecha_emision DESC, f.numero_factura DESC"
        return self._consultar(sql, params, "No se pudo listar las facturas")

    def obtener_cabecera(self, numero_factura: str) -> Optional[dict]:
        """Cabecera completa para pantalla y PDF: emisor y cliente con su ubicación, catálogos y detracción."""
        numero = validar_numero_factura(numero_factura)
        return self._consultar_uno(
            f"""
            SELECT f.numero_factura, f.fecha_emision, f.fecha_vencimiento, f.igv_porcentaje,
                   f.subtotal, f.igv_calculado, f.total,
                   f.id_detraccion, d.servicio_detraccion, d.detraccion_porcentaje, f.monto_detraccion,
                   m.descripcion AS moneda, fp.descripcion AS forma_pago,
                   e.ruc_empresa, e.razon_social_empresa, e.direccion_empresa, e.telefono_empresa,
                   e.cuenta_corriente,
                   CONCAT_WS(', ', de.nombre, pe.nombre, dpe.nombre) AS ubicacion_empresa,
                   c.ruc_cliente, c.nombre_cliente, c.direccion_cliente,
                   CONCAT_WS(', ', dc.nombre, pc.nombre, dpc.nombre) AS ubicacion_cliente,
                   {_ESTADO_VENCIMIENTO}
            FROM factura f
            JOIN empresa e     ON e.ruc_empresa     = f.ruc_empresa
            JOIN distrito de   ON de.id_distrito    = e.id_distrito
            JOIN provincia pe  ON pe.id_provincia   = de.id_provincia
            JOIN departamento dpe ON dpe.id_departamento = pe.id_departamento
            JOIN cliente c     ON c.ruc_cliente     = f.ruc_cliente
            JOIN distrito dc   ON dc.id_distrito    = c.id_distrito
            JOIN provincia pc  ON pc.id_provincia   = dc.id_provincia
            JOIN departamento dpc ON dpc.id_departamento = pc.id_departamento
            JOIN moneda m      ON m.id_moneda       = f.id_moneda
            JOIN forma_pago fp ON fp.id_forma_pago  = f.id_forma_pago
            LEFT JOIN detraccion d ON d.id_detraccion = f.id_detraccion
            WHERE f.numero_factura = %s
            """,
            (numero,),
            "No se pudo consultar la factura",
        )

    def obtener_detalle(self, numero_factura: str) -> list[dict]:
        """Consulta 2 del script: ítems, cantidades y precios aplicados de una factura."""
        numero = validar_numero_factura(numero_factura)
        return self._consultar(
            """
            SELECT f.numero_factura, s.codigo_servicio, s.descripcion_servicio,
                   df.cantidad, df.precio_unitario_aplicado, df.valor_venta
            FROM factura f
            JOIN detalle_factura df ON df.numero_factura = f.numero_factura
            JOIN servicio s         ON s.codigo_servicio = df.codigo_servicio
            WHERE f.numero_factura = %s
            ORDER BY s.codigo_servicio
            """,
            (numero,),
            "No se pudo consultar el detalle de la factura",
        )

    def consultar(self, numero_factura: str) -> Optional[dict]:
        """Factura completa: {'cabecera': {...}, 'items': [...]} o None si no existe."""
        cab = self.obtener_cabecera(numero_factura)
        if cab is None:
            return None
        return {"cabecera": cab, "items": self.obtener_detalle(numero_factura)}

    # ===================================================================== UPDATE
    def actualizar_cabecera(self, numero_factura: str, **cambios) -> dict:
        """Modifica campos de cabecera y fuerza el recálculo de importes.

        Los triggers solo reaccionan a cambios en detalle_factura; si cambia el IGV o la detracción
        hay que invocar recalcular_factura() para que subtotal/IGV/total/detracción no queden obsoletos.
        Todo ocurre en una sola transacción.
        """
        numero = validar_numero_factura(numero_factura)
        desconocidos = set(cambios) - set(_CAMPOS_EDITABLES)
        if desconocidos:
            raise ValidationError(f"Campos no editables: {sorted(desconocidos)}")
        if not cambios:
            raise ValidationError("No se indicó ningún campo a modificar.")

        valores: dict = {}
        for campo, valor in cambios.items():
            if campo == "igv_porcentaje":
                valor = validar_porcentaje(a_decimal(valor, "IGV"), "IGV")
            elif campo in ("id_detraccion",):
                valor = None if valor is None else validar_entero_rango(valor, campo, 1, 65535)
            elif campo in ("id_moneda", "id_forma_pago"):
                valor = validar_entero_rango(valor, campo, 1, 255)
            elif campo == "ruc_cliente":
                valor = validar_ruc(valor, "RUC del cliente")
            elif campo in ("fecha_emision", "fecha_vencimiento"):
                if valor is not None and not isinstance(valor, date):
                    raise ValidationError(f"'{campo}' debe ser una fecha.")
                if campo == "fecha_emision" and valor is None:
                    raise ValidationError("La fecha de emisión es obligatoria.")
            valores[campo] = valor

        def trabajo(cur):
            cur.execute(
                "SELECT fecha_emision, fecha_vencimiento FROM factura WHERE numero_factura = %s FOR UPDATE",
                (numero,),
            )
            actual = cur.fetchone()
            if actual is None:
                raise DAOError(f"La factura {numero} no existe.")
            emision = valores.get("fecha_emision", actual["fecha_emision"])
            vence = valores["fecha_vencimiento"] if "fecha_vencimiento" in valores else actual["fecha_vencimiento"]
            if vence is not None and vence < emision:
                raise ValidationError("La fecha de vencimiento no puede ser anterior a la de emisión.")

            # Los nombres de columna salen de una lista blanca fija; los valores siempre van con %s.
            asignaciones = ", ".join(f"{_CAMPOS_EDITABLES[c]} = %s" for c in valores)
            cur.execute(
                f"UPDATE factura SET {asignaciones} WHERE numero_factura = %s",
                (*valores.values(), numero),
            )
            cur.execute("CALL recalcular_factura(%s)", (numero,))
            return self._resumen(cur, numero)

        return self._en_transaccion(trabajo, f"No se pudo actualizar la factura {numero}")

    def agregar_item(self, numero_factura: str, item: ItemFactura) -> dict:
        numero = validar_numero_factura(numero_factura)
        it = self._validar_item(item)

        def trabajo(cur):
            self._insertar_detalle(cur, numero, it)
            return self._resumen(cur, numero)

        return self._en_transaccion(trabajo, f"No se pudo agregar el ítem a {numero}")

    def actualizar_item(
        self, numero_factura: str, codigo_servicio: int,
        cantidad: Optional[int] = None, precio_unitario=None,
    ) -> dict:
        numero = validar_numero_factura(numero_factura)
        codigo = validar_entero_rango(codigo_servicio, "código de servicio", 1, 255)
        if cantidad is None and precio_unitario is None:
            raise ValidationError("Indique la nueva cantidad y/o el nuevo precio.")
        sets, params = [], []
        if cantidad is not None:
            sets.append("cantidad = %s")
            params.append(validar_entero_rango(cantidad, "cantidad", 1, MAX_CANTIDAD))
        if precio_unitario is not None:
            sets.append("precio_unitario_aplicado = %s")
            params.append(validar_importe_positivo(a_decimal(precio_unitario, "precio unitario"), "precio unitario"))

        def trabajo(cur):
            cur.execute(
                f"UPDATE detalle_factura SET {', '.join(sets)} WHERE numero_factura = %s AND codigo_servicio = %s",
                (*params, numero, codigo),
            )
            if cur.rowcount == 0:
                raise DAOError(f"La factura {numero} no tiene el servicio {codigo}.")
            return self._resumen(cur, numero)

        return self._en_transaccion(trabajo, f"No se pudo modificar el ítem de {numero}")

    def eliminar_item(self, numero_factura: str, codigo_servicio: int) -> dict:
        numero = validar_numero_factura(numero_factura)
        codigo = validar_entero_rango(codigo_servicio, "código de servicio", 1, 255)

        def trabajo(cur):
            cur.execute(
                "DELETE FROM detalle_factura WHERE numero_factura = %s AND codigo_servicio = %s",
                (numero, codigo),
            )
            if cur.rowcount == 0:
                raise DAOError(f"La factura {numero} no tiene el servicio {codigo}.")
            return self._resumen(cur, numero)

        return self._en_transaccion(trabajo, f"No se pudo eliminar el ítem de {numero}")

    # ===================================================================== DELETE
    def eliminar(self, numero_factura: str) -> None:
        """Elimina la factura; sus detalles caen por ON DELETE CASCADE."""
        numero = validar_numero_factura(numero_factura)
        filas = self._ejecutar(
            "DELETE FROM factura WHERE numero_factura = %s", (numero,), "No se pudo eliminar la factura"
        )
        self._exigir_afectadas(filas, f"La factura {numero} no existe.")
