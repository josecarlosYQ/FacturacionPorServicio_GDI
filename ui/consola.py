"""Interfaz de consola: menús, lectura validada de datos y presentación de tablas.

Esta capa no contiene SQL: solo habla con los DAO y muestra los mensajes de error ya traducidos.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from core.errors import FacturacionError, ValidationError
from core.models import Cliente, ItemFactura, NuevaFactura, Servicio
from core.utils import a_decimal, calcular_totales, formato_importe, parsear_fecha
from dao.catalogo_dao import CatalogoDAO
from dao.cliente_dao import ClienteDAO
from dao.factura_dao import FacturaDAO
from dao.reporte_dao import ReporteDAO
from dao.servicio_dao import ServicioDAO

log = logging.getLogger("facturacion.ui")
SERIE_POR_DEFECTO = "F001"


class Cancelado(Exception):
    """El usuario canceló la operación (Ctrl+C / Ctrl+Z)."""


# ============================================================ formato de tablas
def _pct(v) -> str:
    return "" if v is None else f"{Decimal(v) * 100:.0f}%"


def _ent(v) -> str:
    return "" if v is None else str(int(v))


def _fmt(valor, fmt: Optional[Callable] = None) -> str:
    if fmt is not None:
        return fmt(valor)
    if valor is None:
        return "-"
    if isinstance(valor, Decimal):
        return formato_importe(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def imprimir_tabla(filas: list[dict], columnas: list[tuple]) -> None:
    """columnas: (clave, titulo) o (clave, titulo, funcion_formato)."""
    if not filas:
        print("  (sin resultados)")
        return
    cols = [(c[0], c[1], c[2] if len(c) > 2 else None) for c in columnas]
    celdas = [[_fmt(f.get(k), fm)[:45] for k, _, fm in cols] for f in filas]
    numericas = [isinstance(filas[0].get(k), (Decimal, int)) for k, _, _ in cols]
    anchos = [max(len(t), *(len(r[i]) for r in celdas)) for i, (_, t, _) in enumerate(cols)]

    def linea(valores):
        return "  " + " | ".join(
            v.rjust(anchos[i]) if numericas[i] else v.ljust(anchos[i]) for i, v in enumerate(valores)
        )

    print(linea([t for _, t, _ in cols]))
    print("  " + "-+-".join("-" * a for a in anchos))
    for r in celdas:
        print(linea(r))
    print(f"  ({len(filas)} fila{'s' if len(filas) != 1 else ''})")


# ================================================================== entradas
def pedir(texto: str, obligatorio: bool = True, defecto: Optional[str] = None) -> str:
    sufijo = f" [{defecto}]" if defecto not in (None, "") else (" (Enter = omitir)" if not obligatorio else "")
    while True:
        try:
            valor = input(f"  {texto}{sufijo}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            raise Cancelado()
        if valor:
            return valor
        if defecto is not None:
            return defecto
        if not obligatorio:
            return ""
        print("    Este dato es obligatorio.")


def pedir_entero(texto: str, minimo: int, maximo: int, defecto: Optional[int] = None) -> int:
    while True:
        valor = pedir(texto, True, None if defecto is None else str(defecto))
        try:
            n = int(valor)
            if minimo <= n <= maximo:
                return n
            print(f"    Debe estar entre {minimo} y {maximo}.")
        except ValueError:
            print("    Ingrese un número entero.")


def pedir_decimal(texto: str, obligatorio: bool = True, defecto: Optional[str] = None) -> Optional[Decimal]:
    while True:
        valor = pedir(texto, obligatorio, defecto)
        if not valor:
            return None
        try:
            return a_decimal(valor, texto)
        except ValidationError as e:
            print(f"    {e}")


def pedir_fecha(texto: str, obligatorio: bool = True, defecto: Optional[date] = None) -> Optional[date]:
    while True:
        valor = pedir(texto + " (AAAA-MM-DD)", obligatorio, defecto.isoformat() if defecto else None)
        if not valor:
            return None
        try:
            return parsear_fecha(valor, texto)
        except ValidationError as e:
            print(f"    {e}")


def confirmar(texto: str) -> bool:
    return pedir(f"{texto} (s/n)", True).lower() in ("s", "si", "sí", "y", "yes")


def elegir_catalogo(titulo: str, filas: list[dict], clave: str, columnas: list[tuple],
                    permitir_ninguno: bool = False) -> Optional[int]:
    print(f"\n  {titulo}")
    imprimir_tabla(filas, columnas)
    validos = {f[clave] for f in filas}
    while True:
        valor = pedir(f"Elija {clave}", obligatorio=not permitir_ninguno)
        if not valor and permitir_ninguno:
            return None
        if valor.isdigit() and int(valor) in validos:
            return int(valor)
        print("    Opción no válida.")


def menu(titulo: str, opciones: list[tuple[str, str]]) -> str:
    print(f"\n=== {titulo} ===")
    for clave, texto in opciones:
        print(f"  {clave}) {texto}")
    return pedir("Opción")


# ================================================================ aplicación
class Consola:
    def __init__(self, db):
        self.db = db
        self.clientes = ClienteDAO(db)
        self.servicios = ServicioDAO(db)
        self.facturas = FacturaDAO(db)
        self.reportes = ReporteDAO(db)
        self.catalogos = CatalogoDAO(db)

    # ------------------------------------------------------------- ejecución
    def ejecutar(self) -> None:
        print("\nSistema de Facturación - Repuestos y Rectificaciones Pacífico E.I.R.L.")
        acciones = {"1": self.menu_clientes, "2": self.menu_servicios, "3": self.menu_facturas, "4": self.menu_reportes}
        while True:
            try:
                op = menu("MENÚ PRINCIPAL", [("1", "Clientes"), ("2", "Servicios"), ("3", "Facturas"),
                                              ("4", "Reportes"), ("0", "Salir")])
            except Cancelado:
                break
            if op == "0":
                break
            if op in acciones:
                acciones[op]()
            else:
                print("  Opción no válida.")
        print("\nHasta pronto.")

    def _submenu(self, titulo: str, opciones: list[tuple[str, str]], acciones: dict) -> None:
        while True:
            try:
                op = menu(titulo, opciones + [("0", "Volver")])
            except Cancelado:
                return
            if op == "0":
                return
            accion = acciones.get(op)
            if accion is None:
                print("  Opción no válida.")
                continue
            self._seguro(accion)

    @staticmethod
    def _seguro(accion: Callable[[], None]) -> None:
        """Ejecuta una acción mostrando errores controlados sin cerrar el programa."""
        try:
            accion()
        except Cancelado:
            print("  Operación cancelada.")
        except FacturacionError as e:
            print(f"\n  ✖ {e}")
        except Exception:  # error inesperado: detalle al log, mensaje genérico a pantalla
            log.exception("Error inesperado")
            print("\n  ✖ Ocurrió un error inesperado. Revise el archivo facturacion.log.")

    # ================================================================ CLIENTES
    def menu_clientes(self) -> None:
        self._submenu("CLIENTES", [
            ("1", "Listar / buscar"), ("2", "Ver cliente"), ("3", "Registrar"),
            ("4", "Modificar"), ("5", "Eliminar"), ("6", "Clientes por distrito"),
        ], {"1": self.cli_listar, "2": self.cli_ver, "3": self.cli_crear,
            "4": self.cli_modificar, "5": self.cli_eliminar, "6": self.cli_por_distrito})

    _COLS_CLI = [("ruc_cliente", "RUC"), ("nombre_cliente", "Cliente"), ("direccion_cliente", "Dirección"),
                 ("distrito", "Distrito"), ("provincia", "Provincia"), ("departamento", "Dpto.")]

    def cli_listar(self) -> None:
        texto = pedir("Buscar por nombre o RUC", obligatorio=False)
        imprimir_tabla(self.clientes.listar(texto), self._COLS_CLI)

    def cli_ver(self) -> None:
        c = self.clientes.obtener(pedir("RUC del cliente"))
        imprimir_tabla([c] if c else [], self._COLS_CLI)

    def _pedir_distrito(self) -> int:
        return elegir_catalogo("Distritos", self.catalogos.listar_distritos(), "id_distrito",
                               [("id_distrito", "id_distrito"), ("distrito", "Distrito"),
                                ("provincia", "Provincia"), ("departamento", "Dpto.")])

    def cli_crear(self) -> None:
        ruc = pedir("RUC (11 dígitos)")
        nombre = pedir("Nombre / razón social")
        direccion = pedir("Dirección")
        self.clientes.crear(Cliente(ruc, nombre, direccion, self._pedir_distrito()))
        print("  ✔ Cliente registrado.")

    def cli_modificar(self) -> None:
        actual = self.clientes.obtener(pedir("RUC del cliente a modificar"))
        if not actual:
            print("  No existe ese cliente.")
            return
        nombre = pedir("Nombre", defecto=actual["nombre_cliente"])
        direccion = pedir("Dirección", defecto=actual["direccion_cliente"])
        id_distrito = actual["id_distrito"]
        if confirmar("¿Cambiar el distrito?"):
            id_distrito = self._pedir_distrito()
        self.clientes.actualizar(Cliente(actual["ruc_cliente"], nombre, direccion, id_distrito))
        print("  ✔ Cliente actualizado.")

    def cli_eliminar(self) -> None:
        ruc = pedir("RUC del cliente a eliminar")
        if confirmar(f"¿Eliminar al cliente {ruc}?"):
            self.clientes.eliminar(ruc)
            print("  ✔ Cliente eliminado.")

    def cli_por_distrito(self) -> None:
        imprimir_tabla(self.clientes.listar_por_distrito(pedir("Nombre del distrito")), self._COLS_CLI)

    # =============================================================== SERVICIOS
    def menu_servicios(self) -> None:
        self._submenu("SERVICIOS", [("1", "Listar"), ("2", "Registrar"), ("3", "Modificar"), ("4", "Eliminar")],
                      {"1": self.srv_listar, "2": self.srv_crear, "3": self.srv_modificar, "4": self.srv_eliminar})

    _COLS_SRV = [("codigo_servicio", "Código"), ("descripcion_servicio", "Descripción"),
                 ("valor_unitario_servicio", "Valor unitario")]

    def srv_listar(self) -> None:
        imprimir_tabla(self.servicios.listar(), self._COLS_SRV)

    def srv_crear(self) -> None:
        codigo = pedir_entero("Código", 1, 255, defecto=self.servicios.siguiente_codigo())
        desc = pedir("Descripción")
        valor = pedir_decimal("Valor unitario")
        self.servicios.crear(Servicio(codigo, desc, valor))
        print("  ✔ Servicio registrado.")

    def srv_modificar(self) -> None:
        actual = self.servicios.obtener(pedir_entero("Código del servicio", 1, 255))
        if not actual:
            print("  No existe ese servicio.")
            return
        desc = pedir("Descripción", defecto=actual["descripcion_servicio"])
        valor = pedir_decimal("Valor unitario", defecto=str(actual["valor_unitario_servicio"]))
        self.servicios.actualizar(Servicio(actual["codigo_servicio"], desc, valor))
        print("  ✔ Servicio actualizado (las facturas ya emitidas conservan su precio aplicado).")

    def srv_eliminar(self) -> None:
        codigo = pedir_entero("Código del servicio a eliminar", 1, 255)
        if confirmar(f"¿Eliminar el servicio {codigo}?"):
            self.servicios.eliminar(codigo)
            print("  ✔ Servicio eliminado.")

    # ================================================================ FACTURAS
    def menu_facturas(self) -> None:
        self._submenu("FACTURAS", [
            ("1", "Listar facturas"), ("2", "Consultar una factura (detalle)"), ("3", "Registrar nueva factura"),
            ("4", "Modificar cabecera"), ("5", "Agregar ítem"), ("6", "Modificar ítem"),
            ("7", "Eliminar ítem"), ("8", "Eliminar factura"),
        ], {"1": self.fac_listar, "2": self.fac_consultar, "3": self.fac_registrar,
            "4": self.fac_modificar_cabecera, "5": self.fac_agregar_item, "6": self.fac_modificar_item,
            "7": self.fac_eliminar_item, "8": self.fac_eliminar})

    def fac_listar(self) -> None:
        ruc = pedir("Filtrar por RUC de cliente", obligatorio=False)
        imprimir_tabla(self.facturas.listar(ruc or None), [
            ("numero_factura", "Factura"), ("fecha_emision", "Emisión"), ("fecha_vencimiento", "Vence"),
            ("nombre_cliente", "Cliente"), ("moneda", "Moneda"), ("subtotal", "Subtotal"),
            ("igv_calculado", "IGV"), ("total", "Total"), ("estado_vencimiento", "Estado")])

    def _mostrar_factura(self, datos: dict) -> None:
        c, items = datos["cabecera"], datos["items"]
        print(f"\n  FACTURA {c['numero_factura']}      Emisión: {_fmt(c['fecha_emision'])}"
              f"   Vence: {_fmt(c['fecha_vencimiento'])}   [{c['estado_vencimiento']}]")
        print(f"  Emisor : {c['razon_social_empresa']} ({c['ruc_empresa']})")
        print(f"  Cliente: {c['nombre_cliente']} ({c['ruc_cliente']})")
        print(f"  Moneda : {c['moneda']}   Forma de pago: {c['forma_pago']}")
        print()
        imprimir_tabla(items, [("codigo_servicio", "Cód."), ("descripcion_servicio", "Servicio"),
                               ("cantidad", "Cant."), ("precio_unitario_aplicado", "P. unit."),
                               ("valor_venta", "Valor venta")])
        print(f"\n  Subtotal: {formato_importe(c['subtotal']):>12}")
        print(f"  IGV ({_pct(c['igv_porcentaje'])}): {formato_importe(c['igv_calculado']):>10}")
        print(f"  TOTAL   : {formato_importe(c['total']):>12}")
        if c["id_detraccion"] is not None:
            print(f"  Detracción ({_pct(c['detraccion_porcentaje'])} - {c['servicio_detraccion']}): "
                  f"{formato_importe(c['monto_detraccion'])}")

    def fac_consultar(self) -> None:
        datos = self.facturas.consultar(pedir("Número de factura (ej. F001-00000262)"))
        if datos is None:
            print("  No existe esa factura.")
        else:
            self._mostrar_factura(datos)

    def _elegir_empresa(self) -> str:
        empresas = self.catalogos.listar_empresas()
        if not empresas:
            raise ValidationError("No hay ninguna empresa emisora registrada en la base de datos.")
        if len(empresas) == 1:
            print(f"  Emisor: {empresas[0]['razon_social_empresa']}")
            return empresas[0]["ruc_empresa"]
        print()
        imprimir_tabla(empresas, [("ruc_empresa", "RUC"), ("razon_social_empresa", "Empresa")])
        while True:
            ruc = pedir("RUC de la empresa emisora")
            if any(e["ruc_empresa"] == ruc for e in empresas):
                return ruc
            print("    RUC no válido.")

    def fac_registrar(self) -> None:
        print("\n  --- Nueva factura ---")
        ruc_empresa = self._elegir_empresa()

        cliente = self.clientes.obtener(pedir("RUC del cliente"))
        if not cliente:
            print("  El cliente no existe. Regístrelo primero en el menú Clientes.")
            return
        print(f"  Cliente: {cliente['nombre_cliente']}")

        serie = pedir("Serie", defecto=SERIE_POR_DEFECTO)
        numero = pedir("Número de factura", defecto=self.facturas.siguiente_numero(serie))
        emision = pedir_fecha("Fecha de emisión", defecto=date.today())
        vence = pedir_fecha("Fecha de vencimiento", obligatorio=False)

        id_moneda = elegir_catalogo("Monedas", self.catalogos.listar_monedas(), "id_moneda",
                                    [("id_moneda", "id_moneda"), ("descripcion", "Moneda")])
        id_pago = elegir_catalogo("Formas de pago", self.catalogos.listar_formas_pago(), "id_forma_pago",
                                  [("id_forma_pago", "id_forma_pago"), ("descripcion", "Forma de pago")])
        detracciones = self.catalogos.listar_detracciones()
        id_detraccion = elegir_catalogo("Detracciones", detracciones, "id_detraccion",
                                        [("id_detraccion", "id_detraccion"),
                                         ("detraccion_porcentaje", "%", _pct),
                                         ("servicio_detraccion", "Servicio")], permitir_ninguno=True)
        igv = pedir_decimal("IGV en %", defecto="18") / 100

        catalogo = {s["codigo_servicio"]: s for s in self.servicios.listar()}
        print("\n  Servicios disponibles:")
        imprimir_tabla(list(catalogo.values()), self._COLS_SRV)

        items: list[ItemFactura] = []
        print("\n  Agregue ítems (deje el código vacío para terminar).")
        while True:
            codigo_txt = pedir("Código de servicio", obligatorio=False)
            if not codigo_txt:
                break
            if not codigo_txt.isdigit() or int(codigo_txt) not in catalogo:
                print("    Ese servicio no existe.")
                continue
            codigo = int(codigo_txt)
            if any(i.codigo_servicio == codigo for i in items):
                print("    Ese servicio ya está en la factura; use otra línea distinta o corrija la cantidad.")
                continue
            cantidad = pedir_entero("Cantidad", 1, 255)
            vigente = catalogo[codigo]["valor_unitario_servicio"]
            precio = pedir_decimal("Precio unitario", defecto=str(vigente))
            items.append(ItemFactura(codigo, cantidad, precio))
        if not items:
            print("  Una factura necesita al menos un ítem. Operación cancelada.")
            return

        pct_det = None
        if id_detraccion is not None:
            pct_det = next(d["detraccion_porcentaje"] for d in detracciones if d["id_detraccion"] == id_detraccion)
        vista = calcular_totales([(i.cantidad, i.precio_unitario) for i in items], igv, pct_det)
        print(f"\n  Vista previa -> Subtotal {formato_importe(vista['subtotal'])} | IGV {formato_importe(vista['igv'])}"
              f" | Total {formato_importe(vista['total'])} | Detracción {formato_importe(vista['detraccion'])}")
        print("  (los importes definitivos los calcula la base de datos con sus triggers)")
        if not confirmar("¿Registrar la factura?"):
            print("  Operación cancelada.")
            return

        self.facturas.registrar(NuevaFactura(
            numero_factura=numero, fecha_emision=emision, fecha_vencimiento=vence, id_moneda=id_moneda,
            id_forma_pago=id_pago, ruc_empresa=ruc_empresa, ruc_cliente=cliente["ruc_cliente"],
            igv_porcentaje=igv, id_detraccion=id_detraccion, items=items))
        print(f"\n  ✔ Factura {numero.upper()} registrada.")
        self._mostrar_factura(self.facturas.consultar(numero))

    def fac_modificar_cabecera(self) -> None:
        numero = pedir("Número de factura")
        datos = self.facturas.consultar(numero)
        if datos is None:
            print("  No existe esa factura.")
            return
        self._mostrar_factura(datos)
        op = menu("¿Qué desea cambiar?", [
            ("1", "Fecha de emisión"), ("2", "Fecha de vencimiento"), ("3", "Detracción"),
            ("4", "Forma de pago"), ("5", "Moneda"), ("6", "IGV %"), ("7", "Cliente")])
        if op == "1":
            cambios = {"fecha_emision": pedir_fecha("Nueva fecha de emisión")}
        elif op == "2":
            cambios = {"fecha_vencimiento": pedir_fecha("Nueva fecha de vencimiento (vacío = sin vencimiento)", False)}
        elif op == "3":
            cambios = {"id_detraccion": elegir_catalogo(
                "Detracciones", self.catalogos.listar_detracciones(), "id_detraccion",
                [("id_detraccion", "id_detraccion"), ("detraccion_porcentaje", "%", _pct),
                 ("servicio_detraccion", "Servicio")], permitir_ninguno=True)}
        elif op == "4":
            cambios = {"id_forma_pago": elegir_catalogo(
                "Formas de pago", self.catalogos.listar_formas_pago(), "id_forma_pago",
                [("id_forma_pago", "id_forma_pago"), ("descripcion", "Forma de pago")])}
        elif op == "5":
            cambios = {"id_moneda": elegir_catalogo(
                "Monedas", self.catalogos.listar_monedas(), "id_moneda",
                [("id_moneda", "id_moneda"), ("descripcion", "Moneda")])}
        elif op == "6":
            cambios = {"igv_porcentaje": pedir_decimal("Nuevo IGV en %") / 100}
        elif op == "7":
            ruc = pedir("RUC del nuevo cliente")
            if not self.clientes.obtener(ruc):
                print("  Ese cliente no existe.")
                return
            cambios = {"ruc_cliente": ruc}
        else:
            print("  Opción no válida.")
            return
        self.facturas.actualizar_cabecera(numero, **cambios)
        print("  ✔ Cabecera actualizada y totales recalculados.")
        self._mostrar_factura(self.facturas.consultar(numero))

    def fac_agregar_item(self) -> None:
        numero = pedir("Número de factura")
        imprimir_tabla(self.servicios.listar(), self._COLS_SRV)
        codigo = pedir_entero("Código de servicio", 1, 255)
        cantidad = pedir_entero("Cantidad", 1, 255)
        precio = pedir_decimal("Precio unitario (Enter = valor vigente del servicio)", obligatorio=False)
        self.facturas.agregar_item(numero, ItemFactura(codigo, cantidad, precio))
        print("  ✔ Ítem agregado.")
        self._mostrar_factura(self.facturas.consultar(numero))

    def fac_modificar_item(self) -> None:
        numero = pedir("Número de factura")
        codigo = pedir_entero("Código del servicio a modificar", 1, 255)
        txt = pedir("Nueva cantidad (Enter = sin cambio)", obligatorio=False)
        cantidad = int(txt) if txt.isdigit() else None
        precio = pedir_decimal("Nuevo precio unitario (Enter = sin cambio)", obligatorio=False)
        self.facturas.actualizar_item(numero, codigo, cantidad, precio)
        print("  ✔ Ítem actualizado.")
        self._mostrar_factura(self.facturas.consultar(numero))

    def fac_eliminar_item(self) -> None:
        numero = pedir("Número de factura")
        codigo = pedir_entero("Código del servicio a quitar", 1, 255)
        if confirmar(f"¿Quitar el servicio {codigo} de {numero}?"):
            self.facturas.eliminar_item(numero, codigo)
            print("  ✔ Ítem eliminado.")
            self._mostrar_factura(self.facturas.consultar(numero))

    def fac_eliminar(self) -> None:
        numero = pedir("Número de factura a eliminar")
        if confirmar(f"¿Eliminar la factura {numero} y todo su detalle?"):
            self.facturas.eliminar(numero)
            print("  ✔ Factura eliminada.")

    # ================================================================ REPORTES
    def menu_reportes(self) -> None:
        self._submenu("REPORTES", [
            ("1", "Total facturado por cliente"), ("2", "Servicios más solicitados"),
            ("3", "Ventas en un rango de fechas"), ("4", "Facturas con detracción"),
            ("5", "Resumen por moneda"), ("6", "Resumen por forma de pago"),
            ("7", "Ventas e IGV por mes"),
        ], {"1": self.rep_por_cliente, "2": self.rep_servicios, "3": self.rep_rango,
            "4": self.rep_detraccion, "5": self.rep_moneda, "6": self.rep_pago, "7": self.rep_mensual})

    def _filtro_moneda(self) -> Optional[int]:
        """Los importes de cada factura están en su moneda: permite acotar para no mezclar."""
        if not confirmar("¿Filtrar por una moneda (recomendado para no sumar Soles con Dólares)?"):
            return None
        return elegir_catalogo("Monedas", self.catalogos.listar_monedas(), "id_moneda",
                               [("id_moneda", "id_moneda"), ("descripcion", "Moneda")])

    def rep_por_cliente(self) -> None:
        imprimir_tabla(self.reportes.total_facturado_por_cliente(self._filtro_moneda()), [
            ("ruc_cliente", "RUC"), ("nombre_cliente", "Cliente"),
            ("cantidad_facturas", "N.º facturas"), ("total_facturado", "Total facturado")])

    def rep_servicios(self) -> None:
        txt = pedir("Mostrar solo los N primeros (Enter = todos)", obligatorio=False)
        limite = int(txt) if txt.isdigit() and int(txt) > 0 else None
        imprimir_tabla(self.reportes.servicios_mas_solicitados(limite, self._filtro_moneda()), [
            ("codigo_servicio", "Cód."), ("descripcion_servicio", "Servicio"),
            ("unidades_solicitadas", "Unidades", _ent), ("importe_vendido", "Importe vendido")])

    def rep_rango(self) -> None:
        desde = pedir_fecha("Desde")
        hasta = pedir_fecha("Hasta")
        imprimir_tabla(self.reportes.ventas_por_rango_fechas(desde, hasta), [
            ("numero_factura", "Factura"), ("fecha_emision", "Emisión"), ("nombre_cliente", "Cliente"),
            ("moneda", "Moneda"), ("subtotal", "Subtotal"), ("igv_calculado", "IGV"), ("total", "Total")])

    def rep_detraccion(self) -> None:
        solo = confirmar("¿Excluir las de 0 % ('No aplica detracción')?")
        imprimir_tabla(self.reportes.facturas_con_detraccion(solo), [
            ("numero_factura", "Factura"), ("nombre_cliente", "Cliente"),
            ("servicio_detraccion", "Detracción"), ("detraccion_porcentaje", "%", _pct),
            ("total", "Total"), ("monto_detraccion", "Monto detr."), ("neto_referencial", "Neto ref.")])

    def rep_moneda(self) -> None:
        imprimir_tabla(self.reportes.resumen_por_moneda(), [
            ("moneda", "Moneda"), ("cantidad_facturas", "N.º facturas"), ("subtotal_acumulado", "Subtotal"),
            ("igv_acumulado", "IGV"), ("total_acumulado", "Total")])

    def rep_pago(self) -> None:
        imprimir_tabla(self.reportes.resumen_por_forma_pago(), [
            ("forma_pago", "Forma de pago"), ("moneda", "Moneda"),
            ("cantidad_facturas", "N.º facturas"), ("total_facturado", "Total")])

    def rep_mensual(self) -> None:
        imprimir_tabla(self.reportes.ventas_e_igv_por_mes(self._filtro_moneda()), [
            ("periodo", "Periodo"), ("cantidad_facturas", "N.º facturas"), ("subtotal", "Subtotal"),
            ("igv", "IGV"), ("total_ventas", "Total ventas")])
