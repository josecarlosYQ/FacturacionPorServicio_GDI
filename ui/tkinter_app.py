"""Interfaz gráfica Tkinter para Facturación Pacífico.

Pestañas: Clientes, Servicios, Nueva factura, Facturas registradas, Reportes y Empresa emisora.
Todos los Combobox se llenan desde MySQL al abrir la vista (ver ui/widgets.ComboID).
"""
import logging
import os
import tkinter as tk
from datetime import date
from decimal import Decimal
from tkinter import filedialog, messagebox, ttk

from core.errors import FacturacionError, ValidationError
from core.models import Cliente, Empresa, ItemFactura, NuevaFactura, Servicio
from core.utils import a_decimal, calcular_totales, formato_importe, parsear_fecha, simbolo_moneda
from dao.catalogo_dao import CatalogoDAO
from dao.cliente_dao import ClienteDAO
from dao.empresa_dao import EmpresaDAO
from dao.factura_dao import FacturaDAO
from dao.reporte_dao import ReporteDAO
from dao.servicio_dao import ServicioDAO
from ui.pdf_exporter import exportar_factura_pdf
from ui.widgets import ComboID, SelectorUbigeo

log = logging.getLogger("facturacion.ui")


class AplicacionTk:
    def __init__(self, db):
        self.db = db
        self.clientes = ClienteDAO(db)
        self.servicios = ServicioDAO(db)
        self.facturas = FacturaDAO(db)
        self.catalogos = CatalogoDAO(db)
        self.reportes = ReporteDAO(db)
        self.empresas = EmpresaDAO(db)
        self.empresa: dict | None = None          # perfil emisor vigente (fila de la BD)
        self._ruc_empresa_guardado: str | None = None
        self._items: list[dict] = []
        self._ultima_factura: str | None = None
        self._servicios_cache: list[dict] = []

        self.ventana = tk.Tk()
        self.ventana.title("Factura Pe | Sistema de gestión")
        self.ventana.geometry("1180x720")
        self.ventana.minsize(1000, 560)
        self._estilos()
        self._construir()
        self._menu()
        self.refrescar_todo()
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)
        if self.empresa is None:
            self.tabs.select(self.tab_empresa)
            self.ventana.after(300, lambda: messagebox.showinfo(
                "Configure su empresa",
                "Antes de facturar registre los datos de la empresa emisora en esta pestaña.",
                parent=self.ventana))

    # ================================================================== estructura
    def _estilos(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TFrame", background="#f3f6fb")
        st.configure("TLabelframe", background="#f3f6fb")
        st.configure("TLabelframe.Label", background="#f3f6fb", font=("Segoe UI", 10, "bold"), foreground="#17365d")
        st.configure("TLabel", background="#f3f6fb", font=("Segoe UI", 10))
        st.configure("Title.TLabel", font=("Segoe UI", 19, "bold"), foreground="#17365d")
        st.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#52627a")
        st.configure("Emisor.TLabel", font=("Segoe UI", 10), foreground="#17365d")
        st.configure("TButton", font=("Segoe UI", 9), padding=7)
        st.configure("Accent.TButton", background="#17365d", foreground="white")
        st.map("Accent.TButton", background=[("active", "#24558c"), ("disabled", "#9fb0c6")])
        st.configure("Treeview", rowheight=27, font=("Segoe UI", 9))
        st.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _construir(self):
        base = ttk.Frame(self.ventana, padding=16)
        base.pack(fill="both", expand=True)
        cab = ttk.Frame(base)
        cab.pack(fill="x", pady=(0, 14))
        ttk.Label(cab, text="FACTURA PE", style="Title.TLabel").pack(anchor="w")
        self.lbl_subtitulo = ttk.Label(cab, text="Gestión comercial", style="Sub.TLabel")
        self.lbl_subtitulo.pack(anchor="w")
        self.tabs = ttk.Notebook(base)
        self.tabs.pack(fill="both", expand=True)
        nombres = [("tab_clientes", "Clientes"), ("tab_servicios", "Servicios"),
                   ("tab_facturas", "Nueva factura"), ("tab_consulta", "Facturas registradas"),
                   ("tab_reportes", "Reportes"), ("tab_empresa", "Empresa emisora")]
        for attr, texto in nombres:
            frame = ttk.Frame(self.tabs, padding=12)
            setattr(self, attr, frame)
            self.tabs.add(frame, text=texto)
        self._ui_clientes()
        self._ui_servicios()
        self._ui_facturas()
        self._ui_consulta()
        self._ui_reportes()
        self._ui_empresa()
        self.tabs.bind("<<NotebookTabChanged>>", self._al_cambiar_pestana)

    def _menu(self):
        barra = tk.Menu(self.ventana)
        archivo = tk.Menu(barra, tearoff=0)
        archivo.add_command(label="Actualizar datos", command=self.refrescar_todo)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.cerrar)
        barra.add_cascade(label="Archivo", menu=archivo)

        maestros = tk.Menu(barra, tearoff=0)
        maestros.add_command(label="Clientes", command=lambda: self.tabs.select(self.tab_clientes))
        maestros.add_command(label="Servicios / Productos", command=lambda: self.tabs.select(self.tab_servicios))
        barra.add_cascade(label="Maestros", menu=maestros)

        fact = tk.Menu(barra, tearoff=0)
        fact.add_command(label="Nueva factura", command=lambda: self.tabs.select(self.tab_facturas))
        fact.add_command(label="Facturas registradas", command=lambda: self.tabs.select(self.tab_consulta))
        fact.add_command(label="Reportes", command=lambda: self.tabs.select(self.tab_reportes))
        barra.add_cascade(label="Facturación", menu=fact)

        conf = tk.Menu(barra, tearoff=0)
        conf.add_command(label="Empresa emisora…", command=lambda: self.tabs.select(self.tab_empresa))
        barra.add_cascade(label="Configuración", menu=conf)
        self.ventana.config(menu=barra)

    # ================================================================== helpers UI
    def _tabla(self, parent, cols, headings=None, widths=None):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=8)
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for i, c in enumerate(cols):
            tree.heading(c, text=(headings or cols)[i])
            tree.column(c, width=(widths or [140] * len(cols))[i], anchor="w")
        sy = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sx = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _campo(self, parent, label, var, row, col=0, width=28, **kw):
        box = ttk.Frame(parent)
        box.grid(row=row, column=col, padx=6, pady=5, sticky="ew")
        ttk.Label(box, text=label).pack(anchor="w")
        ent = ttk.Entry(box, textvariable=var, width=width, **kw)
        ent.pack(fill="x")
        return ent

    def _combo(self, parent, label, row, col, width=30, **kw):
        box = ttk.Frame(parent)
        box.grid(row=row, column=col, padx=6, pady=5, sticky="ew")
        ttk.Label(box, text=label).pack(anchor="w")
        cb = ComboID(box, width=width, **kw)
        cb.pack(fill="x")
        return cb

    def _safe(self, fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - se muestra al usuario y se registra
            log.exception("Error en interfaz")
            messagebox.showerror("No se pudo completar la operación", str(e), parent=self.ventana)
            return None

    def _al_cambiar_pestana(self, _e=None):
        actual = self.tabs.select()
        if actual == str(self.tab_facturas):
            self._cargar_datos_factura()
        elif actual == str(self.tab_consulta):
            self.cargar_facturas()

    # ================================================================== carga general
    def refrescar_todo(self):
        self.cargar_empresa()
        self.cargar_clientes()
        self.cargar_servicios()
        self._cargar_datos_factura()
        self.cargar_facturas()

    # ================================================================== CLIENTES
    def _ui_clientes(self):
        f = self.tab_clientes
        form = ttk.LabelFrame(f, text="Datos del cliente", padding=10)
        form.pack(fill="x")
        self.c_ruc, self.c_nombre, self.c_dir = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self._campo(form, "RUC (11 dígitos)", self.c_ruc, 0, 0)
        self._campo(form, "Nombre / razón social", self.c_nombre, 0, 1, width=40)
        self._campo(form, "Dirección", self.c_dir, 0, 2, width=40)
        self.ub_cliente = SelectorUbigeo(form, self.catalogos)
        self.ub_cliente.grid(row=1, column=0, columnspan=3, sticky="ew", padx=2, pady=4)
        btn = ttk.Frame(form)
        btn.grid(row=2, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(btn, text="Registrar", command=self.guardar_cliente, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(btn, text="Actualizar seleccionado", command=self.actualizar_cliente).pack(side="left", padx=3)
        ttk.Button(btn, text="Eliminar", command=self.eliminar_cliente).pack(side="left", padx=3)
        ttk.Button(btn, text="Limpiar", command=self.limpiar_cliente).pack(side="left", padx=3)
        self.tree_clientes = self._tabla(
            f, ("ruc", "nombre", "direccion", "distrito", "provincia"),
            ("RUC", "Cliente", "Dirección", "Distrito", "Provincia"), [120, 270, 270, 150, 130])
        self.tree_clientes.bind("<<TreeviewSelect>>", self.seleccionar_cliente)

    def cargar_clientes(self):
        rows = self._safe(lambda: self.clientes.listar())
        if rows is None:
            return
        self.tree_clientes.delete(*self.tree_clientes.get_children())
        for r in rows:
            self.tree_clientes.insert("", "end", iid=r["ruc_cliente"], values=(
                r["ruc_cliente"], r["nombre_cliente"], r["direccion_cliente"], r["distrito"], r["provincia"]))

    def limpiar_cliente(self):
        for v in (self.c_ruc, self.c_nombre, self.c_dir):
            v.set("")
        self.ub_cliente.limpiar()
        self.tree_clientes.selection_remove(self.tree_clientes.selection())

    def seleccionar_cliente(self, _=None):
        sel = self.tree_clientes.selection()
        if not sel:
            return
        fila = self._safe(lambda: self.clientes.obtener(sel[0]))
        if not fila:
            return
        self.c_ruc.set(fila["ruc_cliente"])
        self.c_nombre.set(fila["nombre_cliente"])
        self.c_dir.set(fila["direccion_cliente"])
        self.ub_cliente.establecer(fila["id_distrito"])

    def _leer_cliente(self) -> Cliente:
        id_distrito = self.ub_cliente.id_distrito()
        if id_distrito is None:
            raise ValidationError("Seleccione departamento, provincia y distrito del cliente.")
        return Cliente(self.c_ruc.get(), self.c_nombre.get(), self.c_dir.get(), id_distrito)

    def guardar_cliente(self):
        def op():
            self.clientes.crear(self._leer_cliente())
            messagebox.showinfo("Correcto", "Cliente registrado.", parent=self.ventana)
            self.limpiar_cliente()
            self.cargar_clientes()
        self._safe(op)

    def actualizar_cliente(self):
        def op():
            self.clientes.actualizar(self._leer_cliente())
            messagebox.showinfo("Correcto", "Cliente actualizado.", parent=self.ventana)
            self.cargar_clientes()
        self._safe(op)

    def eliminar_cliente(self):
        if not self.c_ruc.get():
            return messagebox.showwarning("Atención", "Seleccione un cliente.", parent=self.ventana)
        if messagebox.askyesno("Confirmar", "¿Eliminar el cliente seleccionado?", parent=self.ventana):
            def op():
                self.clientes.eliminar(self.c_ruc.get())
                self.cargar_clientes()
                self.limpiar_cliente()
            self._safe(op)

    # ================================================================== SERVICIOS
    def _ui_servicios(self):
        f = self.tab_servicios
        form = ttk.LabelFrame(f, text="Datos del servicio / producto", padding=10)
        form.pack(fill="x")
        self.s_codigo, self.s_desc, self.s_precio = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self._campo(form, "Código (1-255)", self.s_codigo, 0, 0)
        self._campo(form, "Descripción", self.s_desc, 0, 1, width=50)
        self._campo(form, "Precio unitario", self.s_precio, 0, 2)
        btn = ttk.Frame(form)
        btn.grid(row=1, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(btn, text="Registrar", command=self.guardar_servicio, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(btn, text="Actualizar seleccionado", command=self.actualizar_servicio).pack(side="left", padx=3)
        ttk.Button(btn, text="Eliminar", command=self.eliminar_servicio).pack(side="left", padx=3)
        ttk.Button(btn, text="Limpiar", command=self.limpiar_servicio).pack(side="left", padx=3)
        self.tree_servicios = self._tabla(
            f, ("codigo", "descripcion", "precio"), ("Código", "Descripción", "Precio unitario"), [100, 600, 160])
        self.tree_servicios.bind("<<TreeviewSelect>>", self.seleccionar_servicio)

    def cargar_servicios(self):
        rows = self._safe(self.servicios.listar)
        if rows is None:
            return
        self._servicios_cache = rows
        self.tree_servicios.delete(*self.tree_servicios.get_children())
        for r in rows:
            self.tree_servicios.insert("", "end", values=(
                r["codigo_servicio"], r["descripcion_servicio"], formato_importe(r["valor_unitario_servicio"])))

    def limpiar_servicio(self):
        for v in (self.s_codigo, self.s_desc, self.s_precio):
            v.set("")
        self.tree_servicios.selection_remove(self.tree_servicios.selection())

    def seleccionar_servicio(self, _=None):
        sel = self.tree_servicios.selection()
        if not sel:
            return
        cod, desc, precio = self.tree_servicios.item(sel[0], "values")
        self.s_codigo.set(cod)
        self.s_desc.set(desc)
        self.s_precio.set(str(precio).replace(",", ""))

    def _leer_servicio(self) -> Servicio:
        return Servicio(int(self.s_codigo.get()), self.s_desc.get(), a_decimal(self.s_precio.get(), "precio unitario"))

    def guardar_servicio(self):
        def op():
            self.servicios.crear(self._leer_servicio())
            messagebox.showinfo("Correcto", "Servicio registrado.", parent=self.ventana)
            self.limpiar_servicio()
            self.cargar_servicios()
        self._safe(op)

    def actualizar_servicio(self):
        def op():
            self.servicios.actualizar(self._leer_servicio())
            messagebox.showinfo("Correcto", "Servicio actualizado.", parent=self.ventana)
            self.cargar_servicios()
        self._safe(op)

    def eliminar_servicio(self):
        if not self.s_codigo.get():
            return messagebox.showwarning("Atención", "Seleccione un servicio.", parent=self.ventana)
        if messagebox.askyesno("Confirmar", "¿Eliminar el servicio seleccionado?", parent=self.ventana):
            def op():
                self.servicios.eliminar(int(self.s_codigo.get()))
                self.cargar_servicios()
                self.limpiar_servicio()
            self._safe(op)

    # ================================================================== EMPRESA EMISORA
    def _ui_empresa(self):
        f = self.tab_empresa
        form = ttk.LabelFrame(f, text="Perfil de la empresa emisora", padding=12)
        form.pack(fill="x")
        self.e_razon, self.e_ruc, self.e_dir = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.e_tel, self.e_cta = tk.StringVar(), tk.StringVar()
        self._campo(form, "Razón social (máx. 50)", self.e_razon, 0, 0, width=45)
        self._campo(form, "RUC (11 dígitos)", self.e_ruc, 0, 1)
        self._campo(form, "Dirección (máx. 50)", self.e_dir, 1, 0, width=45)
        self._campo(form, "Teléfono (9 dígitos)", self.e_tel, 1, 1)
        self._campo(form, "Cuenta corriente (solo dígitos)", self.e_cta, 2, 0, width=45)
        self.ub_empresa = SelectorUbigeo(form, self.catalogos)
        self.ub_empresa.grid(row=3, column=0, columnspan=2, sticky="ew", padx=2, pady=6)
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        btn = ttk.Frame(form)
        btn.grid(row=4, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(btn, text="Guardar datos de la empresa", style="Accent.TButton",
                   command=self.guardar_empresa).pack(side="left", padx=3)
        ttk.Button(btn, text="Recargar", command=self.cargar_empresa).pack(side="left", padx=3)
        ttk.Label(f, text="Estos datos se cargan automáticamente en cada nueva factura y en el PDF.",
                  style="Sub.TLabel").pack(anchor="w", pady=8)

    def cargar_empresa(self):
        emp = self._safe(self.empresas.obtener)
        self.empresa = emp
        self._ruc_empresa_guardado = emp["ruc_empresa"] if emp else None
        if emp:
            self.e_razon.set(emp["razon_social_empresa"])
            self.e_ruc.set(emp["ruc_empresa"])
            self.e_dir.set(emp["direccion_empresa"])
            self.e_tel.set(emp["telefono_empresa"])
            self.e_cta.set(str(emp["cuenta_corriente"]))
            self.ub_empresa.establecer(emp["id_distrito"])
            self.lbl_subtitulo.config(text=f'{emp["razon_social_empresa"]}  |  Gestión comercial')
        else:
            self.lbl_subtitulo.config(text="Empresa emisora sin configurar")
        self._pintar_emisor()

    def guardar_empresa(self):
        def op():
            id_distrito = self.ub_empresa.id_distrito()
            if id_distrito is None:
                raise ValidationError("Seleccione departamento, provincia y distrito de la empresa.")
            emp = Empresa(self.e_ruc.get(), self.e_razon.get(), self.e_dir.get(),
                          self.e_tel.get(), self.e_cta.get(), id_distrito)
            self.empresas.guardar(emp, self._ruc_empresa_guardado)
            self.cargar_empresa()
            messagebox.showinfo("Correcto", "Datos de la empresa guardados.", parent=self.ventana)
        self._safe(op)

    # ================================================================== NUEVA FACTURA
    def _ui_facturas(self):
        f = self.tab_facturas
        emi = ttk.LabelFrame(f, text="Empresa emisora", padding=8)
        emi.pack(fill="x")
        self.lbl_emisor = ttk.Label(emi, text="", style="Emisor.TLabel", justify="left")
        self.lbl_emisor.pack(side="left")
        ttk.Button(emi, text="Editar empresa", command=lambda: self.tabs.select(self.tab_empresa)).pack(side="right")

        cab = ttk.LabelFrame(f, text="Datos de la factura", padding=8)
        cab.pack(fill="x", pady=(8, 0))
        self.f_num, self.f_fecha = tk.StringVar(), tk.StringVar(value=date.today().isoformat())
        self.f_venc, self.f_igv = tk.StringVar(), tk.StringVar(value="0.18")
        self._campo(cab, "Número de factura", self.f_num, 0, 0)
        self._campo(cab, "Fecha emisión (AAAA-MM-DD)", self.f_fecha, 0, 1)
        self._campo(cab, "Vencimiento (opcional)", self.f_venc, 0, 2)
        self._campo(cab, "IGV (0.18 = 18%)", self.f_igv, 0, 3, width=12)
        self.cb_cliente = self._combo(cab, "Cliente", 1, 0, width=40)
        self.cb_moneda = self._combo(cab, "Moneda", 1, 1)
        self.cb_pago = self._combo(cab, "Forma de pago", 1, 2)
        self.cb_detraccion = self._combo(cab, "Detracción", 1, 3, width=34)
        for c in range(4):
            cab.columnconfigure(c, weight=1)
        ttk.Button(cab, text="Generar número", command=self.numero_siguiente).grid(row=2, column=0, sticky="w", padx=6)
        for cb in (self.cb_moneda, self.cb_detraccion):
            cb.bind("<<ComboboxSelected>>", lambda _e: self._pintar_items())
        self.f_igv.trace_add("write", lambda *_: self._pintar_items())

        det = ttk.LabelFrame(f, text="Agregar servicios", padding=8)
        det.pack(fill="x", pady=8)
        self.item_cant = tk.StringVar(value="1")
        ttk.Label(det, text="Servicio").pack(side="left")
        self.cb_servicio = ComboID(det, width=62)
        self.cb_servicio.pack(side="left", padx=6)
        ttk.Label(det, text="Cantidad").pack(side="left")
        ttk.Entry(det, textvariable=self.item_cant, width=8).pack(side="left", padx=6)
        ttk.Button(det, text="Agregar", command=self.agregar_item).pack(side="left", padx=4)
        ttk.Button(det, text="Quitar seleccionado", command=self.quitar_item).pack(side="left", padx=4)

        # La barra inferior se empaqueta ANTES que la tabla (side=bottom) para que el botón
        # «Registrar factura» siga visible aunque la ventana sea baja.
        bottom = ttk.Frame(f)
        bottom.pack(side="bottom", fill="x", pady=(8, 0))
        self.total_label = ttk.Label(bottom, text="", font=("Segoe UI", 11, "bold"))
        self.total_label.pack(side="left")
        self.btn_registrar = ttk.Button(bottom, text="Registrar factura", command=self.registrar_factura,
                                        style="Accent.TButton")
        self.btn_registrar.pack(side="right")
        self.btn_pdf_ultima = ttk.Button(bottom, text="Exportar PDF de la última", state="disabled",
                                         command=lambda: self._exportar_numero(self._ultima_factura))
        self.btn_pdf_ultima.pack(side="right", padx=8)
        self.items_tree = self._tabla(
            f, ("codigo", "descripcion", "cantidad", "precio", "importe"),
            ("Código", "Servicio", "Cantidad", "P. unitario", "Importe"), [80, 420, 90, 130, 130])
        self._pintar_items()

    def _pintar_emisor(self):
        if not hasattr(self, "lbl_emisor"):
            return
        e = self.empresa
        if not e:
            self.lbl_emisor.config(text="⚠ Aún no configuró la empresa emisora (pestaña «Empresa emisora»).")
            self.btn_registrar.state(["disabled"])
            return
        self.lbl_emisor.config(text=(
            f'{e["razon_social_empresa"]}   |   RUC {e["ruc_empresa"]}\n'
            f'{e["direccion_empresa"]}, {e["distrito"]} - {e["provincia"]} - {e["departamento"]}   |   '
            f'Tel. {e["telefono_empresa"]}   |   Cta. Cte. {e["cuenta_corriente"]}'))
        self.btn_registrar.state(["!disabled"])

    def _cargar_datos_factura(self):
        """Llena TODOS los combos de la vista desde MySQL, conservando la selección previa si existe."""
        previos = (self.cb_cliente.id(), self.cb_moneda.id(), self.cb_pago.id(),
                   self.cb_detraccion.id(), self.cb_servicio.id())
        datos = self._safe(lambda: (
            self.clientes.listar(), self.catalogos.listar_monedas(), self.catalogos.listar_formas_pago(),
            self.catalogos.listar_detracciones(), self.servicios.listar(), self.empresas.obtener()))
        if datos is None:
            return
        clientes, monedas, pagos, detracciones, servicios, empresa = datos
        self.empresa = empresa
        self._pintar_emisor()
        self.cb_cliente.cargar(clientes, "ruc_cliente", lambda r: f'{r["ruc_cliente"]} | {r["nombre_cliente"]}')
        self.cb_moneda.cargar(monedas, "id_moneda", lambda r: r["descripcion"])
        self.cb_pago.cargar(pagos, "id_forma_pago", lambda r: r["descripcion"])
        self.cb_detraccion.cargar(
            detracciones, "id_detraccion",
            lambda r: f'{r["servicio_detraccion"]} ({Decimal(r["detraccion_porcentaje"]) * 100:.0f}%)',
            vacio="Ninguna")
        self.cb_servicio.cargar(
            servicios, "codigo_servicio",
            lambda r: f'{r["codigo_servicio"]} | {r["descripcion_servicio"]} | {formato_importe(r["valor_unitario_servicio"])}')
        self._servicios_cache = servicios
        for cb, previo in zip((self.cb_cliente, self.cb_moneda, self.cb_pago, self.cb_detraccion, self.cb_servicio), previos):
            if previo is not None:
                cb.seleccionar(previo)
        if not self.f_num.get():
            self.numero_siguiente()
        self._pintar_items()

    def numero_siguiente(self):
        self._safe(lambda: self.f_num.set(self.facturas.siguiente_numero()))

    def agregar_item(self):
        try:
            fila = self.cb_servicio.fila()
            if fila is None:
                raise ValidationError("Seleccione un servicio.")
            try:
                cant = int(self.item_cant.get())
            except ValueError:
                raise ValidationError("La cantidad debe ser un número entero.")
            if not 1 <= cant <= 255:
                raise ValidationError("La cantidad debe estar entre 1 y 255.")
            cod = int(fila["codigo_servicio"])
            existente = next((x for x in self._items if x["codigo_servicio"] == cod), None)
            if existente:  # la clave del detalle es (servicio, factura): se suman cantidades
                if existente["cantidad"] + cant > 255:
                    raise ValidationError("La cantidad total de un servicio no puede superar 255.")
                existente["cantidad"] += cant
            else:
                self._items.append({"codigo_servicio": cod, "descripcion": fila["descripcion_servicio"],
                                    "cantidad": cant, "precio": Decimal(str(fila["valor_unitario_servicio"]))})
            self._pintar_items()
        except FacturacionError as e:
            messagebox.showerror("Datos inválidos", str(e), parent=self.ventana)

    def quitar_item(self):
        sel = self.items_tree.selection()
        if not sel:
            return
        cod = int(self.items_tree.item(sel[0], "values")[0])
        self._items = [x for x in self._items if x["codigo_servicio"] != cod]
        self._pintar_items()

    def _simbolo(self) -> str:
        fila = self.cb_moneda.fila()
        return simbolo_moneda(fila["descripcion"]) if fila else "S/"

    def _pintar_items(self):
        self.items_tree.delete(*self.items_tree.get_children())
        for x in self._items:
            imp = x["precio"] * x["cantidad"]
            self.items_tree.insert("", "end", values=(
                x["codigo_servicio"], x["descripcion"], x["cantidad"], f'{x["precio"]:,.2f}', f"{imp:,.2f}"))
        try:
            igv = a_decimal(self.f_igv.get(), "IGV")
        except ValidationError:
            igv = Decimal("0.00")
        det = self.cb_detraccion.fila()
        pct_det = Decimal(str(det["detraccion_porcentaje"])) if det else None
        t = calcular_totales([(x["cantidad"], x["precio"]) for x in self._items], igv, pct_det)
        s = self._simbolo()
        texto = f'Subtotal: {s} {t["subtotal"]:,.2f}    IGV: {s} {t["igv"]:,.2f}    Total: {s} {t["total"]:,.2f}'
        if pct_det:
            texto += f'    Detracción: {s} {t["detraccion"]:,.2f}'
        self.total_label.config(text=texto)

    def registrar_factura(self):
        def op():
            if not self.empresa:
                raise ValidationError("Configure primero la empresa emisora.")
            if not self._items:
                raise ValidationError("Agregue al menos un servicio.")
            for cb, nombre in ((self.cb_cliente, "un cliente"), (self.cb_moneda, "la moneda"),
                               (self.cb_pago, "la forma de pago")):
                if not cb.hay_seleccion():
                    raise ValidationError(f"Seleccione {nombre}.")
            venc = parsear_fecha(self.f_venc.get(), "vencimiento") if self.f_venc.get().strip() else None
            nueva = NuevaFactura(
                numero_factura=self.f_num.get().strip(),
                fecha_emision=parsear_fecha(self.f_fecha.get(), "fecha de emisión"),
                id_moneda=self.cb_moneda.id(), id_forma_pago=self.cb_pago.id(),
                ruc_empresa=self.empresa["ruc_empresa"], ruc_cliente=self.cb_cliente.id(),
                igv_porcentaje=a_decimal(self.f_igv.get(), "IGV"),
                fecha_vencimiento=venc, id_detraccion=self.cb_detraccion.id(),
                items=[ItemFactura(x["codigo_servicio"], x["cantidad"]) for x in self._items])
            res = self.facturas.registrar(nueva)  # cabecera + detalle en UNA transacción
            numero = res["numero_factura"]
            self._ultima_factura = numero
            self.btn_pdf_ultima.state(["!disabled"])
            self._items = []
            self.f_venc.set("")
            self._pintar_items()
            self.numero_siguiente()
            self.cargar_facturas()
            if messagebox.askyesno(
                    "Factura registrada",
                    f'La factura {numero} se registró correctamente.\nTotal: {self._simbolo()} {res["total"]:,.2f}\n\n'
                    "¿Desea exportarla a PDF ahora?", parent=self.ventana):
                self._exportar_numero(numero)
        self._safe(op)

    # ================================================================== FACTURAS REGISTRADAS
    def _ui_consulta(self):
        f = self.tab_consulta
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filtrar por RUC de cliente (opcional):").pack(side="left")
        self.q_ruc = tk.StringVar()
        ttk.Entry(bar, textvariable=self.q_ruc, width=22).pack(side="left", padx=6)
        ttk.Button(bar, text="Buscar", command=self.cargar_facturas).pack(side="left")
        ttk.Button(bar, text="Ver detalle", command=self.ver_detalle).pack(side="left", padx=5)
        ttk.Button(bar, text="Exportar PDF", command=self.exportar_pdf, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(bar, text="Actualizar", command=self.cargar_facturas).pack(side="left")
        self.tree_facturas = self._tabla(
            f, ("numero", "fecha", "cliente", "ruc", "moneda", "subtotal", "igv", "total", "estado"),
            ("Número", "Emisión", "Cliente", "RUC", "Moneda", "Subtotal", "IGV", "Total", "Estado"),
            [130, 90, 220, 110, 100, 90, 80, 100, 150])
        self.tree_facturas.bind("<Double-1>", lambda _e: self.ver_detalle())

    def cargar_facturas(self):
        rows = self._safe(lambda: self.facturas.listar(self.q_ruc.get().strip() or None))
        if rows is None:
            return
        self.tree_facturas.delete(*self.tree_facturas.get_children())
        for r in rows:
            self.tree_facturas.insert("", "end", iid=r["numero_factura"], values=(
                r["numero_factura"], r["fecha_emision"], r["nombre_cliente"], r["ruc_cliente"], r["moneda"],
                formato_importe(r["subtotal"]), formato_importe(r["igv_calculado"]),
                formato_importe(r["total"]), r["estado_vencimiento"]))

    def _numero_seleccionado(self):
        sel = self.tree_facturas.selection()
        if not sel:
            messagebox.showwarning("Atención", "Seleccione una factura.", parent=self.ventana)
            return None
        return sel[0]

    def exportar_pdf(self):
        numero = self._numero_seleccionado()
        if numero:
            self._exportar_numero(numero)

    def _exportar_numero(self, numero):
        if not numero:
            return
        datos = self._safe(lambda: self.facturas.consultar(numero))
        if not datos:
            return
        ruta = filedialog.asksaveasfilename(
            parent=self.ventana, title="Guardar factura en PDF", initialfile=f"Factura_{numero}.pdf",
            defaultextension=".pdf", filetypes=[("Documento PDF", "*.pdf")])
        if not ruta:
            return
        try:
            exportar_factura_pdf(datos, ruta)
        except Exception as e:  # noqa: BLE001
            log.exception("No se pudo exportar la factura %s", numero)
            messagebox.showerror("Error al exportar", str(e), parent=self.ventana)
            return
        if messagebox.askyesno("PDF generado", f"La factura {numero} se exportó correctamente.\n\n{ruta}\n\n¿Abrir el archivo?",
                               parent=self.ventana):
            try:
                os.startfile(ruta)  # type: ignore[attr-defined]  # Windows
            except AttributeError:
                import subprocess, sys
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ruta])
            except OSError as e:
                messagebox.showwarning("No se pudo abrir", str(e), parent=self.ventana)

    def ver_detalle(self):
        numero = self._numero_seleccionado()
        if not numero:
            return
        data = self._safe(lambda: self.facturas.consultar(numero))
        if not data:
            return
        c = data["cabecera"]
        win = tk.Toplevel(self.ventana)
        win.title(f"Detalle de factura {numero}")
        win.geometry("850x500")
        win.configure(bg="#f3f6fb")
        s = simbolo_moneda(c.get("moneda"))
        ttk.Label(win, text=f'{numero}  |  {c.get("nombre_cliente")}  |  Total: {s} {c.get("total"):,.2f}',
                  font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=15, pady=12)
        t = self._tabla(win, ("codigo", "servicio", "cantidad", "precio", "importe"),
                        ("Código", "Servicio", "Cantidad", "Precio aplicado", "Valor venta"), [90, 350, 100, 130, 130])
        for r in data["items"]:
            t.insert("", "end", values=(r["codigo_servicio"], r["descripcion_servicio"], r["cantidad"],
                                        formato_importe(r["precio_unitario_aplicado"]), formato_importe(r["valor_venta"])))

    # ================================================================== REPORTES
    def _ui_reportes(self):
        f = self.tab_reportes
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="Reporte:").pack(side="left")
        self.cb_reporte = ttk.Combobox(
            bar, state="readonly", width=42,
            values=["Total facturado por cliente", "Servicios más solicitados", "Facturas con detracción",
                    "Resumen por moneda", "Resumen por forma de pago", "Ventas e IGV por mes"])
        self.cb_reporte.current(0)
        self.cb_reporte.pack(side="left", padx=7)
        ttk.Button(bar, text="Generar", command=self.generar_reporte, style="Accent.TButton").pack(side="left")
        self.tree_reportes = self._tabla(f, ("a",), ("Resultado",), [200])

    def generar_reporte(self):
        funcs = {
            "Total facturado por cliente": self.reportes.total_facturado_por_cliente,
            "Servicios más solicitados": self.reportes.servicios_mas_solicitados,
            "Facturas con detracción": self.reportes.facturas_con_detraccion,
            "Resumen por moneda": self.reportes.resumen_por_moneda,
            "Resumen por forma de pago": self.reportes.resumen_por_forma_pago,
            "Ventas e IGV por mes": self.reportes.ventas_e_igv_por_mes}
        rows = self._safe(funcs[self.cb_reporte.get()])
        if rows is None:
            return
        self.tree_reportes.delete(*self.tree_reportes.get_children())
        if not rows:
            messagebox.showinfo("Sin datos", "El reporte no devolvió resultados.", parent=self.ventana)
            return
        cols = list(rows[0].keys())
        self.tree_reportes["columns"] = cols
        for k in cols:
            self.tree_reportes.heading(k, text=k.replace("_", " ").title())
            self.tree_reportes.column(k, width=160, anchor="w")
        for r in rows:
            self.tree_reportes.insert("", "end", values=[r.get(k) for k in cols])

    # ================================================================== ciclo de vida
    def cerrar(self):
        self.ventana.destroy()

    def ejecutar(self):
        self.ventana.mainloop()
