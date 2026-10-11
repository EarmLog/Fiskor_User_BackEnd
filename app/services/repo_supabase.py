# ============================================================
# Repositorio generico contra Supabase con filtrado por empresa.
# Usa RLS en Postgres (recomendado). Tambien permite filtrar por
# usuario_email si aplica.
# ============================================================
import logging
from typing import Any

from app.services.supabase_client import get_client, SupabaseError

registro = logging.getLogger("fiskor")


class RepoSB:
    def __init__(self, tabla: str):
        self.tabla = tabla
        self.sb = get_client()

    def _empresa_id(self, kwargs: dict[str, Any]) -> Any:
        return kwargs.get("empresa_id") or kwargs.get("empresaId")

    def listar(self, **filtros: Any) -> list[dict[str, Any]]:
        q = self.sb.table(self.tabla).select("*")
        eid = self._empresa_id(filtros)
        if eid is not None:
            q = q.eq("empresa_id", eid)
        for k, v in filtros.items():
            if k in ("empresa_id", "empresaId", "order", "limit", "offset"):
                continue
            q = q.eq(k, v)
        try:
            res = q.execute()
            return res.data or []
        except Exception as exc:
            raise SupabaseError(str(exc)) from exc

    def obtener(self, _id: Any, **extra: Any) -> dict[str, Any] | None:
        q = self.sb.table(self.tabla).select("*").eq("id", _id)
        eid = self._empresa_id(extra)
        if eid is not None:
            q = q.eq("empresa_id", eid)
        res = q.execute()
        data = res.data or []
        return data[0] if data else None

    def crear(self, payload: dict[str, Any]) -> dict[str, Any]:
        res = self.sb.table(self.tabla).insert(payload).execute()
        data = res.data or []
        return data[0] if data else {}

    def actualizar(self, _id: Any, payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
        q = self.sb.table(self.tabla).update(payload).eq("id", _id)
        eid = self._empresa_id(extra)
        if eid is not None:
            q = q.eq("empresa_id", eid)
        res = q.execute()
        data = res.data or []
        return data[0] if data else {}

    def eliminar(self, _id: Any, **extra: Any) -> bool:
        q = self.sb.table(self.tabla).delete().eq("id", _id)
        eid = self._empresa_id(extra)
        if eid is not None:
            q = q.eq("empresa_id", eid)
        q.execute()
        return True

    def upsert(self, payload: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        res = self.sb.table(self.tabla).upsert(payload).execute()
        return res.data or []
