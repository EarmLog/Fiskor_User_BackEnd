# ============================================================
# Cliente Supabase (REST + Auth) para migrar datos a la nube.
# Se usa como capa de acceso para leer/escribir en PostgreSQL.
# ============================================================
import logging
from typing import Any

from supabase import Client, create_client

from app.config import Configuracion

registro = logging.getLogger("fiskor")


class SupabaseError(Exception):
    pass


def _crear_cliente() -> Client | None:
    url = Configuracion.SUPABASE_URL
    key = Configuracion.SUPABASE_ANON_KEY
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as exc:
        registro.warning("No se pudo inicializar cliente Supabase: %s", exc)
        return None


_cliente = _crear_cliente()


def get_client() -> Client:
    global _cliente
    if _cliente is None:
        _cliente = _crear_cliente()
    if _cliente is None:
        raise SupabaseError("Supabase no esta configurado")
    return _cliente


def disponible() -> bool:
    try:
        c = get_client()
        return c is not None
    except Exception:
        return False
