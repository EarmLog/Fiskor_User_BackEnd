# ============================================================
# API de empresa y parametros del sistema.
#   - Datos fiscales del negocio.
#   - Imagen corporativa (logo, sello, firma): subir/reemplazar.
#   - Configuracion general (salario minimo, IVA, IGTF, etc.).
# ============================================================
import uuid
from pathlib import Path

from flask import Blueprint, request, send_file
from werkzeug.utils import secure_filename

from app.config import Configuracion
from app.extensions import db
from app.models.empresa import Empresa, ParametroSistema
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id
from app.utils.fechas import a_fecha, periodo_ejercicio
from app.utils.respuestas import error, exito
from app.utils.seguridad import (
    ROL_ADMINISTRADOR,
    requiere_sesion,
    solo_administrador,
    usuario_actual,
)
from app.utils.validaciones import limpiar_texto, normalizar_rif, validar_rif

empresa_bp = Blueprint("empresa", __name__, url_prefix="/api/empresa")

# Imagenes permitidas para logo, sello y firma.
EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg", ".webp"}
TAMANO_MAX_IMAGEN = 5 * 1024 * 1024  # 5 MB por imagen

# Mapa: tipo logico -> (subcarpeta, campo del modelo)
TIPOS_IMAGEN = {
    "logo": ("logos", "logo_ruta"),
    "sello": ("sellos", "sello_ruta"),
    "firma": ("firmas", "firma_ruta"),
}


def _guardar_imagen(archivo, tipo: str) -> str:
    """Valida y guarda una imagen corporativa. Devuelve la ruta relativa.

    Lanza ValueError con un mensaje claro cuando el archivo no sirve.
    """
    subcarpeta, _ = TIPOS_IMAGEN[tipo]
    nombre_original = archivo.filename or ""
    extension = Path(nombre_original).suffix.lower()
    if extension not in EXTENSIONES_IMAGEN:
        raise ValueError("Formato no permitido. Use PNG, JPG o WEBP")

    # Validamos el tamano leyendo el archivo (el navegador no siempre
    # envia content-length en formularios multipart).
    contenido = archivo.read()
    if len(contenido) > TAMANO_MAX_IMAGEN:
        raise ValueError("La imagen supera el limite de 5 MB")
    if not contenido:
        raise ValueError("El archivo esta vacio")

    carpeta = Configuracion.RUTA_UPLOADS / subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre_seguro = secure_filename(nombre_original) or "imagen"
    # Nombre unico para no chocar con la imagen anterior y poder reemplazarla.
    nombre_final = f"{uuid.uuid4().hex[:10]}_{nombre_seguro}"
    destino = carpeta / nombre_final
    destino.write_bytes(contenido)
    return f"{subcarpeta}/{nombre_final}"


def _borrar_imagen(ruta_relativa: str) -> None:
    """Elimina una imagen anterior del disco (si existe)."""
    if not ruta_relativa:
        return
    try:
        candidato = (Configuracion.RUTA_UPLOADS / ruta_relativa).resolve()
        if candidato.exists() and candidato.is_file():
            candidato.unlink()
    except Exception:  # pragma: no cover
        pass


def _puede_gestionar(empresa: Empresa) -> bool:
    """True si el usuario puede editar la empresa (admin o su dueño)."""
    usuario = usuario_actual()
    if usuario.get("rol") == ROL_ADMINISTRADOR:
        return True
    correo = (usuario.get("email") or "").strip().lower()
    return (empresa.propietario_email or "").strip().lower() == correo


@empresa_bp.route("", methods=["GET"])
@requiere_sesion
def listar():
    """Lista las empresas del usuario (el admin ve todas)."""
    usuario = usuario_actual()
    if usuario.get("rol") == ROL_ADMINISTRADOR:
        empresas = Empresa.query.order_by(Empresa.codigo).all()
    else:
        correo = (usuario.get("email") or "").strip().lower()
        empresas = (
            Empresa.query.filter(db.func.lower(Empresa.propietario_email) == correo)
            .order_by(Empresa.codigo)
            .all()
        )
    return exito([empresa.a_diccionario() for empresa in empresas], "Empresas registradas")


@empresa_bp.route("/actual", methods=["GET"])
@requiere_sesion
def actual():
    """Devuelve la empresa del usuario conectado (su propio negocio)."""
    empresa_id = empresa_activa_id()
    empresa = Empresa.query.get(empresa_id) if empresa_id else None
    if empresa is None:
        empresa = Empresa.query.order_by(Empresa.id).first()
    if empresa is None:
        return error("No hay empresas registradas", 404)
    return exito(empresa.a_diccionario(), "Empresa activa")


@empresa_bp.route("", methods=["POST"])
@solo_administrador
def crear():
    """Registra una empresa nueva."""
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 120)
    if not nombre:
        return error("El nombre de la empresa es obligatorio", 400)

    rif = normalizar_rif(datos.get("rif", ""))
    if rif:
        valido, mensaje = validar_rif(rif)
        if not valido:
            return error(mensaje, 400)

    codigo = (datos.get("codigo") or "").strip()
    if not codigo:
        ultimo = Empresa.query.order_by(Empresa.id.desc()).first()
        codigo = f"{(ultimo.id + 1) if ultimo else 1:04d}"
    if Empresa.query.filter_by(codigo=codigo).first():
        return error("Ya existe una empresa con ese codigo", 409)

    # Si no envian fechas, usamos el ejercicio del anio en curso.
    from datetime import date

    if not datos.get("inicio_ejercicio"):
        inicio, cierre = periodo_ejercicio(date.today().year)
    else:
        inicio = a_fecha(datos.get("inicio_ejercicio"))
        cierre = a_fecha(datos.get("cierre_ejercicio")) or inicio

    empresa = Empresa(
        codigo=codigo,
        # El negocio queda a nombre del usuario que lo crea.
        propietario_email=(datos.get("propietario_email") or usuario_actual()["email"] or "").strip().lower(),
        nombre=nombre,
        nombre_fiscal=limpiar_texto(datos.get("nombre_fiscal"), 180),
        rif=rif,
        direccion=limpiar_texto(datos.get("direccion"), 255),
        telefono=limpiar_texto(datos.get("telefono"), 40),
        email=limpiar_texto(datos.get("email"), 120),
        inicio_ejercicio=inicio,
        cierre_ejercicio=cierre,
        contribuyente_especial=bool(datos.get("contribuyente_especial")),
        porcentaje_iva=float(datos.get("porcentaje_iva") or 16.0),
        porcentaje_igtf=float(datos.get("porcentaje_igtf") or 3.0),
        serial_onat=limpiar_texto(datos.get("serial_onat"), 60),
        activa=bool(datos.get("activa", True)),
    )
    db.session.add(empresa)
    db.session.commit()
    registrar("crear", "empresa", "empresas", empresa.id, nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(empresa.a_diccionario(), "Empresa registrada", 201)


@empresa_bp.route("/<int:empresa_id>", methods=["PUT"])
@requiere_sesion
def actualizar(empresa_id: int):
    """Actualiza los datos de una empresa."""
    empresa = Empresa.query.get(empresa_id)
    if empresa is None:
        return error("Empresa no encontrada", 404)
    if not _puede_gestionar(empresa):
        return error("No tiene permisos para modificar esta empresa", 403)
    datos = request.get_json(silent=True) or {}

    if "nombre" in datos:
        empresa.nombre = limpiar_texto(datos["nombre"], 120) or empresa.nombre
    if "nombre_fiscal" in datos:
        empresa.nombre_fiscal = limpiar_texto(datos["nombre_fiscal"], 180)
    if "rif" in datos:
        rif = normalizar_rif(datos["rif"])
        if rif:
            valido, mensaje = validar_rif(rif)
            if not valido:
                return error(mensaje, 400)
        empresa.rif = rif
    for campo in ("direccion", "telefono", "email", "serial_onat"):
        if campo in datos:
            setattr(empresa, campo, limpiar_texto(datos[campo], 255))
    # Identidad de los documentos (formato de factura/nota).
    for campo in ("firma_nombre", "firma_cargo"):
        if campo in datos:
            setattr(empresa, campo, limpiar_texto(datos[campo], 120))
    if "color_marca" in datos:
        color = limpiar_texto(datos["color_marca"], 10)
        # Aceptamos solo colores hex validos (#RRGGBB).
        empresa.color_marca = color if color.startswith("#") and len(color) == 7 else empresa.color_marca
    if "pie_documento" in datos:
        empresa.pie_documento = limpiar_texto(datos["pie_documento"], 500)
    if "inicio_ejercicio" in datos:
        empresa.inicio_ejercicio = a_fecha(datos["inicio_ejercicio"])
    if "cierre_ejercicio" in datos:
        empresa.cierre_ejercicio = a_fecha(datos["cierre_ejercicio"])
    if "contribuyente_especial" in datos:
        empresa.contribuyente_especial = bool(datos["contribuyente_especial"])
    if "porcentaje_iva" in datos:
        empresa.porcentaje_iva = float(datos["porcentaje_iva"] or 16.0)
    if "porcentaje_igtf" in datos:
        empresa.porcentaje_igtf = float(datos["porcentaje_igtf"] or 3.0)
    if "activa" in datos:
        empresa.activa = bool(datos["activa"])

    db.session.commit()
    registrar("modificar", "empresa", "empresas", empresa.id, "Actualizacion de empresa",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(empresa.a_diccionario(), "Empresa actualizada")


# ------------------------------------------------------------
# Imagen corporativa: logo, sello digital y firma autorizada
# ------------------------------------------------------------
@empresa_bp.route("/<int:empresa_id>/imagenes/<string:tipo>", methods=["POST"])
@requiere_sesion
def subir_imagen(empresa_id: int, tipo: str):
    """Sube (o reemplaza) el logo, sello o firma de la empresa.

    Recibe multipart/form-data con el campo 'archivo'. La imagen se
    guarda en BackEnd/app/static/uploads y la ruta se ancla en la BD.
    """
    if tipo not in TIPOS_IMAGEN:
        return error("Tipo de imagen no valido (use logo, sello o firma)", 400)

    empresa = Empresa.query.get(empresa_id)
    if empresa is None:
        return error("Empresa no encontrada", 404)
    if not _puede_gestionar(empresa):
        return error("No tiene permisos para modificar esta empresa", 403)

    archivo = request.files.get("archivo")
    if archivo is None:
        return error("Debe adjuntar una imagen", 400)

    _, campo = TIPOS_IMAGEN[tipo]
    ruta_anterior = getattr(empresa, campo)
    try:
        ruta_relativa = _guardar_imagen(archivo, tipo)
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception:
        return error("No se pudo guardar la imagen", 500)

    # Guardamos la nueva y borramos la anterior para no acumular basura.
    setattr(empresa, campo, ruta_relativa)
    db.session.commit()
    _borrar_imagen(ruta_anterior)

    registrar("modificar", "empresa", "empresas", empresa.id, f"Imagen {tipo} actualizada",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(empresa.a_diccionario(), f"{tipo.capitalize()} actualizado")


@empresa_bp.route("/<int:empresa_id>/imagenes/<string:tipo>", methods=["DELETE"])
@requiere_sesion
def borrar_imagen(empresa_id: int, tipo: str):
    """Quita el logo, sello o firma de la empresa."""
    if tipo not in TIPOS_IMAGEN:
        return error("Tipo de imagen no valido", 400)
    empresa = Empresa.query.get(empresa_id)
    if empresa is None:
        return error("Empresa no encontrada", 404)
    if not _puede_gestionar(empresa):
        return error("No tiene permisos para modificar esta empresa", 403)

    _, campo = TIPOS_IMAGEN[tipo]
    _borrar_imagen(getattr(empresa, campo))
    setattr(empresa, campo, "")
    db.session.commit()
    registrar("modificar", "empresa", "empresas", empresa.id, f"Imagen {tipo} eliminada",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(empresa.a_diccionario(), f"{tipo.capitalize()} eliminado")


@empresa_bp.route("/<int:empresa_id>/imagenes/<string:tipo>", methods=["GET"])
def obtener_imagen(empresa_id: int, tipo: str):
    """Sirve la imagen corporativa (para <img> del frontend y documentos).

    Es publica porque el navegador la carga en etiquetas <img> que no
    pueden enviar el token. Solo expone logos/sellos de la empresa.
    """
    if tipo not in TIPOS_IMAGEN:
        return error("Tipo de imagen no valido", 404)
    empresa = Empresa.query.get(empresa_id)
    if empresa is None:
        return error("Empresa no encontrada", 404)

    _, campo = TIPOS_IMAGEN[tipo]
    ruta_relativa = getattr(empresa, campo)
    if not ruta_relativa:
        return error("La empresa no tiene esa imagen configurada", 404)

    ruta = (Configuracion.RUTA_UPLOADS / ruta_relativa).resolve()
    if not ruta.exists():
        return error("La imagen ya no esta disponible en el disco", 404)
    return send_file(ruta, max_age=60)


@empresa_bp.route("/parametros", methods=["GET"])
@requiere_sesion
def obtener_parametros():
    """Devuelve todos los parametros del sistema."""
    parametros = {p.clave: p.valor for p in ParametroSistema.query.all()}
    return exito(parametros, "Parametros del sistema")


@empresa_bp.route("/parametros", methods=["PUT"])
@solo_administrador
def guardar_parametros():
    """Actualiza uno o varios parametros del sistema."""
    datos = request.get_json(silent=True) or {}
    for clave, valor in datos.items():
        ParametroSistema.guardar(str(clave), str(valor))
    db.session.commit()
    registrar("modificar", "empresa", "parametros_sistema", None, "Actualizacion de parametros",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito({p.clave: p.valor for p in ParametroSistema.query.all()}, "Parametros actualizados")
