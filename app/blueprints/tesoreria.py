# ============================================================
# API de caja y bancos.
#   - Cuentas bancarias.
#   - Apertura/cierre de caja por cajero.
#   - Ingresos y egresos de efectivo, pago movil y transferencias.
# ============================================================
from datetime import date, datetime

from flask import Blueprint, request

from app.extensions import db
from app.models.tesoreria import CuentaBancaria, MovimientoCaja, SesionCaja
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto

tesoreria_bp = Blueprint("tesoreria", __name__, url_prefix="/api/tesoreria")


# ------------------------------------------------------------
# Cuentas bancarias
# ------------------------------------------------------------
@tesoreria_bp.route("/cuentas", methods=["GET"])
@requiere_sesion
def listar_cuentas():
    empresa_id = empresa_activa_id()
    cuentas = CuentaBancaria.query.filter_by(empresa_id=empresa_id).order_by(CuentaBancaria.banco).all()
    return exito([c.a_diccionario() for c in cuentas], "Cuentas bancarias")


@tesoreria_bp.route("/cuentas", methods=["POST"])
@requiere_sesion
def crear_cuenta():
    datos = request.get_json(silent=True) or {}
    banco = limpiar_texto(datos.get("banco"), 80)
    if not banco:
        return error("El nombre del banco es obligatorio", 400)
    cuenta = CuentaBancaria(
        empresa_id=empresa_activa_id(),
        banco=banco,
        numero_cuenta=limpiar_texto(datos.get("numero_cuenta"), 30),
        tipo=limpiar_texto(datos.get("tipo"), 20) or "corriente",
        moneda=limpiar_texto(datos.get("moneda"), 10) or "VES",
        titular=limpiar_texto(datos.get("titular"), 150),
        rif_titular=limpiar_texto(datos.get("rif_titular"), 20),
        saldo=float(datos.get("saldo") or 0),
    )
    db.session.add(cuenta)
    db.session.commit()
    return exito(cuenta.a_diccionario(), "Cuenta bancaria registrada", 201)


# ------------------------------------------------------------
# Caja
# ------------------------------------------------------------
@tesoreria_bp.route("/caja/actual", methods=["GET"])
@requiere_sesion
def caja_actual():
    """Devuelve la sesion de caja abierta del usuario (si tiene)."""
    usuario = usuario_actual()["email"]
    sesion = (
        SesionCaja.query.filter_by(estado="abierta", usuario=usuario)
        .order_by(SesionCaja.id.desc())
        .first()
    )
    if sesion is None:
        return exito(None, "No hay caja abierta")
    return exito(sesion.a_diccionario(), "Caja abierta")


@tesoreria_bp.route("/caja/abrir", methods=["POST"])
@requiere_sesion
def abrir_caja():
    usuario = usuario_actual()["email"]
    abierta = SesionCaja.query.filter_by(estado="abierta", usuario=usuario).first()
    if abierta:
        return error("Ya tiene una caja abierta. Cierrela antes de abrir otra", 409)
    datos = request.get_json(silent=True) or {}
    sesion = SesionCaja(
        empresa_id=empresa_activa_id(),
        usuario=usuario,
        monto_inicial=float(datos.get("monto_inicial") or 0),
        abierta_en=datetime.utcnow(),
        estado="abierta",
    )
    db.session.add(sesion)
    db.session.commit()
    registrar("crear", "tesoreria", "sesiones_caja", sesion.id, "Apertura de caja",
              usuario=usuario, ip=request.remote_addr)
    return exito(sesion.a_diccionario(), "Caja abierta", 201)


@tesoreria_bp.route("/caja/cerrar", methods=["POST"])
@requiere_sesion
def cerrar_caja():
    usuario = usuario_actual()["email"]
    sesion = SesionCaja.query.filter_by(estado="abierta", usuario=usuario).first()
    if sesion is None:
        return error("No hay una caja abierta", 404)
    datos = request.get_json(silent=True) or {}
    monto_cierre = float(datos.get("monto_cierre") or 0)

    # Calculamos el total esperado en bolivares segun los movimientos.
    total_movimientos = sum(
        (mov.monto if mov.tipo == "ingreso" else -mov.monto)
        for mov in sesion.movimientos
        if mov.moneda == "VES"
    )
    esperado = round((sesion.monto_inicial or 0) + total_movimientos, 2)
    sesion.monto_cierre = monto_cierre
    sesion.diferencia = round(monto_cierre - esperado, 2)
    sesion.cerrada_en = datetime.utcnow()
    sesion.observaciones = limpiar_texto(datos.get("observaciones"), 255)
    sesion.estado = "cerrada"
    db.session.commit()
    registrar("modificar", "tesoreria", "sesiones_caja", sesion.id,
              f"Cierre de caja (diferencia {sesion.diferencia:.2f})",
              usuario=usuario, ip=request.remote_addr)
    return exito(sesion.a_diccionario(), "Caja cerrada")


@tesoreria_bp.route("/movimientos", methods=["GET"])
@requiere_sesion
def listar_movimientos():
    empresa_id = empresa_activa_id()
    consulta = MovimientoCaja.query.filter_by(empresa_id=empresa_id)
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    from app.utils.fechas import a_fecha

    if desde:
        consulta = consulta.filter(MovimientoCaja.fecha >= a_fecha(desde))
    if hasta:
        consulta = consulta.filter(MovimientoCaja.fecha <= a_fecha(hasta))
    movimientos = consulta.order_by(MovimientoCaja.id.desc()).limit(300).all()
    return exito([m.a_diccionario() for m in movimientos], "Movimientos de caja")


@tesoreria_bp.route("/movimientos", methods=["POST"])
@requiere_sesion
def crear_movimiento():
    """Registra un ingreso o egreso de caja."""
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "ingreso").lower()
    if tipo not in ("ingreso", "egreso"):
        return error("Tipo de movimiento no valido", 400)
    try:
        monto = float(datos.get("monto") or 0)
    except (TypeError, ValueError):
        return error("El monto debe ser un numero valido", 400)
    if monto <= 0:
        return error("El monto debe ser mayor que cero", 400)

    usuario = usuario_actual()["email"]
    sesion = SesionCaja.query.filter_by(estado="abierta", usuario=usuario).first()
    movimiento = MovimientoCaja(
        empresa_id=empresa_activa_id(),
        sesion_caja_id=sesion.id if sesion else None,
        tipo=tipo,
        concepto=limpiar_texto(datos.get("concepto"), 180),
        categoria=limpiar_texto(datos.get("categoria"), 60) or "otros",
        metodo=limpiar_texto(datos.get("metodo"), 30) or "efectivo_bs",
        moneda=limpiar_texto(datos.get("moneda"), 10) or "VES",
        monto=monto,
        tasa=float(datos.get("tasa") or 1),
        referencia=limpiar_texto(datos.get("referencia"), 60),
        usuario=usuario,
        fecha=date.today(),
    )
    db.session.add(movimiento)
    db.session.commit()
    registrar("crear", "tesoreria", "movimientos_caja", movimiento.id,
              f"{tipo} {monto} ({movimiento.metodo})", usuario=usuario, ip=request.remote_addr)
    return exito(movimiento.a_diccionario(), "Movimiento registrado", 201)


@tesoreria_bp.route("/resumen", methods=["GET"])
@requiere_sesion
def resumen():
    """Resumen rapido de caja y bancos."""
    empresa_id = empresa_activa_id()
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    from app.utils.fechas import a_fecha

    consulta = MovimientoCaja.query.filter_by(empresa_id=empresa_id)
    if desde:
        consulta = consulta.filter(MovimientoCaja.fecha >= a_fecha(desde))
    if hasta:
        consulta = consulta.filter(MovimientoCaja.fecha <= a_fecha(hasta))
    movimientos = consulta.all()
    ingresos = sum(m.monto for m in movimientos if m.tipo == "ingreso" and m.moneda == "VES")
    egresos = sum(m.monto for m in movimientos if m.tipo == "egreso" and m.moneda == "VES")
    return exito(
        {
            "ingresos_bs": round(ingresos, 2),
            "egresos_bs": round(egresos, 2),
            "neto_bs": round(ingresos - egresos, 2),
            "cuentas_bancarias": [
                c.a_diccionario() for c in CuentaBancaria.query.filter_by(empresa_id=empresa_id).all()
            ],
        },
        "Resumen de tesoreria",
    )
