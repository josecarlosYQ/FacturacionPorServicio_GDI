"""Modelos de dominio (dataclasses). Los importes son siempre Decimal."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Cliente:
    ruc_cliente: str
    nombre_cliente: str
    direccion_cliente: str
    id_distrito: int


@dataclass
class Servicio:
    codigo_servicio: int
    descripcion_servicio: str
    valor_unitario_servicio: Decimal


@dataclass
class ItemFactura:
    """Línea de detalle. Si precio_unitario es None se toma el valor vigente del servicio."""
    codigo_servicio: int
    cantidad: int
    precio_unitario: Optional[Decimal] = None


@dataclass
class NuevaFactura:
    numero_factura: str
    fecha_emision: date
    id_moneda: int
    id_forma_pago: int
    ruc_empresa: str
    ruc_cliente: str
    igv_porcentaje: Decimal = Decimal("0.18")
    fecha_vencimiento: Optional[date] = None
    id_detraccion: Optional[int] = None
    items: list[ItemFactura] = field(default_factory=list)


@dataclass
class Empresa:
    """Perfil de la empresa emisora (tabla `empresa`)."""
    ruc_empresa: str
    razon_social_empresa: str
    direccion_empresa: str
    telefono_empresa: str
    cuenta_corriente: str  # BIGINT en BD; se maneja como texto de dígitos en la interfaz
    id_distrito: int
