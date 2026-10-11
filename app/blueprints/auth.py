# ============================================================
# API de autenticacion.
#   POST /api/auth/login         -> inicia sesion (Supabase o respaldo)
#   GET  /api/auth/perfil        -> datos del usuario conectado
#   POST /api/auth/registro      -> solicita una cuenta nueva
#   POST /api/auth/recuperar     -> envia enlace de recuperacion
#   POST /api/auth/restablecer   -> cambia la contrasena con token
#   GET  /api/auth/solicitudes   -> lista solicitudes (admin)
#   POST /api/auth/solicitudes/<id>/aprobar|rechazar (admin)
# ============================================================
from flask import Blueprint, request
from flask_jwt_extended import create_access_token

from app.config import Configuracion
from app.services import auth_service
from app.services.auditoria_service import registrar
from app.utils.respuestas import error, exito
from app.utils.seguridad import ROLES_VALIDOS, requiere_sesion, solo_administrador, usuario_actual
from app.utils.validaciones import validar_email

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


# ------------------------------------------------------------
# Registro publico (queda pendiente de aprobacion)
# ------------------------------------------------------------
@auth_bp.route("/registro", methods=["POST"])
def registro():
    """Recibe una solicitud de alta de usuario nueva."""
    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip().lower()

    valido, mensaje = validar_email(email)
    if not valido:
        return error(mensaje, 400)
    if not (datos.get("nombre") or "").strip():
        return error("El nombre es obligatorio", 400)
    if len(str(datos.get("password") or "")) < 6:
        return error("La contrasena debe tener al menos 6 caracteres", 400)
    if datos.get("rol") and datos["rol"] not in ROLES_VALIDOS:
        return error("El rol indicado no es valido", 400)

    # Registro abierto: la cuenta se crea y queda activa al instante.
    if not Configuracion.REGISTRO_REQUIERE_APROBACION:
        try:
            creado = auth_service.registrar_usuario(dict(datos))
        except auth_service.ErrorAutenticacion as exc:
            return error(str(exc), 409)
        except Exception:  # pragma: no cover - depende de la red
            return error("No se pudo crear la cuenta. Intente nuevamente.", 500)

        registrar(
            accion="registro",
            modulo="autenticacion",
            detalle="Cuenta creada por auto-registro",
            usuario=creado.get("email", email),
            ip=request.remote_addr,
        )
        return exito(
            {"creado": True, "email": creado.get("email", email)},
            "Cuenta creada correctamente. Ya puedes iniciar sesion.",
            201,
        )

    # Registro con aprobacion: queda pendiente hasta que un admin lo revise.
    try:
        auth_service.crear_solicitud_registro(dict(datos))
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 409)

    return exito(
        {"creado": False, "pendiente": True},
        "Solicitud enviada. Un administrador la revisara y activara tu cuenta.",
        201,
    )


# ------------------------------------------------------------
# Recuperacion de contrasena
# ------------------------------------------------------------
@auth_bp.route("/recuperar", methods=["POST"])
def recuperar():
    """Genera y envia el enlace de recuperacion de contrasena."""
    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip()
    valido, _ = validar_email(email)
    if not valido:
        return error("Indique un correo valido", 400)

    # Respuesta generica para no revelar si el correo existe o no.
    mensaje = "Si el correo esta registrado, recibiras un enlace para restablecer tu contrasena."
    try:
        resultado = auth_service.generar_token_recuperacion(email, request.remote_addr)
    except Exception:
        return exito(None, mensaje)

    registrar(
        accion="recuperar",
        modulo="autenticacion",
        detalle="Solicitud de recuperacion de contrasena",
        usuario=email,
        ip=request.remote_addr,
    )
    # En desarrollo sin SMTP devolvemos el enlace para poder probar.
    return exito(
        {"enlace": resultado.get("enlace")} if resultado.get("enlace") else None,
        mensaje,
    )


@auth_bp.route("/token-valido", methods=["GET"])
def token_valido():
    """Verifica si un enlace de recuperacion sigue vigente."""
    email = (request.args.get("email") or "").strip().lower()
    token = request.args.get("token") or ""
    return exito({"valido": auth_service.token_es_valido(email, token)}, "Estado del enlace")


@auth_bp.route("/restablecer", methods=["POST"])
def restablecer():
    """Cambia la contrasena usando un token valido."""
    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip().lower()
    token = datos.get("token") or ""
    clave = datos.get("password") or ""
    if len(clave) < 6:
        return error("La nueva contrasena debe tener al menos 6 caracteres", 400)

    try:
        auth_service.restablecer_contrasena(email, token, clave)
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 400)
    except Exception:
        return error("No se pudo restablecer la contrasena", 500)

    registrar(
        accion="restablecer",
        modulo="autenticacion",
        detalle="Contrasena restablecida con token",
        usuario=email,
        ip=request.remote_addr,
    )
    return exito(None, "Contrasena actualizada. Ya puedes iniciar sesion.")


# ------------------------------------------------------------
# Solicitudes de registro (solo administrador)
# ------------------------------------------------------------
@auth_bp.route("/solicitudes", methods=["GET"])
@solo_administrador
def listar_solicitudes():
    """Lista las solicitudes de registro pendientes (o todas)."""
    estado = request.args.get("estado", "pendiente")
    return exito(auth_service.listar_solicitudes(estado), "Solicitudes de registro")


@auth_bp.route("/solicitudes/<int:solicitud_id>/aprobar", methods=["POST"])
@solo_administrador
def aprobar_solicitud(solicitud_id: int):
    """Aprueba una solicitud y crea la cuenta del usuario."""
    datos = request.get_json(silent=True) or {}
    if datos.get("rol") and datos["rol"] not in ROLES_VALIDOS:
        return error("El rol indicado no es valido", 400)
    try:
        creado = auth_service.aprobar_solicitud(
            solicitud_id, datos, revisado_por=usuario_actual()["email"]
        )
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 400)
    except Exception:
        return error("No se pudo aprobar la solicitud", 500)

    registrar("aprobar", "usuarios", "solicitudes_registro", solicitud_id,
              "Solicitud aprobada", usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(creado, "Solicitud aprobada y usuario creado", 201)


@auth_bp.route("/solicitudes/<int:solicitud_id>/rechazar", methods=["POST"])
@solo_administrador
def rechazar_solicitud(solicitud_id: int):
    """Rechaza una solicitud de registro."""
    datos = request.get_json(silent=True) or {}
    try:
        rechazada = auth_service.rechazar_solicitud(
            solicitud_id, datos.get("motivo", ""), revisado_por=usuario_actual()["email"]
        )
    except auth_service.ErrorAutenticacion as exc:
        return error(str(exc), 400)

    registrar("rechazar", "usuarios", "solicitudes_registro", solicitud_id,
              "Solicitud rechazada", usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(rechazada, "Solicitud rechazada")
