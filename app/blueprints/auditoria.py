# ============================================================
# API de auditoria (trazas de las operaciones).
# Solo visible para administradores y contadores.
# ============================================================
from flask import Blueprint, request

from app.models.seguridad import Auditoria
from app.utils.respuestas import exito
from app.utils.seguridad import requiere_rol

auditoria_bp = Blueprint("auditoria", __name__, url_prefix="/api/auditoria")


@auditoria_bp.route("", methods=["GET"])
@requiere_rol("Administrador", "Contador")
def listar():
    """Lista las trazas de auditoria con filtros opcionales."""
    consulta = Auditoria.query
    modulo = request.args.get("modulo")
    usuario = request.args.get("usuario")
    accion = request.args.get("accion")
    if modulo:
        consulta = consulta.filter_by(modulo=modulo)
    if usuario:
        consulta = consulta.filter(Auditoria.usuario_email.ilike(f"%{usuario}%"))
    if accion:
        consulta = consulta.filter_by(accion=accion)
    trazas = consulta.order_by(Auditoria.id.desc()).limit(300).all()
    return exito([t.a_diccionario() for t in trazas], "Trazas de auditoria")