"""Pantalla inicial de configuración de la base de datos (first-run setup)."""
import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from core.config import DBConfig, guardar_config
from core.errors import FacturacionError
from core.setup_db import BD_POR_DEFECTO, instalar_base_datos, leer_script, nombre_bd_del_script

log = logging.getLogger("facturacion.ui.config")


class VentanaConfigBD(tk.Tk):
    """Pide host, puerto, usuario y contraseña; instala la BD con el script SQL y guarda config.json.

    Tras `mainloop()`, `self.resultado` contiene el DBConfig guardado, o None si se canceló.
    """

    def __init__(self, previo: Optional[DBConfig] = None, motivo: str = ""):
        super().__init__()
        self.resultado: Optional[DBConfig] = None
        self.title("Factura Pe | Configuración de base de datos")
        self.resizable(False, False)
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg="#f3f6fb")
        st.configure("TFrame", background="#f3f6fb")
        st.configure("TLabel", background="#f3f6fb", font=("Segoe UI", 10))
        st.configure("T.TLabel", font=("Segoe UI", 16, "bold"), foreground="#17365d")
        st.configure("S.TLabel", foreground="#52627a")
        st.configure("A.TButton", background="#17365d", foreground="white", padding=8)
        st.map("A.TButton", background=[("active", "#24558c")])

        self.v_host = tk.StringVar(value=previo.host if previo else "localhost")
        self.v_port = tk.StringVar(value=str(previo.port) if previo else "3306")
        self.v_user = tk.StringVar(value=previo.user if previo else "root")
        self.v_pass = tk.StringVar(value="")
        self.v_estado = tk.StringVar(value="")

        marco = ttk.Frame(self, padding=22)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Configuración de la base de datos", style="T.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ayuda = motivo or ("Ingrese los datos de su servidor MySQL. No necesita crear la base de datos: "
                           "la aplicación la creará con las tablas y los datos maestros.")
        ttk.Label(marco, text=ayuda, style="S.TLabel", wraplength=420, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

        campos = [("Host", self.v_host, None), ("Puerto", self.v_port, None),
                  ("Usuario", self.v_user, None), ("Contraseña", self.v_pass, "•")]
        self._entradas = []
        for i, (txt, var, ocultar) in enumerate(campos, start=2):
            ttk.Label(marco, text=txt).grid(row=i, column=0, sticky="w", pady=5)
            e = ttk.Entry(marco, textvariable=var, width=34, show=ocultar or "")
            e.grid(row=i, column=1, sticky="ew", pady=5, padx=(12, 0))
            self._entradas.append(e)

        ttk.Label(marco, textvariable=self.v_estado, style="S.TLabel", wraplength=420).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        botones = ttk.Frame(marco)
        botones.grid(row=8, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self.btn_guardar = ttk.Button(botones, text="Guardar y conectar", style="A.TButton", command=self._guardar)
        self.btn_guardar.pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right", padx=8)

        self.bind("<Return>", lambda _e: self._guardar())
        self._entradas[3 if previo else 2].focus_set()
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}+{(self.winfo_screenheight() - h) // 3}")

    def _guardar(self):
        host, user = self.v_host.get().strip(), self.v_user.get().strip()
        if not host or not user:
            messagebox.showwarning("Datos incompletos", "Host y usuario son obligatorios.", parent=self)
            return
        try:
            puerto = int(self.v_port.get().strip())
            if not 1 <= puerto <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Puerto inválido", "El puerto debe ser un número entre 1 y 65535.", parent=self)
            return

        self.btn_guardar.state(["disabled"])
        self.configure(cursor="watch")
        self.v_estado.set("Conectando y creando la base de datos…")
        self.update_idletasks()
        try:
            nombre_bd = nombre_bd_del_script(leer_script())
            config = DBConfig(host=host, user=user, password=self.v_pass.get(),
                              database=nombre_bd or BD_POR_DEFECTO, port=puerto)

            def progreso(i, n):
                self.v_estado.set(f"Ejecutando script SQL… {i}/{n}")
                self.update_idletasks()

            nombre_bd = instalar_base_datos(config, progreso)
            config = DBConfig(host=host, user=user, password=self.v_pass.get(), database=nombre_bd, port=puerto)
            guardar_config(config)
        except FacturacionError as e:
            log.exception("Fallo en la configuración inicial")
            self.v_estado.set("")
            messagebox.showerror("No se pudo configurar la base de datos", str(e), parent=self)
        except Exception as e:  # noqa: BLE001
            log.exception("Error inesperado en la configuración inicial")
            self.v_estado.set("")
            messagebox.showerror("Error inesperado", str(e), parent=self)
        else:
            self.resultado = config
            self.destroy()
            return
        finally:
            try:
                self.configure(cursor="")
                self.btn_guardar.state(["!disabled"])
            except tk.TclError:
                pass  # la ventana ya se cerró

    def ejecutar(self) -> Optional[DBConfig]:
        self.mainloop()
        return self.resultado
