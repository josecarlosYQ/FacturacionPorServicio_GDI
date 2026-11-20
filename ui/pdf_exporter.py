"""Generación de facturas en PDF (A4) a partir de los datos persistidos en MySQL.

Entrada: {'cabecera': {...}, 'items': [...]} tal como lo devuelve FacturaDAO.consultar().
"""
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.utils import monto_en_letras, simbolo_moneda

AZUL = colors.HexColor("#17365D")
CELESTE = colors.HexColor("#EAF0F7")
GRIS = colors.HexColor("#52627A")
LINEA = colors.HexColor("#C8D2DF")
ANCHO_UTIL = A4[0] - 34 * mm


def _t(valor, defecto="—") -> str:
    return escape(str(valor)) if valor not in (None, "") else defecto


def _dinero(valor) -> str:
    return f"{Decimal(str(valor or 0)):,.2f}"


def _fecha(valor) -> str:
    if not valor:
        return "—"
    return valor.strftime("%d/%m/%Y") if hasattr(valor, "strftime") else str(valor)


def _estilos() -> dict:
    base = getSampleStyleSheet()["Normal"]

    def mk(nombre, **k):
        return ParagraphStyle(nombre, parent=base, **k)

    return {
        "empresa": mk("empresa", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=AZUL),
        "datos": mk("datos", fontSize=8.5, leading=11.5, textColor=GRIS),
        "caja_tit": mk("caja_tit", fontName="Helvetica-Bold", fontSize=9, leading=12,
                       textColor=colors.white, alignment=TA_CENTER),
        "caja_num": mk("caja_num", fontName="Helvetica-Bold", fontSize=13, leading=16,
                       textColor=AZUL, alignment=TA_CENTER),
        "caja_ruc": mk("caja_ruc", fontSize=10, leading=13, alignment=TA_CENTER),
        "sec": mk("sec", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=AZUL),
        "txt": mk("txt", fontSize=8.5, leading=11.5),
        "lbl": mk("lbl", fontName="Helvetica-Bold", fontSize=8.5, leading=11.5, textColor=AZUL),
        "der": mk("der", fontSize=8.5, leading=11.5, alignment=TA_RIGHT),
        "cen": mk("cen", fontSize=8.5, leading=11.5, alignment=TA_CENTER),
        "th": mk("th", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                 textColor=colors.white, alignment=TA_CENTER),
        "letras": mk("letras", fontName="Helvetica-Bold", fontSize=8.5, leading=11.5),
    }


def _cabecera_documento(c: dict, s: dict) -> Table:
    emisor = [
        Paragraph(_t(c.get("razon_social_empresa")).upper(), s["empresa"]),
        Paragraph(_t(c.get("direccion_empresa")), s["datos"]),
        Paragraph(_t(c.get("ubicacion_empresa"), ""), s["datos"]),
        Paragraph(f"Teléfono: {_t(c.get('telefono_empresa'))}", s["datos"]),
        Paragraph(f"Cuenta corriente: {_t(c.get('cuenta_corriente'))}", s["datos"]),
    ]
    caja = Table(
        [[Paragraph("FACTURA", s["caja_tit"])],
         [Paragraph(f"RUC {_t(c.get('ruc_empresa'))}", s["caja_ruc"])],
         [Paragraph(_t(c.get("numero_factura")), s["caja_num"])]],
        colWidths=[58 * mm],
    )
    caja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL), ("BOX", (0, 0), (-1, -1), 1, AZUL),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    t = Table([[emisor, caja]], colWidths=[ANCHO_UTIL - 60 * mm, 60 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0),
                           ("RIGHTPADDING", (-1, 0), (-1, 0), 0)]))
    return t


def _fila_pares(pares: list, s: dict) -> Table:
    """Tabla de 4 columnas (etiqueta, valor, etiqueta, valor)."""
    filas = []
    for i in range(0, len(pares), 2):
        fila = []
        for etiqueta, valor in pares[i:i + 2]:
            fila += [Paragraph(etiqueta, s["lbl"]), Paragraph(_t(valor), s["txt"])]
        while len(fila) < 4:
            fila += ["", ""]
        filas.append(fila)
    mitad = ANCHO_UTIL / 2
    t = Table(filas, colWidths=[30 * mm, mitad - 30 * mm, 30 * mm, mitad - 30 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINEA), ("INNERGRID", (0, 0), (-1, -1), 0.3, LINEA),
        ("BACKGROUND", (0, 0), (0, -1), CELESTE), ("BACKGROUND", (2, 0), (2, -1), CELESTE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def exportar_factura_pdf(datos: dict, ruta: str) -> None:
    """Crea el PDF de una factura en `ruta`."""
    c = datos["cabecera"]
    items = datos.get("items", [])
    s = _estilos()
    sim = simbolo_moneda(c.get("moneda"))

    doc = SimpleDocTemplate(
        ruta, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=14 * mm, bottomMargin=18 * mm,
        title=f"Factura {c.get('numero_factura', '')}", author=str(c.get("razon_social_empresa") or ""),
    )

    story = [_cabecera_documento(c, s), Spacer(1, 6 * mm)]
    story += [Paragraph("DATOS DEL DOCUMENTO", s["sec"]), Spacer(1, 1.5 * mm), _fila_pares([
        ("Fecha de emisión", _fecha(c.get("fecha_emision"))),
        ("Fecha de vencimiento", _fecha(c.get("fecha_vencimiento"))),
        ("Moneda", c.get("moneda")), ("Forma de pago", c.get("forma_pago")),
    ], s), Spacer(1, 4 * mm)]
    story += [Paragraph("DATOS DEL CLIENTE", s["sec"]), Spacer(1, 1.5 * mm), _fila_pares([
        ("Cliente", c.get("nombre_cliente")), ("RUC", c.get("ruc_cliente")),
        ("Dirección", c.get("direccion_cliente")), ("Ubicación", c.get("ubicacion_cliente")),
    ], s), Spacer(1, 5 * mm)]

    encabezados = ("Código", "Descripción", "Cant.", f"P. unitario ({sim})", f"Importe ({sim})")
    filas = [[Paragraph(h, s["th"]) for h in encabezados]]
    for it in items:
        filas.append([
            Paragraph(_t(it.get("codigo_servicio")), s["cen"]),
            Paragraph(_t(it.get("descripcion_servicio")), s["txt"]),
            Paragraph(_t(it.get("cantidad")), s["cen"]),
            Paragraph(_dinero(it.get("precio_unitario_aplicado")), s["der"]),
            Paragraph(_dinero(it.get("valor_venta")), s["der"]),
        ])
    anchos = [18 * mm, 0, 16 * mm, 34 * mm, 34 * mm]
    anchos[1] = ANCHO_UTIL - sum(anchos)
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL), ("GRID", (0, 0), (-1, -1), 0.35, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FB")]),
    ]))
    story += [Paragraph("DETALLE", s["sec"]), Spacer(1, 1.5 * mm), tabla, Spacer(1, 4 * mm)]

    pct_igv = (Decimal(str(c.get("igv_porcentaje") or 0)) * 100).normalize()
    totales = [("Subtotal (valor de venta)", f"{sim} {_dinero(c.get('subtotal'))}"),
               (f"IGV ({pct_igv:f}%)", f"{sim} {_dinero(c.get('igv_calculado'))}"),
               ("IMPORTE TOTAL", f"{sim} {_dinero(c.get('total'))}")]
    tt = Table([[Paragraph(a, s["lbl"]), Paragraph(b, s["der"])] for a, b in totales],
               colWidths=[52 * mm, 38 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 1.1, AZUL), ("BACKGROUND", (0, -1), (-1, -1), CELESTE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    bloque = [tt, Spacer(1, 3 * mm),
              Paragraph(escape(monto_en_letras(c.get("total"), c.get("moneda") or "")), s["letras"])]

    if c.get("id_detraccion") and Decimal(str(c.get("detraccion_porcentaje") or 0)) > 0:
        pct = (Decimal(str(c["detraccion_porcentaje"])) * 100).normalize()
        det = Table([[Paragraph(
            "<b>Operación sujeta a detracción (SPOT).</b><br/>"
            f"Concepto: {_t(c.get('servicio_detraccion'))} &nbsp;|&nbsp; Porcentaje: {pct:f}% "
            f"&nbsp;|&nbsp; Monto a depositar: {sim} {_dinero(c.get('monto_detraccion'))}", s["txt"])]],
            colWidths=[ANCHO_UTIL])
        det.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, AZUL), ("BACKGROUND", (0, 0), (-1, -1), CELESTE),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        bloque += [Spacer(1, 4 * mm), det]
    story.append(KeepTogether(bloque))

    emisor = str(c.get("razon_social_empresa") or "")
    nro = str(c.get("numero_factura") or "")

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setStrokeColor(LINEA)
        canvas.line(17 * mm, 13 * mm, A4[0] - 17 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRIS)
        canvas.drawString(17 * mm, 8.5 * mm, f"{emisor}  |  Factura {nro}")
        canvas.drawRightString(A4[0] - 17 * mm, 8.5 * mm, f"Página {documento.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=pie, onLaterPages=pie)
