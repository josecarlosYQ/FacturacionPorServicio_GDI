"""Utilidades de importes monetarios (siempre Decimal, nunca float) y fechas."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from core.errors import ValidationError

CENTAVO = Decimal("0.01")
MAX_DECIMAL_8_2 = Decimal("999999.99")


def a_decimal(valor, campo: str = "importe") -> Decimal:
    """Convierte str/int/float/Decimal a Decimal con 2 decimales (ROUND_HALF_UP, como ROUND de MySQL)."""
    if isinstance(valor, bool) or valor is None:
        raise ValidationError(f"'{campo}' no es un número válido.")
    try:
        d = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError(f"'{campo}' no es un número válido: {valor!r}") from e
    if not d.is_finite():
        raise ValidationError(f"'{campo}' no es un número válido.")
    return d.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_totales(items, igv_porcentaje: Decimal, detraccion_porcentaje: Decimal | None) -> dict:
    """Vista previa en Python de lo que calcularán los triggers (la BD sigue siendo la fuente de verdad).

    items: iterable de (cantidad: int, precio_unitario: Decimal)
    """
    subtotal = sum((redondear(Decimal(c) * p) for c, p in items), Decimal("0.00"))
    igv = redondear(subtotal * igv_porcentaje)
    total = redondear(subtotal + igv)
    detraccion = redondear(total * detraccion_porcentaje) if detraccion_porcentaje is not None else Decimal("0.00")
    return {"subtotal": subtotal, "igv": igv, "total": total, "detraccion": detraccion}


def formato_importe(valor) -> str:
    if valor is None:
        return ""
    return f"{Decimal(valor):,.2f}"


def parsear_fecha(texto: str, campo: str = "fecha") -> date:
    """Acepta AAAA-MM-DD o DD/MM/AAAA."""
    texto = (texto or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"'{campo}' no es una fecha válida (use AAAA-MM-DD o DD/MM/AAAA).")


# ---------------------------------------------------------------- importe en letras (facturas)
_UNIDADES = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
             "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISEIS", "DIECISIETE", "DIECIOCHO",
             "DIECINUEVE", "VEINTE", "VEINTIUNO", "VEINTIDOS", "VEINTITRES", "VEINTICUATRO",
             "VEINTICINCO", "VEINTISEIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
_DECENAS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_CENTENAS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS",
             "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]


def _menor_mil(n: int) -> str:
    if n == 100:
        return "CIEN"
    partes = []
    c, resto = divmod(n, 100)
    if c:
        partes.append(_CENTENAS[c])
    if resto < 30:
        if resto:
            partes.append(_UNIDADES[resto])
    else:
        d, u = divmod(resto, 10)
        partes.append(_DECENAS[d] + (f" Y {_UNIDADES[u]}" if u else ""))
    return " ".join(partes)


def numero_en_letras(n: int) -> str:
    if n == 0:
        return "CERO"
    if n >= 1_000_000_000:
        raise ValueError("Número demasiado grande")
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append("UN MILLON" if millones == 1 else f"{_menor_mil(millones)} MILLONES")
    if miles:
        partes.append("MIL" if miles == 1 else f"{_menor_mil(miles).replace('UNO', 'UN')} MIL")
    if unidades:
        partes.append(_menor_mil(unidades))
    return " ".join(partes)


def monto_en_letras(importe, moneda: str = "") -> str:
    """Ej.: 'SON: CIENTO DIECIOCHO CON 00/100 SOLES'."""
    d = a_decimal(importe, "importe")
    entero, centavos = int(d), int((d - int(d)) * 100)
    nombre = "DOLARES AMERICANOS" if "USD" in (moneda or "").upper() or "LAR" in (moneda or "").upper() else "SOLES"
    return f"SON: {numero_en_letras(entero)} CON {centavos:02d}/100 {nombre}"


def simbolo_moneda(moneda: str) -> str:
    m = (moneda or "").upper()
    return "US$" if ("USD" in m or "LAR" in m) else "S/"
