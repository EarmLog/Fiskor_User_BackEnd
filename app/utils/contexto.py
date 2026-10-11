# ============================================================
# Utilidades de contexto (empresa activa y paginacion).
#
# La empresa activa ahora depende del usuario conectado: cada quien
# trabaja sobre SU propio negocio, de modo que nunca ve datos ajenos.
# ============================================================
from flask import request

from app.models.empresa import Empresa
from app.services import empresa_service
from app.utils.seguridad import ROL_ADMINISTRADOR, usuario_actual


def _empresa_pedida() -> int | None:
    """Lee una empresa especifica indicada por query o cabecera."""
    solicitada = request.args.get("empresa_id") or request.headers.get("X-Empresa-Id")
    if not solicitada:
        return None
    try:
        return int(solicitada)
    except (TypeError, ValueError):
        return None


def _es_del_usuario(empresa: Empresa, email: str) -> bool:
    """Indica si la empresa pertenece al correo indicado."""
    return (empresa.propietario_email or "").strip().lower() == email


def empresa_activa_id() -> int | None:
    """Devuelve el id de la empresa del usuario conectado.

    Reglas:
      - El administrador puede pedir cualquier empresa por query/cabecera.
      - Un usuario solo puede trabajar sobre su propia empresa.
      - Si el usuario aun no tiene empresa, se le crea una vacia al vuelo.
    """
    usuario = usuario_actual()
    email = (usuario.get("email") or "").strip().lower()
    es_admin = usuario.get("rol") == ROL_ADMINISTRADOR

    pedida = _empresa_pedida()
    if pedida is not None:
        empresa = Empresa.query.get(pedida)
        if empresa and (es_admin or _es_del_usuario(empresa, email)):
            return empresa.id

    if not email:
        # Sin sesion (uso interno): devolvemos la primera empresa.
        empresa = Empresa.query.order_by(Empresa.id).first()
        return empresa.id if empresa else None

    # Empresa propia del usuario.
    empresa = empresa_service.empresa_del_usuario(email)
    if empresa:
        return empresa.id

    # El administrador sin empresa propia trabaja sobre la primera.
    if es_admin:
        empresa = Empresa.query.order_by(Empresa.id).first()
        return empresa.id if empresa else None

    # Usuario nuevo sin negocio: se lo creamos vacio.
    empresa = empresa_service.crear_empresa_personal(email)
    return empresa.id


def parametros_paginacion() -> tuple[int, int]:
    """Lee 'pagina' y 'por_pagina' de la query string."""
    pagina = max(request.args.get("pagina", default=1, type=int), 1)
    por_pagina = min(max(request.args.get("por_pagina", default=25, type=int), 1), 200)
    return pagina, por_pagina
