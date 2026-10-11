# ============================================================
# Servicio de autenticacion.
#
# Estrategia "Plan de Respaldo":
#   - Lo normal es validar el usuario contra Supabase.
#   - Si Supabase no responde (se cayo el internet), entramos
#     con la copia local (cache) que se sincroniza en cada login.
# Asi el ERP jamas se queda sin poder facturar por un corte de red.
# ============================================================
import json
import logging
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from app.config import Configuracion
from app.extensions import db
from app.models.seguridad import UsuarioCache
from app.services import supabase_db
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
