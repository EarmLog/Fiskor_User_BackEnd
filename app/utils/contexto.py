# ============================================================
# Utilidades de contexto (empresa activa y paginacion).
# ============================================================
from flask import request

from app.models.empresa import Empresa


def empresa_activa_id() -> int | None:
    """Devuelve el id de la empresa activa.

    Permite que el frontend indique otra empresa por cabecera o query.
    """
    solicitada = request.args.get("empresa_id") or request.headers.get("X-Empresa-Id")
    if solicitada:
        try:
            return int(solicitada)
        except (TypeError, ValueError):
            pass
    empresa = Empresa.query.filter_by(activa=True).order_by(Empresa.id).first()
    if empresa is None:
        empresa = Empresa.query.order_by(Empresa.id).first()
    return empresa.id if empresa else None


def parametros_paginacion() -> tuple[int, int]:
    """Lee 'pagina' y 'por_pagina' de la query string."""
    pagina = max(request.args.get("pagina", default=1, type=int), 1)
    por_pagina = min(max(request.args.get("por_pagina", default=25, type=int), 1), 200)
    return pagina, por_pagina
