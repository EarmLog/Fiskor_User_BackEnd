# ============================================================
# API de proveedores.
# ============================================================
from flask import Blueprint, request
from sqlalchemy import or_

from app.extensions import db
from app.models.terceros import Proveedor
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id, parametros_paginacion
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto, normalizar_rif, validar_rif

proveedores_bp = Blueprint("proveedores", __name__, url_prefix="/api/proveedores")


@proveedores_bp.route("", methods=["GET"])
@requiere_sesion
def listar():
    empresa_id = empresa_activa_id()
    busqueda = (request.args.get("buscar") or "").strip()
    pagina, por_pagina = parametros_paginacion()
    consulta = Proveedor.query.filter_by(empresa_id=empresa_id)
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(or_(Proveedor.nombre.ilike(patron), Proveedor.rif.ilike(patron)))
    total = consulta.count()
    proveedores = consulta.order_by(Proveedor.nombre).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    return exito({"items": [p.a_diccionario() for p in proveedores], "total": total}, "Proveedores")


@proveedores_bp.route("/<int:proveedor_id>", methods=["GET"])
@requiere_sesion
def obtener(proveedor_id: int):
    proveedor = Proveedor.query.get(proveedor_id)
    if proveedor is None:
        return error("Proveedor no encontrado", 404)
    return exito(proveedor.a_diccionario(), "Proveedor")


@proveedores_bp.route("", methods=["POST"])
@requiere_sesion
def crear():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 150)
    if not nombre:
        return error("El nombre del proveedor es obligatorio", 400)
    rif = normalizar_rif(datos.get("rif", ""))
    if rif:
        valido, mensaje = validar_rif(rif)
        if not valido:
            return error(mensaje, 400)
    proveedor = Proveedor(
        empresa_id=empresa_activa_id(),
        codigo=limpiar_texto(datos.get("codigo"), 20),
        nombre=nombre,
        rif=rif,
        direccion=limpiar_texto(datos.get("direccion"), 255),
        telefono=limpiar_texto(datos.get("telefono"), 40),
        email=limpiar_texto(datos.get("email"), 120),
        contacto=limpiar_texto(datos.get("contacto"), 120),
        contribuyente_especial=bool(datos.get("contribuyente_especial")),
        retencion_iva=float(datos.get("retencion_iva") or 75),
        retencion_islr=float(datos.get("retencion_islr") or 5),
        dias_credito=int(datos.get("dias_credito") or 30),
        activo=bool(datos.get("activo", True)),
    )
    db.session.add(proveedor)
    db.session.commit()
    registrar("crear", "proveedores", "proveedores", proveedor.id, nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(proveedor.a_diccionario(), "Proveedor creado", 201)


@proveedores_bp.route("/<int:proveedor_id>", methods=["PUT"])
@requiere_sesion
def actualizar(proveedor_id: int):
    proveedor = Proveedor.query.get(proveedor_id)
    if proveedor is None:
        return error("Proveedor no encontrado", 404)
    datos = request.get_json(silent=True) or {}
    if "nombre" in datos:
        proveedor.nombre = limpiar_texto(datos["nombre"], 150) or proveedor.nombre
    if "rif" in datos:
        rif = normalizar_rif(datos["rif"])
        if rif:
            valido, mensaje = validar_rif(rif)
            if not valido:
                return error(mensaje, 400)
        proveedor.rif = rif
    for campo in ("codigo", "direccion", "telefono", "email", "contacto"):
        if campo in datos:
            setattr(proveedor, campo, limpiar_texto(datos[campo], 255))
    for campo in ("retencion_iva", "retencion_islr", "dias_credito"):
        if campo in datos and datos[campo] is not None:
            setattr(proveedor, campo, float(datos[campo]))
    if "contribuyente_especial" in datos:
        proveedor.contribuyente_especial = bool(datos["contribuyente_especial"])
    if "activo" in datos:
        proveedor.activo = bool(datos["activo"])
    db.session.commit()
    registrar("modificar", "proveedores", "proveedores", proveedor.id, proveedor.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(proveedor.a_diccionario(), "Proveedor actualizado")


@proveedores_bp.route("/<int:proveedor_id>", methods=["DELETE"])
@requiere_sesion
def desactivar(proveedor_id: int):
    proveedor = Proveedor.query.get(proveedor_id)
    if proveedor is None:
        return error("Proveedor no encontrado", 404)
    proveedor.activo = False
    db.session.commit()
    registrar("eliminar", "proveedores", "proveedores", proveedor.id, proveedor.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(None, "Proveedor desactivado")
