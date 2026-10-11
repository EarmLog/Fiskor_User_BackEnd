# ============================================================
# API fiscal y tributaria (SENIAT).
#   - Comprobantes de retencion (IVA e ISLR).
#   - Borradores de libros de compras y ventas.
#   - Resumen de IVA (debito y credito fiscal).
#   - Calendario fiscal del contribuyente.
# ============================================================
from datetime import date

from flask import Blueprint, request

from app.extensions import db
from app.models.compras import Compra
from app.models.fiscal import Retencion
from app.models.terceros import Cliente, Proveedor
from app.models.ventas import Venta
from app.services import fiscal_service
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id
from app.utils.fechas import a_fecha, generar_calendario_fiscal
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto, normalizar_rif, validar_rif

fiscal_bp = Blueprint("fiscal", __name__, url_prefix="/api/fiscal")


# ------------------------------------------------------------
# Retenciones
# ------------------------------------------------------------
@fiscal_bp.route("/retenciones", methods=["GET"])
@requiere_sesion
def listar_retenciones():
    empresa_id = empresa_activa_id()
    tipo = request.args.get("tipo")
    consulta = Retencion.query.filter_by(empresa_id=empresa_id)
    if tipo:
        consulta = consulta.filter_by(tipo=tipo)
    retenciones = consulta.order_by(Retencion.id.desc()).limit(300).all()
    return exito([r.a_diccionario() for r in retenciones], "Retenciones")


@fiscal_bp.route("/retenciones", methods=["POST"])
@requiere_sesion
def crear_retencion():
    """Emite un comprobante de retencion de IVA o ISLR."""
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "IVA").upper()
    if tipo not in ("IVA", "ISLR"):
        return error("El tipo de retencion debe ser IVA o ISLR", 400)

    base = float(datos.get("base_imponible") or 0)
    if base <= 0:
        return error("La base imponible debe ser mayor que cero", 400)

    rif = normalizar_rif(datos.get("sujeto_rif", ""))
    if rif:
        valido, mensaje = validar_rif(rif)
        if not valido:
            return error(mensaje, 400)

    porcentaje = float(datos.get("porcentaje") or (75 if tipo == "IVA" else 5))
    if tipo == "IVA":
        monto = fiscal_service.calcular_retencion_iva(base, porcentaje)
    else:
        monto = fiscal_service.calcular_retencion_islr(base, porcentaje, float(datos.get("sustraendo") or 0))

    empresa_id = empresa_activa_id()
    retencion = Retencion(
        empresa_id=empresa_id,
        tipo=tipo,
        numero_comprobante=fiscal_service.siguiente_numero_retencion(empresa_id, tipo),
        fecha=a_fecha(datos.get("fecha")) or date.today(),
        periodo=limpiar_texto(datos.get("periodo"), 20) or date.today().strftime("%m/%Y"),
        sujeto_tipo=limpiar_texto(datos.get("sujeto_tipo"), 20) or "proveedor",
        sujeto_id=datos.get("sujeto_id") or None,
        sujeto_nombre=limpiar_texto(datos.get("sujeto_nombre"), 180),
        sujeto_rif=rif,
        numero_documento=limpiar_texto(datos.get("numero_documento"), 40),
        numero_control=limpiar_texto(datos.get("numero_control"), 40),
        base_imponible=base,
        porcentaje=porcentaje,
        monto_retenido=monto,
        sustraendo=float(datos.get("sustraendo") or 0),
        moneda=limpiar_texto(datos.get("moneda"), 10) or "VES",
        tasa=float(datos.get("tasa") or 1),
        usuario=usuario_actual()["email"],
    )
    db.session.add(retencion)
    db.session.commit()
    registrar("crear", "fiscal", "retenciones", retencion.id,
              f"Retencion {tipo} {retencion.numero_comprobante}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(retencion.a_diccionario(), "Comprobante de retencion emitido", 201)


# ------------------------------------------------------------
# Libros de compras y ventas
# ------------------------------------------------------------
@fiscal_bp.route("/libro-ventas", methods=["GET"])
@requiere_sesion
def libro_ventas():
    empresa_id = empresa_activa_id()
    desde = a_fecha(request.args.get("desde"))
    hasta = a_fecha(request.args.get("hasta"))
    consulta = Venta.query.filter_by(empresa_id=empresa_id, estado="emitida")
    if desde:
        consulta = consulta.filter(Venta.fecha >= desde)
    if hasta:
        consulta = consulta.filter(Venta.fecha <= hasta)
    ventas = consulta.order_by(Venta.fecha).all()
    filas = []
    for venta in ventas:
        filas.append(
            {
                "fecha": venta.fecha.isoformat() if venta.fecha else "",
                "numero_factura": venta.numero_factura,
                "numero_control": venta.numero_control,
                "rif": venta.cliente.rif if venta.cliente else "V-00000000",
                "razon_social": venta.cliente.nombre if venta.cliente else "Consumidor final",
                "base_imponible": venta.base_imponible,
                "iva": venta.iva,
                "igtf": venta.igtf,
                "total": venta.total_bolivares,
            }
        )
    return exito(
        {
            "filas": filas,
            "total_base": round(sum(f["base_imponible"] * (venta.tasa_aplicada or 1) for f, venta in zip(filas, ventas)), 2),
            "total_iva": round(sum(f["iva"] * (venta.tasa_aplicada or 1) for f, venta in zip(filas, ventas)), 2),
        },
        "Libro de ventas",
    )


@fiscal_bp.route("/libro-compras", methods=["GET"])
@requiere_sesion
def libro_compras():
    empresa_id = empresa_activa_id()
    desde = a_fecha(request.args.get("desde"))
    hasta = a_fecha(request.args.get("hasta"))
    consulta = Compra.query.filter_by(empresa_id=empresa_id, estado="registrada")
    if desde:
        consulta = consulta.filter(Compra.fecha >= desde)
    if hasta:
        consulta = consulta.filter(Compra.fecha <= hasta)
    compras = consulta.order_by(Compra.fecha).all()
    filas = [
        {
            "fecha": compra.fecha.isoformat() if compra.fecha else "",
            "numero_factura": compra.numero_factura,
            "numero_control": compra.numero_control,
            "rif": compra.proveedor.rif if compra.proveedor else "",
            "razon_social": compra.proveedor.nombre if compra.proveedor else "",
            "base_imponible": compra.subtotal,
            "iva": compra.iva,
            "retencion_iva": compra.retencion_iva,
            "total": compra.total,
        }
        for compra in compras
    ]
    return exito(
        {
            "filas": filas,
            "total_base": round(sum(f["base_imponible"] for f in filas), 2),
            "total_iva": round(sum(f["iva"] for f in filas), 2),
            "total_retencion": round(sum(f["retencion_iva"] for f in filas), 2),
        },
        "Libro de compras",
    )


@fiscal_bp.route("/resumen-iva", methods=["GET"])
@requiere_sesion
def resumen_iva():
    """Resumen de IVA para la declaracion (borrador)."""
    empresa_id = empresa_activa_id()
    desde = a_fecha(request.args.get("desde"))
    hasta = a_fecha(request.args.get("hasta"))

    ventas = Venta.query.filter_by(empresa_id=empresa_id, estado="emitida")
    compras = Compra.query.filter_by(empresa_id=empresa_id, estado="registrada")
    if desde:
        ventas = ventas.filter(Venta.fecha >= desde)
        compras = compras.filter(Compra.fecha >= desde)
    if hasta:
        ventas = ventas.filter(Venta.fecha <= hasta)
        compras = compras.filter(Compra.fecha <= hasta)

    debito = sum(v.iva for v in ventas.all())
    credito_informativo = sum(c.iva for c in compras.all())
    retenido = sum(c.retencion_iva for c in compras.all())
    saldo = round(debito - credito_informativo - retenido, 2)
    return exito(
        {
            "debito_fiscal": round(debito, 2),
            "credito_fiscal": round(credito_informativo, 2),
            "iva_retenido": round(retenido, 2),
            "saldo_a_pagar": saldo,
        },
        "Resumen de IVA",
    )


@fiscal_bp.route("/calendario", methods=["GET"])
@requiere_sesion
def calendario():
    """Calendario fiscal del contribuyente para un anio."""
    anio = request.args.get("anio", default=date.today().year, type=int)
    return exito(generar_calendario_fiscal(anio), "Calendario fiscal")
