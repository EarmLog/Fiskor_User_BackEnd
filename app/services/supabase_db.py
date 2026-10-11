# ============================================================
# Conexion con Supabase (PostgreSQL).
#
# IMPORTANTE: Supabase se usa UNICAMENTE para el login y la
# gestion de usuarios. Toda la data del ERP (inventario, ventas,
# compras, nomina, etc.) vive en la base de datos local SQLite.
#
# La tabla creada aqui se llama "fiskor_usuarios".
# ============================================================
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from app.config import Configuracion

registro = logging.getLogger("fiskor")

# Pool de conexiones: se crea una sola vez al arrancar la app.
_pool: pool.ThreadedConnectionPool | None = None


def _cadena_conexion() -> str:
    """Arma la cadena de conexion a partir de la configuracion."""
    return (
        f"host={Configuracion.SUPABASE_HOST} "
        f"port={Configuracion.SUPABASE_PORT} "
        f"dbname={Configuracion.SUPABASE_DB} "
        f"user={Configuracion.SUPABASE_USER} "
        f"password={Configuracion.SUPABASE_PASSWORD} "
        f"sslmode=require connect_timeout=8"
    )


def inicializar_pool() -> bool:
    """Crea el pool de conexiones a Supabase. Devuelve True si funciono.

    Si Supabase no responde el sistema NO se cae: queda en modo local.
    """
    global _pool
    if _pool is not None:
        return True
    try:
        _pool = pool.ThreadedConnectionPool(1, 5, dsn=_cadena_conexion())
        registro.info("Conexion a Supabase establecida correctamente.")
        return True
    except Exception as exc:  # pragma: no cover - depende de la red
        _pool = None
        registro.warning("No se pudo conectar a Supabase: %s", exc)
        return False


def disponible() -> bool:
    """Indica si hay conexion activa con Supabase."""
    return _pool is not None


@contextmanager
def conexion():
    """Entrega una conexion del pool y la devuelve al terminar."""
    if _pool is None and not inicializar_pool():
        raise ConnectionError("Supabase no esta disponible")
    conector = _pool.getconn()
    try:
        yield conector
        conector.commit()
    except Exception:
        conector.rollback()
        raise
    finally:
        _pool.putconn(conector)


# ------------------------------------------------------------
# Definicion de la tabla de usuarios en Supabase
# ------------------------------------------------------------
_SQL_TABLA_USUARIOS = """
CREATE TABLE IF NOT EXISTS fiskor_usuarios (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nombre        TEXT NOT NULL,
    cargo         TEXT DEFAULT '',
    rol           TEXT NOT NULL DEFAULT 'Cajero',
    activo        BOOLEAN NOT NULL DEFAULT TRUE,
    empresas      JSONB NOT NULL DEFAULT '[]'::jsonb,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_acceso TIMESTAMPTZ
);
"""


def asegurar_esquema() -> bool:
    """Crea la tabla de usuarios si aun no existe."""
    try:
        with conexion() as conector:
            with conector.cursor() as cursor:
                cursor.execute(_SQL_TABLA_USUARIOS)
        registro.info("Tabla de usuarios verificada en Supabase.")
        return True
    except Exception as exc:  # pragma: no cover - depende de la red
        registro.warning("No se pudo verificar la tabla de usuarios: %s", exc)
        return False


def buscar_usuario_por_email(email: str) -> dict | None:
    """Busca un usuario por su correo electronico."""
    with conexion() as conector:
        with conector.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM fiskor_usuarios WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
            fila = cursor.fetchone()
    return dict(fila) if fila else None


def listar_usuarios() -> list[dict]:
    """Devuelve todos los usuarios sin exponer la clave."""
    with conexion() as conector:
        with conector.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """SELECT id, email, nombre, cargo, rol, activo, empresas,
                          creado_en, ultimo_acceso
                   FROM fiskor_usuarios ORDER BY id"""
            )
            return [dict(fila) for fila in cursor.fetchall()]


def crear_usuario(datos: dict) -> dict:
    """Inserta un usuario nuevo y devuelve el registro creado."""
    with conexion() as conector:
        with conector.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """INSERT INTO fiskor_usuarios
                       (email, password_hash, nombre, cargo, rol, activo, empresas)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, email, nombre, cargo, rol, activo, empresas, creado_en""",
                (
                    datos["email"].lower(),
                    datos["password_hash"],
                    datos["nombre"],
                    datos.get("cargo", ""),
                    datos.get("rol", "Cajero"),
                    datos.get("activo", True),
                    datos.get("empresas", "[]"),
                ),
            )
            return dict(cursor.fetchone())


def actualizar_usuario(usuario_id: int, datos: dict) -> dict | None:
    """Actualiza los campos enviados de un usuario existente."""
    campos = []
    valores = []
    for clave in ("email", "nombre", "cargo", "rol", "activo", "empresas", "password_hash"):
        if clave in datos and datos[clave] is not None:
            campos.append(f"{clave} = %s")
            valores.append(datos[clave].lower() if clave == "email" else datos[clave])
    if not campos:
        return None
    valores.append(usuario_id)
    with conexion() as conector:
        with conector.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"""UPDATE fiskor_usuarios SET {', '.join(campos)} WHERE id = %s
                    RETURNING id, email, nombre, cargo, rol, activo, empresas""",
                valores,
            )
            fila = cursor.fetchone()
    return dict(fila) if fila else None


def eliminar_usuario(usuario_id: int) -> bool:
    """Elimina un usuario por su id."""
    with conexion() as conector:
        with conector.cursor() as cursor:
            cursor.execute("DELETE FROM fiskor_usuarios WHERE id = %s", (usuario_id,))
            return cursor.rowcount > 0


def registrar_acceso(usuario_id: int) -> None:
    """Guarda la fecha del ultimo inicio de sesion."""
    try:
        with conexion() as conector:
            with conector.cursor() as cursor:
                cursor.execute(
                    "UPDATE fiskor_usuarios SET ultimo_acceso = NOW() WHERE id = %s",
                    (usuario_id,),
                )
    except Exception as exc:  # pragma: no cover
        registro.warning("No se pudo registrar el acceso: %s", exc)
