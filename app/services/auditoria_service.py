# ============================================================
# Bitacora de auditoria.
# Cada accion importante (crear, modificar, eliminar, anular)
# queda registrada con usuario, fecha e IP para tener trazabilidad.
# ============================================================
import logging

from app.extensions import db
from app.models.seguridad import Auditoria

registro = logging.getLogger("fiskor")


def registrar(
    accion: str,
    modulo: str,
    tabla: str = "",
    registro_id: int | None = None,
    detalle: str = "",
    usuario: str = "",
    ip: str = "",
) -> None:
    """Guarda una traza de auditoria sin romper la operacion principal."""
    try:
        traza = Auditoria(
            usuario_email=usuario,
            accion=accion,
            modulo=modulo,
            tabla=tabla,
            registro_id=registro_id,
            detalle=detalle[:500] if detalle else "",
            ip=ip,
        )
        db.session.add(traza)
        db.session.commit()
    except Exception as exc:  # pragma: no cover
        db.session.rollback()
        registro.warning("No se pudo registrar la auditoria: %s", exc)
