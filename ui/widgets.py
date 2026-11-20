"""Widgets reutilizables: Combobox con ID interno y selector de ubigeo en cascada."""
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Optional


class ComboID(ttk.Combobox):
    """Combobox de solo lectura que muestra un texto y devuelve el ID interno asociado.

    Se usa el índice de selección (current()) en lugar de interpretar el texto, así el
    texto visible puede contener cualquier carácter sin romper el vínculo con el ID.
    """

    def __init__(self, master, **kw):
        kw.setdefault("state", "readonly")
        self._var = kw.pop("textvariable", None) or tk.StringVar(master=master)
        super().__init__(master, textvariable=self._var, **kw)
        self._ids: list[Any] = []
        self._filas: list[Optional[dict]] = []

    def cargar(self, filas: Iterable[dict], id_key: str, texto: Callable[[dict], str],
               vacio: Optional[str] = None, seleccionar_primero: bool = True) -> None:
        """Rellena el combo. `vacio` agrega una primera opción sin ID (por ejemplo 'Ninguna')."""
        filas = list(filas)
        self._ids, self._filas, etiquetas = [], [], []
        if vacio is not None:
            self._ids.append(None); self._filas.append(None); etiquetas.append(vacio)
        for f in filas:
            self._ids.append(f[id_key]); self._filas.append(f); etiquetas.append(texto(f))
        self["values"] = etiquetas
        if etiquetas and seleccionar_primero:
            self.current(0)
        else:
            self._var.set("")

    def id(self):
        i = self.current()
        return self._ids[i] if 0 <= i < len(self._ids) else None

    def fila(self) -> Optional[dict]:
        i = self.current()
        return self._filas[i] if 0 <= i < len(self._filas) else None

    def hay_seleccion(self) -> bool:
        return self.current() >= 0

    def seleccionar(self, valor) -> bool:
        for i, v in enumerate(self._ids):
            if v == valor:
                self.current(i)
                return True
        return False

    def limpiar(self) -> None:
        self._var.set("")
        try:
            self.selection_clear()
        except tk.TclError:
            pass


class SelectorUbigeo(ttk.Frame):
    """Departamento -> Provincia -> Distrito en cascada, alimentado por la base de datos."""

    def __init__(self, master, catalogos, on_change: Optional[Callable] = None):
        super().__init__(master)
        self._cat = catalogos
        self._on_change = on_change
        self.cb_dep, self.cb_prov, self.cb_dist = (ComboID(self, width=24) for _ in range(3))
        for col, (txt, cb) in enumerate((("Departamento", self.cb_dep), ("Provincia", self.cb_prov),
                                         ("Distrito", self.cb_dist))):
            ttk.Label(self, text=txt).grid(row=0, column=col, sticky="w", padx=4)
            cb.grid(row=1, column=col, padx=4, sticky="ew")
            self.columnconfigure(col, weight=1)
        self.cb_dep.bind("<<ComboboxSelected>>", lambda _e: self._cargar_provincias())
        self.cb_prov.bind("<<ComboboxSelected>>", lambda _e: self._cargar_distritos())
        self.cb_dist.bind("<<ComboboxSelected>>", lambda _e: self._notificar())
        self.recargar()

    def _notificar(self):
        if self._on_change:
            self._on_change()

    def recargar(self) -> None:
        self.cb_dep.cargar(self._cat.listar_departamentos(), "id_departamento", lambda r: r["nombre"],
                           seleccionar_primero=False)
        self.cb_prov.cargar([], "id_provincia", lambda r: r["nombre"])
        self.cb_dist.cargar([], "id_distrito", lambda r: r["nombre"])

    def _cargar_provincias(self, seleccionar=True):
        dep = self.cb_dep.id()
        filas = self._cat.listar_provincias(dep) if dep is not None else []
        self.cb_prov.cargar(filas, "id_provincia", lambda r: r["nombre"], seleccionar_primero=False)
        self.cb_dist.cargar([], "id_distrito", lambda r: r["nombre"])

    def _cargar_distritos(self):
        prov = self.cb_prov.id()
        filas = self._cat.listar_distritos_de(prov) if prov is not None else []
        self.cb_dist.cargar(filas, "id_distrito", lambda r: r["nombre"], seleccionar_primero=False)

    def id_distrito(self) -> Optional[int]:
        return self.cb_dist.id()

    def establecer(self, id_distrito: Optional[int]) -> None:
        """Preselecciona departamento, provincia y distrito a partir de un id_distrito guardado."""
        if id_distrito is None:
            self.limpiar()
            return
        ub = self._cat.ubicacion_de_distrito(int(id_distrito))
        if not ub:
            self.limpiar()
            return
        self.cb_dep.seleccionar(ub["id_departamento"]); self._cargar_provincias()
        self.cb_prov.seleccionar(ub["id_provincia"]); self._cargar_distritos()
        self.cb_dist.seleccionar(ub["id_distrito"])

    def limpiar(self) -> None:
        self.cb_dep.limpiar()
        self.cb_prov.cargar([], "id_provincia", lambda r: r["nombre"])
        self.cb_dist.cargar([], "id_distrito", lambda r: r["nombre"])
