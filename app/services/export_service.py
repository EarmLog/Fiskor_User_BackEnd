# ============================================================
# Exportacion de datos a Excel y documentos a PDF/Word.
#   - Excel con pandas + openpyxl (planillas, reportes, libros).
#   - PDF con reportlab (facturas fiscales con logo y sello).
#   - Word con python-docx (facturas y documentos editables).
#
# Todo se genera en disco (carpeta exportados/) y se devuelve la
# ruta para que el frontend la descargue.
# ============================================================
import logging
from datetime import datetime
from pathlib import Path

from app.config import Configuracion

registro = logging.getLogger("fiskor")


def _asegurar_carpeta(ruta: Path) -> Path:
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _marca_tiempo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ruta_absoluta_upload(ruta_relativa: str | None) -> Path | None:
    """Convierte una ruta relativa de uploads en ruta absoluta.

    Las imagenes (logo, sello, firma) se guardan como rutas relativas
    dentro de app/static/uploads. Si el archivo no existe, devolvemos
    None para que el documento se genere igual (sin imagen).
    """
    if not ruta_relativa:
        return None
    candidato = (Configuracion.RUTA_UPLOADS / ruta_relativa).resolve()
    return candidato if candidato.exists() else None


# ============================================================
# Excel
# ============================================================
def exportar_excel(filas: list[dict], titulo: str, nombre_base: str | None = None) -> str:
    """Escribe una lista de diccionarios en un archivo .xlsx.

    Aplica formato basico: encabezado en negrita y congelado, y ancho
    de columnas ajustado. Devuelve la ruta del archivo generado.
    """
    import pandas as pd

    carpeta = _asegurar_carpeta(Path(Configuracion.RUTA_EXPORTADOS) / "excel")
    nombre = nombre_base or f"{titulo.lower().replace(' ', '_')}_{_marca_tiempo()}"
    ruta = carpeta / f"{nombre}.xlsx"

    if not filas:
        filas = [{"Aviso": "Sin registros para exportar"}]
    dataframe = pd.DataFrame(filas)

    try:
        # Usamos openpyxl para dar formato de encabezado a la hoja.
        with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
            dataframe.to_excel(escritor, index=False, sheet_name=(titulo[:28] or "Reporte"))
            hoja = escritor.sheets[titulo[:28] or "Reporte"]
            hoja.freeze_panes = "A2"
            for celda in hoja[1]:
                celda.font = celda.font.copy(bold=True, color="FFFFFF")
                celda.fill = celda.fill.copy(fill_type="solid", fgColor="1D4ED8")
            for columna in hoja.columns:
                largo = max((len(str(c.value)) for c in columna if c.value is not None), default=10)
                hoja.column_dimensions[columna[0].column_letter].width = min(largo + 3, 45)
    except Exception as exc:  # pragma: no cover - respaldo si falla el formato
        registro.warning("Formato Excel avanzado no disponible, guardando simple: %s", exc)
        dataframe.to_excel(ruta, index=False, sheet_name=(titulo[:28] or "Reporte"))

    registro.info("Excel generado: %s", ruta)
    return str(ruta)


# ============================================================
# Helpers de formato de documentos
# ============================================================
def _datos_empresa(empresa: dict) -> dict:
    """Normaliza el diccionario de empresa para los documentos."""
    return {
        "nombre": empresa.get("nombre_fiscal") or empresa.get("nombre") or "Fiskor ERP",
        "nombre_comercial": empresa.get("nombre") or "",
        "rif": empresa.get("rif", ""),
        "direccion": empresa.get("direccion", ""),
        "telefono": empresa.get("telefono", ""),
        "email": empresa.get("email", ""),
        "serial_onat": empresa.get("serial_onat", ""),
        "pie": empresa.get("pie_documento", ""),
        "color": empresa.get("color_marca") or "#1d4ed8",
        "logo": ruta_absoluta_upload(empresa.get("logo_ruta")),
        "sello": ruta_absoluta_upload(empresa.get("sello_ruta")),
        "firma": ruta_absoluta_upload(empresa.get("firma_ruta")),
        "firma_nombre": empresa.get("firma_nombre", ""),
        "firma_cargo": empresa.get("firma_cargo", ""),
    }


def _fmt(valor, decimales: int = 2) -> str:
    """Formatea un numero con separador de miles."""
    try:
        return f"{float(valor):,.{decimales}f}"
    except (TypeError, ValueError):
        return "0,00"


# ============================================================
# PDF (reportlab)
# ============================================================
def generar_factura_pdf(empresa: dict, venta: dict, detalles: list[dict], plantilla: dict | None = None) -> str:
    """Genera la factura/nota de entrega en PDF con reportlab.

    Incluye encabezado fiscal, logo corporativo, tabla de productos,
    calculo de IVA/IGTF y un espacio al pie para el sello y la firma.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    datos = _datos_empresa(empresa)
    plantilla = plantilla or {}
    mostrar_logo = plantilla.get("mostrar_logo", True)
    mostrar_sello = plantilla.get("mostrar_sello", True)
    mostrar_firma = plantilla.get("mostrar_firma", True)
    mostrar_iva = plantilla.get("mostrar_iva", True)
    mostrar_igtf = plantilla.get("mostrar_igtf", True)

    color_marca = colors.HexColor(plantilla.get("color") or datos["color"] or "#1d4ed8")

    carpeta = _asegurar_carpeta(Path(Configuracion.RUTA_EXPORTADOS) / "pdf")
    numero = venta.get("numero_factura") or _marca_tiempo()
    nombre_archivo = f"factura_{str(numero).replace('/', '-')}.pdf"
    ruta = carpeta / nombre_archivo

    documento = SimpleDocTemplate(
        str(ruta),
        pagesize=letter,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.6 * cm,
        title=f"Factura {numero}",
        author=datos["nombre"],
    )

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("titulo", parent=estilos["Heading1"], fontSize=16, textColor=color_marca)
    estilo_sub = ParagraphStyle("sub", parent=estilos["Normal"], fontSize=8, textColor=colors.HexColor("#475569"))
    estilo_normal = ParagraphStyle("normal", parent=estilos["Normal"], fontSize=9)
    estilo_derecha = ParagraphStyle("der", parent=estilos["Normal"], fontSize=9, alignment=2)

    elementos = []

    # ---- Encabezado: logo a la izquierda, datos fiscales a la derecha ----
    encabezado_datos = [
        Paragraph(f"<b>{datos['nombre']}</b>", estilo_normal),
        Paragraph(f"RIF: {datos['rif'] or '—'}", estilo_sub),
        Paragraph(f"Direccion Fiscal: {datos['direccion'] or '—'}", estilo_sub),
        Paragraph(f"Telefono: {datos['telefono'] or '—'}  |  {datos['email'] or ''}", estilo_sub),
    ]
    if datos["serial_onat"]:
        encabezado_datos.append(Paragraph(f"Serial ONAT: {datos['serial_onat']}", estilo_sub))

    celda_logo = ""
    if mostrar_logo and datos["logo"]:
        try:
            celda_logo = Image(str(datos["logo"]), width=3.6 * cm, height=2.0 * cm, kind="proportional")
        except Exception as exc:  # pragma: no cover
            registro.warning("No se pudo incrustar el logo: %s", exc)

    tabla_encabezado = Table(
        [[celda_logo, encabezado_datos]],
        colWidths=[4.2 * cm, 12.0 * cm],
    )
    tabla_encabezado.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elementos.append(tabla_encabezado)
    elementos.append(Spacer(1, 0.2 * cm))
    elementos.append(HRFlowable(width="100%", thickness=1.2, color=color_marca))
    elementos.append(Spacer(1, 0.25 * cm))

    if plantilla.get("leyenda_superior"):
        elementos.append(Paragraph(plantilla["leyenda_superior"], estilo_sub))
        elementos.append(Spacer(1, 0.2 * cm))

    # ---- Titulo del documento ----
    tipo_doc = "NOTA DE ENTREGA" if venta.get("tipo") == "nota_entrega" else "FACTURA"
    if plantilla.get("titulo_encabezado"):
        tipo_doc = plantilla["titulo_encabezado"]
    titulo = Table(
        [
            [
                Paragraph(f"<b>{tipo_doc}</b>", estilo_titulo),
                Paragraph(
                    f"<b>N&deg;:</b> {numero}<br/>"
                    f"<b>Control:</b> {venta.get('numero_control') or '—'}<br/>"
                    f"<b>Fecha:</b> {venta.get('fecha') or ''}",
                    estilo_derecha,
                ),
            ]
        ],
        colWidths=[9.0 * cm, 7.2 * cm],
    )
    titulo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    elementos.append(titulo)
    elementos.append(Spacer(1, 0.3 * cm))

    # ---- Datos del cliente ----
    cliente_tabla = Table(
        [
            [Paragraph("<b>Cliente:</b>", estilo_normal), Paragraph(venta.get("cliente_nombre") or "Consumidor final", estilo_normal)],
            [Paragraph("<b>RIF/C.I.:</b>", estilo_normal), Paragraph(venta.get("cliente_rif") or "—", estilo_normal)],
            [Paragraph("<b>Condicion:</b>", estilo_normal), Paragraph(str(venta.get("condicion") or "contado").capitalize(), estilo_normal)],
            [Paragraph("<b>Tasa aplicada:</b>", estilo_normal), Paragraph(f"Bs. {_fmt(venta.get('tasa_aplicada'))} por USD", estilo_normal)],
        ],
        colWidths=[3.2 * cm, 13.0 * cm],
    )
    cliente_tabla.setStyle(
        TableStyle(
            [
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elementos.append(cliente_tabla)
    elementos.append(Spacer(1, 0.35 * cm))

    # ---- Tabla de productos ----
    cabecera = ["Descripcion", "Cant.", "P. Unit $"]
    if mostrar_iva:
        cabecera.append("IVA %")
    cabecera.append("Total $")

    filas = [cabecera]
    for detalle in detalles:
        fila = [
            Paragraph(str(detalle.get("descripcion") or ""), estilo_normal),
            _fmt(detalle.get("cantidad"), 2),
            _fmt(detalle.get("precio_unitario")),
        ]
        if mostrar_iva:
            fila.append(_fmt(detalle.get("iva_porcentaje"), 0))
        fila.append(_fmt(detalle.get("total")))
        filas.append(fila)

    anchos = [8.0 * cm, 1.8 * cm, 2.4 * cm]
    if mostrar_iva:
        anchos.append(1.6 * cm)
    anchos.append(2.4 * cm)

    tabla_productos = Table(filas, colWidths=anchos, repeatRows=1)
    tabla_productos.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), color_marca),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ]
        )
    )
    elementos.append(tabla_productos)
    elementos.append(Spacer(1, 0.3 * cm))

    # ---- Totales ----
    resumen = [
        ("Subtotal:", f"$ {_fmt(venta.get('subtotal'))}"),
        ("Descuento:", f"$ {_fmt(venta.get('descuento'))}"),
        ("Base imponible:", f"$ {_fmt(venta.get('base_imponible'))}"),
    ]
    if mostrar_iva:
        resumen.append(("IVA:", f"$ {_fmt(venta.get('iva'))}"))
    if mostrar_igtf and float(venta.get("igtf") or 0) > 0:
        resumen.append(("IGTF (Bs):", f"Bs. {_fmt(venta.get('igtf'))}"))
    resumen.append(("TOTAL USD:", f"$ {_fmt(venta.get('total_divisas'))}"))
    resumen.append(("TOTAL Bs.:", f"Bs. {_fmt(venta.get('total_bolivares'))}"))

    filas_totales = [
        [Paragraph(f"<b>{etiqueta}</b>", estilo_derecha), Paragraph(f"<b>{valor}</b>", estilo_derecha)]
        for etiqueta, valor in resumen
    ]
    tabla_totales = Table(filas_totales, colWidths=[4.0 * cm, 4.0 * cm], hAlign="RIGHT")
    tabla_totales.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LINEABOVE", (0, -2), (-1, -2), 0.8, color_marca),
            ]
        )
    )
    elementos.append(tabla_totales)
    elementos.append(Spacer(1, 0.5 * cm))

    # ---- Espacio reservado para sello y firma ----
    if mostrar_sello or mostrar_firma:
        elementos.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cbd5e1")))
        elementos.append(Spacer(1, 0.15 * cm))

        celda_sello = ""
        if mostrar_sello and datos["sello"]:
            try:
                celda_sello = Image(str(datos["sello"]), width=4.5 * cm, height=2.6 * cm, kind="proportional")
            except Exception as exc:  # pragma: no cover
                registro.warning("No se pudo incrustar el sello: %s", exc)
        elif mostrar_sello:
            celda_sello = Paragraph("<i>(Espacio reservado para el sello digital)</i>", estilo_sub)

        firma_partes = []
        if datos["firma"]:
            try:
                firma_partes.append(Image(str(datos["firma"]), width=4.0 * cm, height=1.4 * cm, kind="proportional"))
            except Exception:  # pragma: no cover
                pass
        firma_partes.append(Paragraph("_____________________________", estilo_normal))
        firma_partes.append(Paragraph("<b>Firma autorizada</b>", estilo_normal))
        if datos["firma_nombre"]:
            firma_partes.append(Paragraph(datos["firma_nombre"], estilo_sub))
        if datos["firma_cargo"]:
            firma_partes.append(Paragraph(datos["firma_cargo"], estilo_sub))

        celda_firma = firma_partes if mostrar_firma else ""
        tabla_pie = Table([[celda_sello, celda_firma]], colWidths=[9.0 * cm, 7.2 * cm])
        tabla_pie.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        elementos.append(tabla_pie)

    pie = datos["pie"] or plantilla.get("leyenda_inferior")
    if pie:
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(Paragraph(pie, estilo_sub))

    documento.build(elementos)
    registro.info("Factura PDF generada: %s", ruta)
    return str(ruta)


# ============================================================
# Word (python-docx)
# ============================================================
def generar_documento_word(titulo: str, empresa: dict, lineas: list[str], nombre_base: str | None = None) -> str:
    """Crea un documento .docx con encabezado de la empresa."""
    from docx import Document
    from docx.shared import Pt

    datos = _datos_empresa(empresa)
    carpeta = _asegurar_carpeta(Path(Configuracion.RUTA_EXPORTADOS) / "word")
    nombre = nombre_base or f"{titulo.lower().replace(' ', '_')}_{_marca_tiempo()}"
    ruta = carpeta / f"{nombre}.docx"

    documento = Document()
    if datos["logo"]:
        try:
            documento.add_picture(str(datos["logo"]), width=None)
        except Exception:  # pragma: no cover
            pass
    encabezado = documento.add_heading(datos["nombre"], level=0)
    encabezado.alignment = 1

    subtitulo = documento.add_paragraph()
    subtitulo.alignment = 1
    subtitulo.add_run(f"RIF: {datos['rif']}    |    {datos['direccion']}").font.size = Pt(9)

    documento.add_heading(titulo, level=2)
    for linea in lineas:
        documento.add_paragraph(str(linea))
    documento.save(ruta)
    registro.info("Documento Word generado: %s", ruta)
    return str(ruta)


def generar_factura_word(empresa: dict, venta: dict, detalles: list[dict]) -> str:
    """Genera una factura/nota de entrega en Word (editable)."""
    from docx import Document
    from docx.shared import Inches, Pt

    datos = _datos_empresa(empresa)
    carpeta = _asegurar_carpeta(Path(Configuracion.RUTA_EXPORTADOS) / "word")
    ruta = carpeta / f"factura_{venta.get('numero_factura', _marca_tiempo())}.docx"

    documento = Document()
    if datos["logo"]:
        try:
            documento.add_picture(str(datos["logo"]), width=Inches(1.5))
        except Exception:  # pragma: no cover
            pass

    titulo = documento.add_heading(datos["nombre"], level=0)
    titulo.alignment = 1
    info = documento.add_paragraph()
    info.alignment = 1
    info.add_run(
        f"RIF: {datos['rif']}\n{datos['direccion']}\nTelefono: {datos['telefono']}"
    ).font.size = Pt(9)

    tipo_doc = "FACTURA" if venta.get("tipo") == "factura" else "NOTA DE ENTREGA"
    documento.add_heading(f"{tipo_doc} N° {venta.get('numero_factura', '')}", level=2)

    documento.add_paragraph(f"Cliente: {venta.get('cliente_nombre', '')}")
    documento.add_paragraph(f"RIF/Cedula: {venta.get('cliente_rif', '')}")
    documento.add_paragraph(f"Fecha: {venta.get('fecha', '')}")
    documento.add_paragraph(f"Control: {venta.get('numero_control', '')}")

    tabla = documento.add_table(rows=1, cols=4)
    tabla.style = "Light Grid Accent 1"
    encabezados = tabla.rows[0].cells
    for indice, texto in enumerate(["Descripcion", "Cant.", "Precio $", "Total $"]):
        encabezados[indice].text = texto
    for detalle in detalles:
        celdas = tabla.add_row().cells
        celdas[0].text = str(detalle.get("descripcion", ""))
        celdas[1].text = str(detalle.get("cantidad", ""))
        celdas[2].text = _fmt(detalle.get("precio_unitario"))
        celdas[3].text = _fmt(detalle.get("total"))

    documento.add_paragraph()
    resumen = documento.add_paragraph()
    resumen.add_run(f"Subtotal: $ {_fmt(venta.get('subtotal'))}\n")
    resumen.add_run(f"IVA: $ {_fmt(venta.get('iva'))}\n")
    resumen.add_run(f"IGTF: Bs. {_fmt(venta.get('igtf'))}\n")
    resumen.add_run(f"TOTAL Bs.: {_fmt(venta.get('total_bolivares'))}\n")
    resumen.add_run(f"TOTAL $: {_fmt(venta.get('total_divisas'))}\n")
    resumen.add_run(f"Tasa aplicada: {_fmt(venta.get('tasa_aplicada'))} Bs/USD")

    # Espacio para el sello y la firma al pie.
    documento.add_paragraph()
    if datos["sello"]:
        try:
            documento.add_picture(str(datos["sello"]), width=Inches(1.8))
        except Exception:  # pragma: no cover
            pass
    firma = documento.add_paragraph()
    firma.add_run("\n_____________________________\n")
    firma.add_run(f"Firma autorizada: {datos['firma_nombre']} {datos['firma_cargo']}")

    documento.save(ruta)
    registro.info("Factura Word generada: %s", ruta)
    return str(ruta)
