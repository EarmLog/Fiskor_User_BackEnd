# ============================================================
# API de gestion de usuarios (solo Administrador).
# Los usuarios viven en Supabase; aqui se orquesta su CRUD.
# ============================================================
from flask import Blueprint, request

from app.services import auth_service
from app.services.auditoria_service import registrar
from app.utils.respuestas import error, exito
from app.utils.seguridad import ROLES_VALIDOS, requiere_rol, solo_administrador, usuario_actual
from app.utils.validaciones import validar_email

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/api/usuarios")


@usuarios_bp.route("", methods=["GET"])
@requiere_rol("Administrador", "Contador")
def listar():
    """Lista todos los usuarios del sistema."""
    try:
        return exito(auth_service.listar_usuarios(), "Usuarios del sistema")
    except Exception:
        return error("No se pudo obtener la lista de usuarios", 502)


@usuarios_bp.route("", methods=["POST"])
@solo_administrador
def crear():
    """Crea un usuario nuevo."""
    datos = request.get_json(silent=True) or {}
    valido, mensaje = validar_email(datos.get("email"))
    if not valido:
        return error(mensaje, 400)
    if not datos.get("nombre"):
        return error("El nombre es obligatorio", 400)
    if not datos.get("password") or len(str(datos["password"])) < 6:
        return error("La contrasena debe tener al menos 6 caracteres", 400)
    if datos.get("rol") not in ROLES_VALIDOS:
        return error("El rol indicado no es valido", 400)

    try:
        creado = auth_service.crear_usuario(dict(datos))
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 400)
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplic" in str(exc).lower():
            return error("Ya existe un usuario con ese correo", 409)
        return error("No se pudo crear el usuario", 500)

    registrar("crear", "usuarios", "fiskor_usuarios", creado.get("id"), datos.get("email", ""),
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(creado, "Usuario creado con exito", 201)


@usuarios_bp.route("/<int:usuario_id>", methods=["PUT"])
@solo_administrador
def actualizar(usuario_id: int):
    """Actualiza los datos de un usuario."""
    datos = request.get_json(silent=True) or {}
    if "email" in datos and datos["email"]:
        valido, mensaje = validar_email(datos["email"])
        if not valido:
            return error(mensaje, 400)
    if "rol" in datos and datos["rol"] not in ROLES_VALIDOS:
        return error("El rol indicado no es valido", 400)
    try:
        actualizado = auth_service.actualizar_usuario(usuario_id, dict(datos))
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 400)
    if not actualizado:
        return error("Usuario no encontrado", 404)
    registrar("modificar", "usuarios", "fiskor_usuarios", usuario_id, "Actualizacion de usuario",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(actualizado, "Usuario actualizado")


@usuarios_bp.route("/<int:usuario_id>", methods=["DELETE"])
@solo_administrador
def eliminar(usuario_id: int):
    """Elimina un usuario."""
    # Evitamos que el administrador se borre a si mismo.
    if str(usuario_actual()["id"]) == str(usuario_id):
        return error("No puede eliminar su propio usuario", 400)
    try:
        eliminado = auth_service.eliminar_usuario(usuario_id)
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 400)
    if not eliminado:
        return error("Usuario no encontrado", 404)
    registrar("eliminar", "usuarios", "fiskor_usuarios", usuario_id, "Eliminacion de usuario",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(None, "Usuario eliminado")
