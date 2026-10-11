# ============================================================
# Control de acceso basado en roles (RBAC).
# Los roles del sistema son: Administrador, Cajero y Contador.
# ============================================================
from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.utils.respuestas import error

# Roles reconocidos por Fiskor.
ROL_ADMINISTRADOR = "Administrador"
ROL_CAJERO = "Cajero"
ROL_CONTADOR = "Contador"
ROLES_VALIDOS = (ROL_ADMINISTRADOR, ROL_CAJERO, ROL_CONTADOR)


def _cargar_usuario_en_contexto():
    """Deja la informacion del token disponible en flask.g."""
    datos = get_jwt()
    g.usuario_id = datos.get("sub")
    g.usuario_email = datos.get("email")
    g.usuario_rol = datos.get("rol", ROL_CAJERO)


def usuario_actual() -> dict:
    """Devuelve los datos basicos del usuario autenticado."""
    return {
        "id": getattr(g, "usuario_id", None),
        "email": getattr(g, "usuario_email", None),
        "rol": getattr(g, "usuario_rol", ROL_CAJERO),
    }


def requiere_sesion(funcion):
    """Exige que la peticion traiga un token valido."""

    @wraps(funcion)
    def envoltura(*args, **kwargs):
        verify_jwt_in_request()
        _cargar_usuario_en_contexto()
        return funcion(*args, **kwargs)

    return envoltura


def requiere_rol(*roles_permitidos):
    """Exige que el usuario tenga uno de los roles indicados."""

    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            verify_jwt_in_request()
            _cargar_usuario_en_contexto()
            rol = getattr(g, "usuario_rol", None)
            if rol not in roles_permitidos:
                return error(
                    "No tiene permisos para realizar esta accion",
                    403,
                )
            return funcion(*args, **kwargs)

        return envoltura

    return decorador


def solo_administrador(funcion):
    """Atajo para acciones exclusivas del administrador."""
    return requiere_rol(ROL_ADMINISTRADOR)(funcion)
