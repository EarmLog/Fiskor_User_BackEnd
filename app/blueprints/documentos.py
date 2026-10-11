# ============================================================
# API de formatos/plantillas de documentos.
# Permite "montar" un formato por tipo de documento (factura,
# nota de entrega, recibo, retencion) y editarlo o reemplazarlo.
# ============================================================
from flask import Blueprint, request

from app.extensions import db
from app.models.documentos import PlantillaDocumento
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, solo_administrador, usuario_actual
from app.utils.validaciones import limpiar_texto

documentos_bp = Blueprint("documentos", __name__, url_prefix="/api/documentos")

TIPOS_VALIDOS = ("factura", "nota_entrega", "recibo", "retencion", "cotizacion")
CAMPOS_BOOLEANOS = (
    "mostrar_logo",
    "mostrar_sello",
    "mostrar_firma",
    "mostrar_iva",
    "mostrar_igtf",
    "mostrar_datos_bancarios",
    "activo",
)


@documentos_bp.route("/plantillas", methods=["GET"])
@requiere_sesion
def listar_plantillas():
    """Lista los formatos de la empresa (opcionalmente por tipo)."""
    empresa_id = empresa_activa_id()
    tipo = request.args.get("tipo")
    consulta = PlantillaDocumento.query.filter_by(empresa_id=empresa_id)
    if tipo:
        consulta = consulta.filter_by(tipo=tipo)
    plantillas = consulta.order_by(PlantillaDocumento.tipo).all()
    return exito([p.a_diccionario() for p in plantillas], "Formatos de documentos")


@documentos_bp.route("/plantillas", methods=["POST"])
@requiere_sesion
def crear_plantilla():
    """Crea un formato nuevo para la empresa."""
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "factura").lower()
    if tipo not in TIPOS_VALIDOS:
        return error("Tipo de documento no valido", 400)

    plantilla = PlantillaDocumento(
        empresa_id=empresa_activa_id(),
        tipo=tipo,
        nombre=limpiar_texto(datos.get("nombre"), 120) or "Formato personalizado",
        titulo_encabezado=limpiar_texto(datos.get("titulo_encabezado"), 150),
        leyenda_superior=limpiar_texto(datos.get("leyenda_superior"), 500),
        leyenda_inferior=limpiar_texto(datos.get("leyenda_inferior"), 500),
        datos_bancarios=limpiar_texto(datos.get("datos_bancarios"), 500),
        color=_color_valido(datos.get("color")) or "#1d4ed8",
    )
    _aplicar_booleanos(plantilla, datos)
    db.session.add(plantilla)
    db.session.commit()
    registrar("crear", "documentos", "plantillas_documento", plantilla.id, plantilla.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(plantilla.a_diccionario(), "Formato creado", 201)


@documentos_bp.route("/plantillas/<int:plantilla_id>", methods=["PUT"])
@requiere_sesion
def actualizar_plantilla(plantilla_id: int):
    """Actualiza un formato existente (editar/reemplazar)."""
    plantilla = PlantillaDocumento.query.get(plantilla_id)
    if plantilla is None:
        return error("Formato no encontrado", 404)
    datos = request.get_json(silent=True) or {}

    if "tipo" in datos and datos["tipo"] in TIPOS_VALIDOS:
        plantilla.tipo = datos["tipo"]
    if "nombre" in datos:
        plantilla.nombre = limpiar_texto(datos["nombre"], 120) or plantilla.nombre
    if "titulo_encabezado" in datos:
        plantilla.titulo_encabezado = limpiar_texto(datos["titulo_encabezado"], 150)
    if "leyenda_superior" in datos:
        plantilla.leyenda_superior = limpiar_texto(datos["leyenda_superior"], 500)
    if "leyenda_inferior" in datos:
        plantilla.leyenda_inferior = limpiar_texto(datos["leyenda_inferior"], 500)
    if "datos_bancarios" in datos:
        plantilla.datos_bancarios = limpiar_texto(datos["datos_bancarios"], 500)
    if "color" in datos:
        plantilla.color = _color_valido(datos["color"]) or plantilla.color
    _aplicar_booleanos(plantilla, datos)

    db.session.commit()
    registrar("modificar", "documentos", "plantillas_documento", plantilla.id, plantilla.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(plantilla.a_diccionario(), "Formato actualizado")


@documentos_bp.route("/plantillas/<int:plantilla_id>", methods=["DELETE"])
@solo_administrador
def eliminar_plantilla(plantilla_id: int):
    """Elimina un formato."""
    plantilla = PlantillaDocumento.query.get(plantilla_id)
    if plantilla is None:
        return error("Formato no encontrado", 404)
    db.session.delete(plantilla)
    db.session.commit()
    registrar("eliminar", "documentos", "plantillas_documento", plantilla_id, "Formato eliminado",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(None, "Formato eliminado")


def _color_valido(valor) -> str:
    """Devuelve un color hexadecimal valido o cadena vacia."""
    texto = str(valor or "").strip()
    if texto.startswith("#") and len(texto) == 7:
        try:
            int(texto[1:], 16)
            return texto
        except ValueError:
            return ""
    return ""


def _aplicar_booleanos(plantilla: PlantillaDocumento, datos: dict) -> None:
    """Copia los interruptores booleanos presentes en la peticion."""
    for campo in CAMPOS_BOOLEANOS:
        if campo in datos:
            setattr(plantilla, campo, bool(datos[campo]))
