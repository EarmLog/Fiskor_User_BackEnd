# ============================================================
# API de compras a proveedores y cuentas por pagar.
#
# Al registrar una compra:
#   - Se aumenta el inventario.
#   - Si es a credito, se crea la cuenta por pagar.
#   - Se calculan las retenciones de IVA e ISLR del proveedor.
# ============================================================
from datetime import date, timedelta

from flask import Blueprint, request

from app.extensions import db
from app.models.compras import AbonoCxP, Compra, CompraDetalle, CuentaPorPagar
from app.models.terceros import Proveedor
from app.services import fiscal_service, inventario_service
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id, parametros_paginacion
from app.utils.fechas import a_fecha
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto

compras_bp = Blueprint("compras", __name__, url_prefix="/api/compras")


@compras_bp.route("", methods=["GET"])
@requiere_sesion
def listar():
    empresa_id = empresa_activa_id()
    pagina, por_pagina = parametros_paginacion()
    consulta = Compra.query.filter_by(empresa_id=empresa_id)
    total = consulta.count()
    compras = consulta.order_by(Compra.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    datos = []
    for compra in compras:
        item = compra.a_diccionario()
        item["proveedor_nombre"] = compra.proveedor.nombre if compra.proveedor else ""
        datos.append(item)
    return exito({"items": datos, "total": total}, "Compras")


@compras_bp.route("/<int:compra_id>", methods=["GET"])
@requiere_sesion
def obtener(compra_id: int):
    compra = Compra.query.get(compra_id)
    if compra is None:
        return error("Compra no encontrada", 404)
    datos = compra.a_diccionario()
    datos["proveedor_nombre"] = compra.proveedor.nombre if compra.proveedor else ""
    datos["detalles"] = [d.a_diccionario() for d in compra.detalles]
    return exito(datos, "Compra")


@compras_bp.route("", methods=["POST"])
@requiere_sesion
def crear():
    """Registra una compra y aumenta el inventario."""
    datos = request.get_json(silent=True) or {}
    proveedor_id = datos.get("proveedor_id")
    lineas = datos.get("lineas") or []
    if not proveedor_id:
        return error("Debe seleccionar un proveedor", 400)
    if not lineas:
        return error("Debe agregar al menos un renglon a la compra", 400)

    proveedor = Proveedor.query.get(proveedor_id)
    if proveedor is None:
        return error("Proveedor no encontrado", 404)

    empresa_id = empresa_activa_id()
    usuario = usuario_actual()["email"]
    condicion = (datos.get("condicion") or "contado").lower()

    # Recalculamos los totales de los renglones (base en divisas).
    resumen = fiscal_service.resumir_lineas(
        [
            {
                "producto_id": linea.get("producto_id"),
                "descripcion": limpiar_texto(linea.get("descripcion"), 180),
                "cantidad": float(linea.get("cantidad") or 0),
                "precio_unitario": float(linea.get("costo_unitario") or 0),
                "iva_porcentaje": float(linea.get("iva_porcentaje") or 16.0),
                "descuento": 0,
            }
            for linea in lineas
        ]
    )
    total = round(resumen["base_imponible"] + resumen["iva"], 2)

    # Retenciones del proveedor.
    retencion_iva = fiscal_service.calcular_retencion_iva(
        resumen["base_imponible"], proveedor.retencion_iva
    )
    retencion_islr = fiscal_service.calcular_retencion_islr(
        resumen["base_imponible"], proveedor.retencion_islr
    )

    try:
        compra = Compra(
            empresa_id=empresa_id,
            proveedor_id=proveedor_id,
            numero_factura=limpiar_texto(datos.get("numero_factura"), 40),
            numero_control=limpiar_texto(datos.get("numero_control"), 40),
            fecha=a_fecha(datos.get("fecha")) or date.today(),
            tipo=(datos.get("tipo") or "factura").lower(),
            condicion=condicion,
            subtotal=resumen["subtotal"],
            iva=resumen["iva"],
            total=total,
            retencion_iva=retencion_iva,
            retencion_islr=retencion_islr,
            observaciones=limpiar_texto(datos.get("observaciones"), 255),
            usuario=usuario,
        )
        db.session.add(compra)
        db.session.flush()

        for linea in lineas:
            producto_id = linea.get("producto_id")
            cantidad = float(linea.get("cantidad") or 0)
            costo = float(linea.get("costo_unitario") or 0)
            db.session.add(
                CompraDetalle(
                    compra_id=compra.id,
                    producto_id=producto_id,
                    descripcion=limpiar_texto(linea.get("descripcion"), 180),
                    cantidad=cantidad,
                    costo_unitario=costo,
                    iva_porcentaje=float(linea.get("iva_porcentaje") or 16.0),
                    total=round(cantidad * costo, 2),
                )
            )
            if producto_id:
                inventario_service.aumentar_stock(
                    producto_id, cantidad, costo, "Compra", compra.numero_factura, usuario
                )

        if condicion == "credito":
            vencimiento = compra.fecha + timedelta(days=int(datos.get("dias_credito") or proveedor.dias_credito or 30))
            db.session.add(
                CuentaPorPagar(
                    empresa_id=empresa_id,
                    proveedor_id=proveedor_id,
                    compra_id=compra.id,
                    monto_total=total,
                    saldo=total,
                    fecha_emision=compra.fecha,
                    fecha_vencimiento=vencimiento,
                    estado="pendiente",
                )
            )
            proveedor.saldo_pendiente = round((proveedor.saldo_pendiente or 0) + total, 2)

        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo registrar la compra. Verifique los datos ingresados", 500)

    registrar("crear", "compras", "compras", compra.id,
              f"Compra {compra.numero_factura} por ${total:.2f}",
              usuario=usuario, ip=request.remote_addr)
    return exito({"id": compra.id}, "Compra registrada", 201)


@compras_bp.route("/<int:compra_id>/anular", methods=["POST"])
@requiere_sesion
def anular(compra_id: int):
    compra = Compra.query.get(compra_id)
    if compra is None:
        return error("Compra no encontrada", 404)
    if compra.estado == "anulada":
        return error("La compra ya estaba anulada", 400)

    usuario = usuario_actual()["email"]
    try:
        # Revertimos el inventario sumando y restando lo comprado.
        for detalle in compra.detalles:
            if detalle.producto_id:
                # Revertimos con una salida controlada de ser posible.
                from sqlalchemy import update
                from app.models.inventario import Producto

                db.session.execute(
                    update(Producto)
                    .where(Producto.id == detalle.producto_id)
                    .values(stock_actual=Producto.stock_actual - detalle.cantidad)
                )
        cuenta = CuentaPorPagar.query.filter_by(compra_id=compra.id).first()
        if cuenta and cuenta.estado != "pagada":
            cuenta.estado = "anulada"
            proveedor = Proveedor.query.get(cuenta.proveedor_id)
            if proveedor:
                proveedor.saldo_pendiente = round((proveedor.saldo_pendiente or 0) - cuenta.saldo, 2)
        compra.estado = "anulada"
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo anular la compra", 500)

    registrar("anular", "compras", "compras", compra.id, "Anulacion de compra",
              usuario=usuario, ip=request.remote_addr)
    return exito(None, "Compra anulada")


# ------------------------------------------------------------
# Cuentas por pagar
# ------------------------------------------------------------
@compras_bp.route("/cxp", methods=["GET"])
@requiere_sesion
def listar_cxp():
    empresa_id = empresa_activa_id()
    estado = request.args.get("estado", "pendiente")
    consulta = CuentaPorPagar.query.filter_by(empresa_id=empresa_id)
    if estado and estado != "todas":
        consulta = consulta.filter_by(estado=estado)
    cuentas = consulta.order_by(CuentaPorPagar.fecha_vencimiento).all()
    datos = []
    for cuenta in cuentas:
        item = cuenta.a_diccionario()
        item["proveedor_nombre"] = cuenta.proveedor.nombre if cuenta.proveedor else ""
        item["dias_vencida"] = (
            (date.today() - cuenta.fecha_vencimiento).days
            if cuenta.fecha_vencimiento and cuenta.estado == "pendiente"
            else 0
        )
        datos.append(item)
    return exito(datos, "Cuentas por pagar")


@compras_bp.route("/cxp/<int:cuenta_id>/abono", methods=["POST"])
@requiere_sesion
def abonar_cxp(cuenta_id: int):
    cuenta = CuentaPorPagar.query.get(cuenta_id)
    if cuenta is None:
        return error("Cuenta por pagar no encontrada", 404)
    datos = request.get_json(silent=True) or {}
    monto = float(datos.get("monto") or 0)
    if monto <= 0:
        return error("El monto del abono debe ser mayor que cero", 400)
    if monto > cuenta.saldo + 0.01:
        return error(f"El abono no puede superar el saldo pendiente ({cuenta.saldo:.2f})", 400)

    try:
        cuenta.saldo = round(cuenta.saldo - monto, 2)
        if cuenta.saldo <= 0.01:
            cuenta.saldo = 0.0
            cuenta.estado = "pagada"
        db.session.add(
            AbonoCxP(
                cuenta_id=cuenta.id,
                monto=monto,
                moneda=datos.get("moneda") or "USD",
                tasa=float(datos.get("tasa") or 1),
                metodo=datos.get("metodo") or "transferencia",
                referencia=limpiar_texto(datos.get("referencia"), 60),
                usuario=usuario_actual()["email"],
            )
        )
        proveedor = Proveedor.query.get(cuenta.proveedor_id)
        if proveedor:
            proveedor.saldo_pendiente = round(max((proveedor.saldo_pendiente or 0) - monto, 0), 2)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo registrar el abono", 500)

    registrar("crear", "compras", "cuentas_por_pagar", cuenta_id, f"Abono {monto}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(cuenta.a_diccionario(), "Abono registrado")
