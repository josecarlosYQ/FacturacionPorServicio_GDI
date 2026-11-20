"""Validaciones previas que reflejan los CHECK/tipos del esquema (mensajes claros antes de ir a MySQL)."""
import re
from datetime import date
from decimal import Decimal

from core.errors import ValidationError
from core.utils import MAX_DECIMAL_8_2

RE_RUC = re.compile(r"^[0-9]{11}$")
RE_NUMERO_FACTURA = re.compile(r"^[A-Z0-9]{4}-[0-9]{8}$")


def validar_ruc(ruc: str, campo: str = "RUC") -> str:
    ruc = (ruc or "").strip()
    if not RE_RUC.match(ruc):
        raise ValidationError(f"{campo} inválido: debe tener exactamente 11 dígitos.")
    return ruc


def validar_numero_factura(numero: str) -> str:
    numero = (numero or "").strip().upper()
    if not RE_NUMERO_FACTURA.match(numero):
        raise ValidationError("Número de factura inválido. Formato esperado: XXXX-00000000 (ej. F001-00000266).")
    return numero


def validar_texto(valor: str, campo: str, max_len: int) -> str:
    valor = (valor or "").strip()
    if not valor:
        raise ValidationError(f"'{campo}' es obligatorio.")
    if len(valor) > max_len:
        raise ValidationError(f"'{campo}' admite como máximo {max_len} caracteres.")
    return valor


def validar_entero_rango(valor, campo: str, minimo: int, maximo: int) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"'{campo}' debe ser un número entero.") from e
    if not (minimo <= n <= maximo):
        raise ValidationError(f"'{campo}' debe estar entre {minimo} y {maximo}.")
    return n


def validar_importe_positivo(valor: Decimal, campo: str) -> Decimal:
    if valor <= 0:
        raise ValidationError(f"'{campo}' debe ser mayor que cero.")
    if valor > MAX_DECIMAL_8_2:
        raise ValidationError(f"'{campo}' excede el máximo permitido ({MAX_DECIMAL_8_2}).")
    return valor


def validar_porcentaje(valor: Decimal, campo: str) -> Decimal:
    if not (Decimal("0") <= valor <= Decimal("1")):
        raise ValidationError(f"'{campo}' debe estar entre 0.00 y 1.00 (ej. 0.18 para 18 %).")
    return valor


def validar_rango_fechas(desde: date, hasta: date) -> None:
    if desde > hasta:
        raise ValidationError("La fecha 'desde' no puede ser posterior a la fecha 'hasta'.")


def validar_telefono(valor: str) -> str:
    valor = (valor or "").strip()
    if not re.match(r"^[0-9]{9}$", valor):
        raise ValidationError("Teléfono inválido: debe tener exactamente 9 dígitos.")
    return valor


def validar_cuenta_corriente(valor) -> int:
    texto = str(valor or "").strip()
    if not re.match(r"^[0-9]{1,11}$", texto):
        raise ValidationError("Cuenta corriente inválida: use solo dígitos (máximo 11).")
    return int(texto)
