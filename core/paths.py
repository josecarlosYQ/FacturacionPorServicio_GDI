"""Resolución segura de rutas, tanto en desarrollo como dentro de un .exe de PyInstaller."""
import os
import sys


def esta_congelado() -> bool:
    """True cuando el programa corre empaquetado con PyInstaller (sys.frozen)."""
    return bool(getattr(sys, "frozen", False))


def directorio_base() -> str:
    """Carpeta donde viven los archivos EXTERNOS (config.json, logs).

    - Como .exe: la carpeta del ejecutable (NO la carpeta temporal _MEIPASS).
    - En desarrollo: la raíz del proyecto.
    """
    if esta_congelado():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_externa(*partes: str) -> str:
    """Ruta absoluta a un archivo que el usuario puede editar junto al ejecutable."""
    return os.path.join(directorio_base(), *partes)


def ruta_recurso(*partes: str) -> str:
    """Ruta a recursos EMPAQUETADOS dentro del .exe (se extraen a sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", directorio_base())
    return os.path.join(base, *partes)
