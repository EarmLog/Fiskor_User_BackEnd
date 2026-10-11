# ============================================================
# Servicio de autenticacion.
#
# Estrategia "Plan de Respaldo":
#   - Lo normal es validar el usuario contra Supabase.
#   - Si Supabase no responde (se cayo el internet), entramos
#     con la copia local (cache) que se sincroniza en cada login.
# Asi el ERP jamas se queda sin poder facturar por un corte de red.
# ============================================================
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app.config import Configuracion
from app.extensions import db
from app.models.seguridad import SolicitudRegistro, TokenRecuperacion, UsuarioCache
from app.services import email_service, empresa_service, supabase_db
from app.utils.seguridad import ROL_ADMINISTRADOR

registro = logging.getLogger("fiskor")


class ErrorAutenticacion(Exception):
    """Error controlado de credenciales o de acceso."""


# ------------------------------------------------------------
# Claves
# ------------------------------------------------------------
def cifrar_clave(clave: str) -> str:
    """Genera el hash seguro de una contrasena."""
    return generate_password_hash(clave)


def verificar_clave(clave: str, hash_guardado: str) -> bool:
    """Compara una contrasena con su hash."""
    if not hash_guardado:
        return False
    try:
        return check_password_hash(hash_guardado, clave)
    except Exception:
        return False


# ------------------------------------------------------------
# Sincronizacion con la copia local
# ------------------------------------------------------------
def _sincronizar_cache(datos: dict) -> None:
    """Guarda o actualiza el usuario en la cache local."""
    cache = UsuarioCache.query.filter_by(usuario_supabase_id=datos["id"]).first()
    if cache is None:
        cache = UsuarioCache(usuario_supabase_id=datos["id"])
        db.session.add(cache)
    cache.email = datos["email"].lower()
    cache.nombre = datos.get("nombre", "")
    cache.cargo = datos.get("cargo", "")
    cache.rol = datos.get("rol", "Cajero")
    cache.activo = bool(datos.get("activo", True))
    cache.password_hash = datos.get("password_hash", cache.password_hash)
    empresas = datos.get("empresas", [])
    cache.empresas = json.dumps(empresas if isinstance(empresas, list) else [])
    cache.sincronizado_en = datetime.utcnow()
    db.session.commit()


def _datos_desde_cache(cache: UsuarioCache) -> dict:
    """Transforma el registro local en el diccionario de usuario."""
    try:
        empresas = json.loads(cache.empresas or "[]")
    except (ValueError, TypeError):
        empresas = []
    return {
        "id": cache.usuario_supabase_id,
        "email": cache.email,
        "nombre": cache.nombre,
        "cargo": cache.cargo,
        "rol": cache.rol,
        "activo": cache.activo,
        "empresas": empresas,
        "origen": "local",
    }


# ------------------------------------------------------------
# Login
# ------------------------------------------------------------
def iniciar_sesion(email: str, clave: str) -> dict:
    """Valida las credenciales y devuelve los datos del usuario."""
    email = (email or "").strip().lower()
    if not email or not clave:
        raise ErrorAutenticacion("Debe indicar el correo y la contrasena")

    # 1) Intentamos con Supabase (fuente principal).
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            usuario = supabase_db.buscar_usuario_por_email(email)
            if usuario is None:
                raise ErrorAutenticacion("El usuario no existe o la contrasena es incorrecta")
            if not usuario.get("activo", True):
                raise ErrorAutenticacion("El usuario esta inactivo. Contacte al administrador")
            if not verificar_clave(clave, usuario.get("password_hash", "")):
                raise ErrorAutenticacion("El usuario no existe o la contrasena es incorrecta")
            usuario["origen"] = "supabase"
            _sincronizar_cache(usuario)
            supabase_db.registrar_acceso(usuario["id"])
            return usuario
        except ErrorAutenticacion:
            raise
        except Exception as exc:
            registro.warning("Supabase no disponible, usando cache local: %s", exc)

    # 2) Respaldo: copia local.
    cache = UsuarioCache.query.filter(
        db.func.lower(UsuarioCache.email) == email
    ).first()
    if cache is None:
        raise ErrorAutenticacion("El usuario no existe o la contrasena es incorrecta")
    if not verificar_clave(clave, cache.password_hash):
        raise ErrorAutenticacion("El usuario no existe o la contrasena es incorrecta")
    if not cache.activo:
        raise ErrorAutenticacion("El usuario esta inactivo. Contacte al administrador")
    return _datos_desde_cache(cache)


# ------------------------------------------------------------
# Gestion de usuarios (desde el modulo de administracion)
# ------------------------------------------------------------
def listar_usuarios() -> list[dict]:
    """Lista los usuarios; si Supabase falla, usa la copia local."""
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            return supabase_db.listar_usuarios()
        except Exception as exc:
            registro.warning("No se pudo listar en Supabase: %s", exc)
    return [_datos_desde_cache(cache) for cache in UsuarioCache.query.all()]


def crear_usuario(datos: dict) -> dict:
    """Crea un usuario nuevo en Supabase y en la copia local."""
    clave = datos.pop("password", None)
    if not clave:
        raise ErrorAutenticacion("Debe indicar una contrasena")
    datos["password_hash"] = cifrar_clave(clave)
    datos["email"] = datos["email"].strip().lower()

    if supabase_db.disponible() or supabase_db.inicializar_pool():
        creado = supabase_db.crear_usuario(datos)
        _sincronizar_cache({**creado, "password_hash": datos["password_hash"]})
        return creado

    # Sin conexion a Supabase no se puede dar de alta un usuario nuevo.
    raise ErrorAutenticacion("Sin conexion a Supabase: no se pudo crear el usuario")


def actualizar_usuario(usuario_id: int, datos: dict) -> dict:
    """Actualiza un usuario existente."""
    clave = datos.pop("password", None)
    if clave:
        datos["password_hash"] = cifrar_clave(clave)
    if "email" in datos and datos["email"]:
        datos["email"] = datos["email"].strip().lower()

    if not (supabase_db.disponible() or supabase_db.inicializar_pool()):
        raise ErrorAutenticacion("Sin conexion a Supabase: no se pudo actualizar el usuario")
    actualizado = supabase_db.actualizar_usuario(usuario_id, datos)
    if actualizado:
        cache = UsuarioCache.query.filter_by(usuario_supabase_id=usuario_id).first()
        if cache:
            if clave:
                cache.password_hash = datos["password_hash"]
            cache.email = actualizado.get("email", cache.email)
            cache.nombre = actualizado.get("nombre", cache.nombre)
            cache.rol = actualizado.get("rol", cache.rol)
            cache.activo = actualizado.get("activo", cache.activo)
            db.session.commit()
    return actualizado


def eliminar_usuario(usuario_id: int) -> bool:
    """Elimina un usuario de Supabase y de la cache local."""
    if not (supabase_db.disponible() or supabase_db.inicializar_pool()):
        raise ErrorAutenticacion("Sin conexion a Supabase: no se pudo eliminar el usuario")
    eliminado = supabase_db.eliminar_usuario(usuario_id)
    cache = UsuarioCache.query.filter_by(usuario_supabase_id=usuario_id).first()
    if cache:
        db.session.delete(cache)
        db.session.commit()
    return eliminado


# ------------------------------------------------------------
# Administrador inicial
# ------------------------------------------------------------
def asegurar_administrador() -> None:
    """Crea el usuario administrador inicial si no existe."""
    email = Configuracion.ADMIN_EMAIL.lower()
    clave = Configuracion.ADMIN_PASSWORD
    nombre = Configuracion.ADMIN_NOMBRE

    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            existente = supabase_db.buscar_usuario_por_email(email)
            if existente is None:
                supabase_db.crear_usuario(
                    {
                        "email": email,
                        "password_hash": cifrar_clave(clave),
                        "nombre": nombre,
                        "cargo": "Administrador del Sistema",
                        "rol": ROL_ADMINISTRADOR,
                        "activo": True,
                        "empresas": "[]",
                    }
                )
                registro.info("Usuario administrador creado en Supabase: %s", email)
            # Refrescamos la cache local.
            usuario = supabase_db.buscar_usuario_por_email(email)
            if usuario:
                _sincronizar_cache(usuario)
                return
        except Exception as exc:
            registro.warning("No se pudo crear el administrador en Supabase: %s", exc)

    # Respaldo local: aseguramos que el administrador pueda entrar igual.
    cache = UsuarioCache.query.filter_by(email=email).first()
    if cache is None:
        db.session.add(
            UsuarioCache(
                usuario_supabase_id=-1,
                email=email,
                nombre=nombre,
                cargo="Administrador del Sistema",
                rol=ROL_ADMINISTRADOR,
                activo=True,
                password_hash=cifrar_clave(clave),
                empresas="[]",
                sincronizado_en=datetime.utcnow(),
            )
        )
        db.session.commit()
        registro.info("Usuario administrador creado en la copia local: %s", email)
    elif not verificar_clave(clave, cache.password_hash):
        # Si el admin local no coincide con el configurado, lo actualizamos.
        cache.password_hash = cifrar_clave(clave)
        cache.rol = ROL_ADMINISTRADOR
        cache.activo = True
        db.session.commit()


# ------------------------------------------------------------
# Registro publico de usuarios (con aprobacion del administrador)
# ------------------------------------------------------------
def _existe_usuario(email: str) -> bool:
    """Indica si ya hay una cuenta (o solicitud) con ese correo."""
    email = (email or "").strip().lower()
    if UsuarioCache.query.filter(db.func.lower(UsuarioCache.email) == email).first():
        return True
    if SolicitudRegistro.query.filter(db.func.lower(SolicitudRegistro.email) == email).first():
        return True
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            if supabase_db.buscar_usuario_por_email(email):
                return True
        except Exception:  # pragma: no cover
            pass
    return False


def crear_solicitud_registro(datos: dict) -> dict:
    """Registra una solicitud de alta de usuario (estado pendiente).

    NO crea la cuenta: el administrador debe aprobarla. La contrasena
    se guarda ya cifrada para no exponerla.
    """
    email = (datos.get("email") or "").strip().lower()
    clave = datos.get("password") or ""
    if _existe_usuario(email):
        raise ErrorAutenticacion("Ya existe una cuenta o solicitud con ese correo")

    solicitud = SolicitudRegistro(
        email=email,
        nombre=(datos.get("nombre") or "").strip()[:150],
        cargo=(datos.get("cargo") or "").strip()[:80],
        telefono=(datos.get("telefono") or "").strip()[:40],
        password_hash=cifrar_clave(clave),
        rol_solicitado=datos.get("rol") or "Cajero",
        estado="pendiente",
    )
    db.session.add(solicitud)
    db.session.commit()

    # Avisamos al administrador por correo (si hay SMTP configurado).
    try:
        email_service.enviar_aviso_registro(
            Configuracion.ADMIN_EMAIL,
            {
                "nombre": solicitud.nombre,
                "email": solicitud.email,
                "cargo": solicitud.cargo,
                "telefono": solicitud.telefono,
            },
        )
    except Exception as exc:  # pragma: no cover
        registro.warning("No se pudo avisar al administrador: %s", exc)

    return solicitud.a_diccionario(excluir=("password_hash",))


def registrar_usuario(datos: dict, revisado_por: str = "auto-registro") -> dict:
    """Crea la cuenta directamente, sin esperar aprobacion del administrador.

    Se usa cuando el registro esta abierto (FISKOR_REGISTRO_APROBACION=false).
    Crea el usuario en Supabase y lo sincroniza en la copia local para poder
    iniciar sesion incluso si se cae el internet.
    """
    email = (datos.get("email") or "").strip().lower()
    clave = datos.get("password") or ""
    if _existe_usuario(email):
        raise ErrorAutenticacion("Ya existe una cuenta o solicitud con ese correo")

    usuario = {
        "email": email,
        "password_hash": cifrar_clave(clave),
        "nombre": (datos.get("nombre") or "").strip()[:150],
        "cargo": (datos.get("cargo") or "").strip()[:80],
        "rol": datos.get("rol") or "Cajero",
        "activo": True,
        "empresas": "[]",
    }

    creado = None
    # Fuente principal: Supabase.
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            creado = supabase_db.crear_usuario(usuario)
        except Exception as exc:  # pragma: no cover - depende de la red
            registro.warning("No se pudo crear el usuario en Supabase: %s", exc)

    # Respaldo local: si no hay Supabase, la cuenta vive en la copia local.
    if creado is None:
        creado = {**usuario, "id": _siguiente_id_local()}

    _sincronizar_cache(
        {
            "id": creado["id"],
            "email": creado["email"],
            "nombre": creado.get("nombre", ""),
            "cargo": creado.get("cargo", ""),
            "rol": creado.get("rol", "Cajero"),
            "activo": True,
            "empresas": "[]",
            "password_hash": usuario["password_hash"],
        }
    )
    # Le creamos su propio negocio vacio para que empiece sin datos ajenos.
    try:
        empresa_service.asegurar_empresa_usuario(email, usuario["nombre"])
    except Exception as exc:  # pragma: no cover - no debe tumbar el registro
        registro.warning("No se pudo crear la empresa del usuario %s: %s", email, exc)
    return creado


def listar_solicitudes(estado: str | None = "pendiente") -> list[dict]:
    """Lista las solicitudes de registro (por defecto solo pendientes)."""
    consulta = SolicitudRegistro.query
    if estado and estado != "todas":
        consulta = consulta.filter_by(estado=estado)
    solicitudes = consulta.order_by(SolicitudRegistro.id.desc()).all()
    return [s.a_diccionario(excluir=("password_hash",)) for s in solicitudes]


def _siguiente_id_local() -> int:
    """Genera un id local unico y negativo para usuarios sin Supabase.

    Usamos negativos para no chocar nunca con los id reales (positivos)
    que asigna Supabase.
    """
    minimo = db.session.query(db.func.min(UsuarioCache.usuario_supabase_id)).scalar()
    if minimo is None or minimo >= 0:
        return -2  # -1 esta reservado para el administrador local
    return minimo - 1


def aprobar_solicitud(solicitud_id: int, datos: dict, revisado_por: str) -> dict:
    """Aprueba una solicitud y crea la cuenta real (Supabase + copia local)."""
    solicitud = SolicitudRegistro.query.get(solicitud_id)
    if solicitud is None:
        raise ErrorAutenticacion("Solicitud no encontrada")
    if solicitud.estado != "pendiente":
        raise ErrorAutenticacion("La solicitud ya fue revisada")

    rol = datos.get("rol") or solicitud.rol_solicitado or "Cajero"
    usuario = {
        "email": solicitud.email,
        "password_hash": solicitud.password_hash,
        "nombre": datos.get("nombre") or solicitud.nombre,
        "cargo": datos.get("cargo") or solicitud.cargo,
        "rol": rol,
        "activo": True,
        "empresas": "[]",
    }

    creado = None
    # Intentamos crearlo en Supabase (fuente principal).
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            creado = supabase_db.crear_usuario(usuario)
        except Exception as exc:
            registro.warning("No se pudo crear el usuario en Supabase: %s", exc)

    # Respaldo: si no hay Supabase, la cuenta vive en la copia local.
    if creado is None:
        creado = {**usuario, "id": _siguiente_id_local()}

    # Sincronizamos la copia local para permitir el login sin internet.
    _sincronizar_cache(
        {
            "id": creado["id"],
            "email": creado["email"],
            "nombre": creado.get("nombre", ""),
            "cargo": creado.get("cargo", ""),
            "rol": creado.get("rol", "Cajero"),
            "activo": True,
            "empresas": "[]",
            "password_hash": solicitud.password_hash,
        }
    )

    solicitud.estado = "aprobada"
    solicitud.revisado_por = revisado_por
    solicitud.revisado_en = datetime.utcnow()
    db.session.commit()
    # Le creamos su propio negocio vacio al usuario aprobado.
    try:
        empresa_service.asegurar_empresa_usuario(solicitud.email, usuario["nombre"])
    except Exception as exc:  # pragma: no cover - no debe tumbar la aprobacion
        registro.warning("No se pudo crear la empresa del usuario %s: %s", solicitud.email, exc)
    return creado


def rechazar_solicitud(solicitud_id: int, motivo: str, revisado_por: str) -> dict:
    """Rechaza una solicitud de registro."""
    solicitud = SolicitudRegistro.query.get(solicitud_id)
    if solicitud is None:
        raise ErrorAutenticacion("Solicitud no encontrada")
    if solicitud.estado != "pendiente":
        raise ErrorAutenticacion("La solicitud ya fue revisada")
    solicitud.estado = "rechazada"
    solicitud.motivo_rechazo = (motivo or "No aprobada")[:255]
    solicitud.revisado_por = revisado_por
    solicitud.revisado_en = datetime.utcnow()
    db.session.commit()
    return solicitud.a_diccionario(excluir=("password_hash",))


# ------------------------------------------------------------
# Recuperacion de contrasena
# ------------------------------------------------------------
def _hash_token(token: str) -> str:
    """Devuelve el SHA-256 del token (nunca guardamos el token en claro)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generar_token_recuperacion(email: str, ip: str = "") -> dict:
    """Genera y envia un token de recuperacion para el correo indicado.

    Devuelve {"enviado": bool, "enlace": str|None}. El enlace solo se
    incluye en la respuesta cuando NO hay SMTP y no estamos en produccion,
    para poder probar la recuperacion localmente.
    """
    email = (email or "").strip().lower()

    # Buscamos el nombre para personalizar el correo (sin revelar nada).
    nombre = ""
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            usuario = supabase_db.buscar_usuario_por_email(email)
            if usuario:
                nombre = usuario.get("nombre", "")
        except Exception:  # pragma: no cover
            pass
    if not nombre:
        cache = UsuarioCache.query.filter(db.func.lower(UsuarioCache.email) == email).first()
        nombre = cache.nombre if cache else ""

    # Invalidamos tokens anteriores de ese correo que sigan vigentes.
    TokenRecuperacion.query.filter_by(email=email, usado=False).update({"usado": True})

    token = secrets.token_urlsafe(32)
    expira = datetime.utcnow() + timedelta(minutes=Configuracion.MINUTOS_TOKEN_RECUPERACION)
    db.session.add(
        TokenRecuperacion(
            email=email,
            token_hash=_hash_token(token),
            expira_en=expira,
            solicitado_ip=ip[:45],
        )
    )
    db.session.commit()

    enlace = f"{Configuracion.URL_FRONTEND.rstrip('/')}/restablecer?token={token}&email={email}"
    resultado = email_service.enviar_recuperacion(email, nombre, enlace)

    respuesta = {"enviado": bool(resultado.get("enviado"))}
    # En desarrollo sin SMTP devolvemos el enlace para no bloquear las pruebas.
    if not resultado.get("enviado") and not Configuracion.EN_PRODUCCION:
        respuesta["enlace"] = enlace
        respuesta["motivo"] = resultado.get("motivo")
    return respuesta


def _buscar_token_valido(email: str, token: str) -> TokenRecuperacion | None:
    """Devuelve el token si existe, no expiro y no se uso."""
    if not email or not token:
        return None
    return (
        TokenRecuperacion.query.filter_by(
            email=email.strip().lower(), token_hash=_hash_token(token), usado=False
        )
        .filter(TokenRecuperacion.expira_en >= datetime.utcnow())
        .order_by(TokenRecuperacion.id.desc())
        .first()
    )


def token_es_valido(email: str, token: str) -> bool:
    """Verifica si un enlace de recuperacion sigue siendo utilizable."""
    return _buscar_token_valido(email, token) is not None


def restablecer_contrasena(email: str, token: str, nueva_clave: str) -> bool:
    """Cambia la contrasena si el token es valido (Supabase + copia local)."""
    registro_token = _buscar_token_valido(email, token)
    if registro_token is None:
        raise ErrorAutenticacion("El enlace es invalido o ya expiro")

    email = email.strip().lower()
    nuevo_hash = cifrar_clave(nueva_clave)

    # Actualizamos en Supabase si es posible.
    if supabase_db.disponible() or supabase_db.inicializar_pool():
        try:
            usuario = supabase_db.buscar_usuario_por_email(email)
            if usuario:
                supabase_db.actualizar_usuario(usuario["id"], {"password_hash": nuevo_hash})
        except Exception as exc:
            registro.warning("No se pudo actualizar la clave en Supabase: %s", exc)

    # Y siempre en la copia local (permite entrar sin internet).
    cache = UsuarioCache.query.filter(db.func.lower(UsuarioCache.email) == email).first()
    if cache is None:
        raise ErrorAutenticacion("El usuario no existe en este equipo")
    cache.password_hash = nuevo_hash
    registro_token.usado = True
    db.session.commit()
    return True
