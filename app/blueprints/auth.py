# ============================================================
# API de autenticacion.
#   POST /api/auth/login   -> inicia sesion (Supabase o respaldo)
#   GET  /api/auth/perfil  -> datos del usuario conectado
# ============================================================
from flask import Blueprint, request
from flask_jwt_extended import create_access_token

from app.config import Configuracion
from app.services import auth_service
from app.services.auditoria_service import registrar
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def iniciar_sesion():
    """Valida las credenciales y entrega un token de sesion."""
    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip()
    clave = datos.get("password") or datos.get("clave") or ""

    try:
        usuario = auth_service.iniciar_sesion(email, clave)
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 401)
    except Exception as exc:  # pragma: no cover
        return error("No se pudo validar el acceso. Intente nuevamente.", 500)

    # Token con los datos clave dentro (identidad, rol, correo).
    token = create_access_token(
        identity=str(usuario["id"]),
        additional_claims={
            "email": usuario["email"],
            "rol": usuario["rol"],
            "nombre": usuario.get("nombre", ""),
        },
        expires_delta=False,
    )

    registrar(
        accion="login",
        modulo="autenticacion",
        detalle=f"Inicio de sesion desde {request.remote_addr}",
        usuario=usuario["email"],
        ip=request.remote_addr,
    )

    return exito(
        {
            "token": token,
            "usuario": {
                "id": usuario["id"],
                "email": usuario["email"],
                "nombre": usuario.get("nombre", ""),
                "cargo": usuario.get("cargo", ""),
                "rol": usuario["rol"],
                "origen": usuario.get("origen", "supabase"),
            },
        },
        "Bienvenido a Fiskor",
    )


@auth_bp.route("/perfil", methods=["GET"])
@requiere_sesion
def perfil():
    """Devuelve los datos del usuario autenticado."""
    return exito(usuario_actual(), "Perfil del usuario")
