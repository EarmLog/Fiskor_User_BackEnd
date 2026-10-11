# ============================================================
# API de empresa y parametros del sistema.
#   - Datos fiscales del negocio.
#   - Configuracion general (salario minimo, IVA, IGTF, etc.).
# ============================================================
from flask import Blueprint, request

from app.extensions import db
from app.models.empresa import Empresa, ParametroSistema
from app.services.auditoria_service import registrar
from app.utils.fechas import a_fecha, periodo_ejercicio
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, solo_administrador, usuario_actual
from app.utils.validaciones import limpiar_texto, normalizar_rif, validar_rif

empresa_bp = Blueprint("empresa", __name__, url_prefix="/api/empresa")


@empresa_bp.route("", methods=["GET"])
@requiere_sesion
def listar():
    """Lista las empresas registradas."""
    empresas = Empresa.query.order_by(Empresa.codigo).all()
    return exito([empresa.a_diccionario() for empresa in empresas], "Empresas registradas")


@empresa_bp.route("/actual", methods=["GET"])
@requiere_sesion
def actual():
    """Devuelve la empresa activa (la primera activa o la primera)."""
    empresa = Empresa.query.filter_by(activa=True).order_by(Empresa.id).first()
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
@solo_administrador
def actualizar(empresa_id: int):
    """Actualiza los datos de una empresa."""
    empresa = Empresa.query.get(empresa_id)
    if empresa is None:
        return error("Empresa no encontrada", 404)
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
