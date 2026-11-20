"""Punto de entrada de la aplicación gráfica.

Flujo de arranque:
  1. Lee config.json y prueba la conexión a MySQL.
  2. Si no existe, es inválido o la conexión falla -> pantalla de configuración (instala la BD).
  3. Si la conexión es correcta pero faltan tablas/catálogos -> reaplica el script (es idempotente).
  4. Abre la ventana principal.
"""
import logging
import sys

from core.config import DBConfig, cargar_config
from core.database import Database
from core.errors import FacturacionError
from core.paths import ruta_externa
from core.setup_db import catalogos_completos, instalar_base_datos, probar_conexion

log = logging.getLogger("facturacion")


def configurar_logging():
    formato = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    try:
        logging.basicConfig(level=logging.INFO, format=formato,
                            handlers=[logging.FileHandler(ruta_externa("facturacion.log"), encoding="utf-8")])
    except OSError:
        logging.basicConfig(level=logging.WARNING, format=formato)
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)


def _config_guardada_y_valida() -> tuple[DBConfig | None, DBConfig | None, str]:
    """Devuelve (config_valida, config_previa_para_prellenar, motivo_si_falla)."""
    try:
        cfg = cargar_config()
    except FacturacionError as e:
        log.info("Sin configuración utilizable: %s", e)
        return None, None, ""
    try:
        probar_conexion(cfg, con_bd=True)
        return cfg, cfg, ""
    except FacturacionError as e:
        log.warning("config.json existe pero la conexión falló: %s", e)
        return None, cfg, f"La configuración guardada no funcionó:\n{e}\n\nRevise los datos e intente de nuevo."


def obtener_configuracion() -> DBConfig | None:
    cfg, previo, motivo = _config_guardada_y_valida()
    if cfg is not None:
        if not catalogos_completos(cfg):
            log.info("BD incompleta: se reaplica el script SQL")
            instalar_base_datos(cfg)
        return cfg
    from ui.config_ventana import VentanaConfigBD
    return VentanaConfigBD(previo=previo, motivo=motivo).ejecutar()


def main() -> int:
    configurar_logging()
    db = None
    try:
        config = obtener_configuracion()
        if config is None:
            return 0  # el usuario canceló la configuración
        db = Database(config)
        db.connection()
        log.info("Conexión establecida con MySQL (%s@%s/%s)", config.user, config.host, config.database)
        from ui.tkinter_app import AplicacionTk
        AplicacionTk(db).ejecutar()
        return 0
    except FacturacionError as e:
        log.exception("No se pudo iniciar la aplicación")
        _error("Error de configuración o conexión", str(e))
        return 1
    except Exception:
        log.exception("Error fatal")
        _error("Error inesperado", "No se pudo iniciar la aplicación. Revise facturacion.log.")
        return 2
    finally:
        if db is not None:
            db.close()


def _error(titulo: str, mensaje: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showerror(titulo, mensaje)
        r.destroy()
    except Exception:
        print(f"{titulo}: {mensaje}")


if __name__ == "__main__":
    sys.exit(main())
