# ============================================================
# API de clientes.
# ============================================================
from flask import Blueprint, request
from sqlalchemy import or_

from app.extensions import db
from app.models.terceros import Cliente
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id, parametros_paginacion
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto, normalizar_rif, validar_rif

clientes_bp = Blueprint("clientes", __name__, url_prefix="/api/clientes")


@clientes_bp.route("", methods=["GET"])
@requiere_sesion
def listar():
    empresa_id = empresa_activa_id()
    busqueda = (request.args.get("buscar") or "").strip()
    pagina, por_pagina = parametros_paginacion()
    consulta = Cliente.query.filter_by(empresa_id=empresa_id)
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(or_(Cliente.nombre.ilike(patron), Cliente.rif.ilike(patron)))
    total = consulta.count()
    clientes = consulta.order_by(Cliente.nombre).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    return exito({"items": [c.a_diccionario() for c in clientes], "total": total}, "Clientes")


@clientes_bp.route("/<int:cliente_id>", methods=["GET"])
@requiere_sesion
def obtener(cliente_id: int):
    cliente = Cliente.query.get(cliente_id)
    if cliente is None:
        return error("Cliente no encontrado", 404)
    return exito(cliente.a_diccionario(), "Cliente")


@clientes_bp.route("", methods=["POST"])
@requiere_sesion
def crear():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 150)
    if not nombre:
        return error("El nombre del cliente es obligatorio", 400)
    rif = normalizar_rif(datos.get("rif", ""))
    if rif:
        valido, mensaje = validar_rif(rif)
        if not valido:
            return error(mensaje, 400)
    empresa_id = empresa_activa_id()
    cliente = Cliente(
        empresa_id=empresa_id,
        codigo=limpiar_texto(datos.get("codigo"), 20),
        nombre=nombre,
        rif=rif,
        tipo_documento=limpiar_texto(datos.get("tipo_documento"), 20) or "RIF",
        direccion=limpiar_texto(datos.get("direccion"), 255),
        telefono=limpiar_texto(datos.get("telefono"), 40),
        email=limpiar_texto(datos.get("email"), 120),
        contribuyente_especial=bool(datos.get("contribuyente_especial")),
        retencion_iva=float(datos.get("retencion_iva") or 0),
        limite_credito=float(datos.get("limite_credito") or 0),
        activo=bool(datos.get("activo", True)),
    )
    db.session.add(cliente)
    db.session.commit()
    registrar("crear", "clientes", "clientes", cliente.id, nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(cliente.a_diccionario(), "Cliente creado", 201)


@clientes_bp.route("/<int:cliente_id>", methods=["PUT"])
@requiere_sesion
def actualizar(cliente_id: int):
    cliente = Cliente.query.get(cliente_id)
    if cliente is None:
        return error("Cliente no encontrado", 404)
    datos = request.get_json(silent=True) or {}
    if "nombre" in datos:
        cliente.nombre = limpiar_texto(datos["nombre"], 150) or cliente.nombre
    if "rif" in datos:
        rif = normalizar_rif(datos["rif"])
        if rif:
            valido, mensaje = validar_rif(rif)
            if not valido:
                return error(mensaje, 400)
        cliente.rif = rif
    for campo in ("codigo", "tipo_documento", "direccion", "telefono", "email"):
        if campo in datos:
            setattr(cliente, campo, limpiar_texto(datos[campo], 255))
    for campo in ("retencion_iva", "limite_credito"):
        if campo in datos and datos[campo] is not None:
            setattr(cliente, campo, float(datos[campo]))
    if "contribuyente_especial" in datos:
        cliente.contribuyente_especial = bool(datos["contribuyente_especial"])
    if "activo" in datos:
        cliente.activo = bool(datos["activo"])
    db.session.commit()
    registrar("modificar", "clientes", "clientes", cliente.id, cliente.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(cliente.a_diccionario(), "Cliente actualizado")


@clientes_bp.route("/<int:cliente_id>", methods=["DELETE"])
@requiere_sesion
def desactivar(cliente_id: int):
    cliente = Cliente.query.get(cliente_id)
    if cliente is None:
        return error("Cliente no encontrado", 404)
    cliente.activo = False
    db.session.commit()
    registrar("eliminar", "clientes", "clientes", cliente.id, cliente.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(None, "Cliente desactivado")
