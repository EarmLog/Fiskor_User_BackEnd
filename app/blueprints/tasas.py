# ============================================================
# API de tasas de cambio (dolar BCV).
#   GET  /api/tasas/actual      -> tasa vigente (sin internet)
#   GET  /api/tasas/historial   -> historial de tasas
#   POST /api/tasas/actualizar  -> intenta bajar la tasa del dia
#   POST /api/tasas/manual      -> carga manual (modo respaldo)
# ============================================================
from flask import Blueprint, request

from app.services import bcv_service
from app.services.auditoria_service import registrar
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, solo_administrador, usuario_actual
from app.utils.validaciones import validar_monto

tasas_bp = Blueprint("tasas", __name__, url_prefix="/api/tasas")


@tasas_bp.route("/actual", methods=["GET"])
@requiere_sesion
def actual():
    """Tasa vigente guardada localmente (no consulta internet)."""
    return exito(bcv_service.obtener_tasa_actual(), "Tasa vigente")


@tasas_bp.route("/historial", methods=["GET"])
@requiere_sesion
def historial():
    """Ultimas tasas registradas."""
    limite = request.args.get("limite", default=30, type=int)
    return exito(bcv_service.historial(limite), "Historial de tasas")


@tasas_bp.route("/actualizar", methods=["POST"])
@requiere_sesion
def actualizar():
    """Intenta actualizar la tasa desde la API externa.

    Si no hay internet, conserva la ultima tasa y responde sin romper.
    """
    resultado = bcv_service.actualizar_tasa_automatica()
    mensaje = (
        "Tasa actualizada desde la API"
        if resultado.get("actualizada")
        else "No se pudo consultar la API. Se mantiene la ultima tasa conocida."
    )
    return exito({**resultado, **bcv_service.obtener_tasa_actual()}, mensaje)


@tasas_bp.route("/manual", methods=["POST"])
@solo_administrador
def manual():
    """Carga manual de la tasa (respaldo cuando no hay internet)."""
    datos = request.get_json(silent=True) or {}
    valido, mensaje = validar_monto(datos.get("valor"), "valor de la tasa")
    if not valido:
        return error(mensaje, 400)
    valor = float(datos["valor"])
    if valor <= 0:
        return error("La tasa debe ser mayor que cero", 400)

    from app.utils.fechas import a_fecha

    tasa = bcv_service.establecer_tasa_manual(
        valor, usuario=usuario_actual()["email"], fecha=a_fecha(datos.get("fecha"))
    )
    registrar("crear", "tasas", "tasas_cambio", tasa.id, f"Tasa manual {valor}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(tasa.a_diccionario(), "Tasa cargada manualmente")
