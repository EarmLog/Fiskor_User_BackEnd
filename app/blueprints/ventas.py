# ============================================================
# API de ventas, facturacion (POS) y cuentas por cobrar.
#
# Reglas aplicadas al emitir una venta:
#   - IVA del 16% por renglon.
#   - IGTF del 3% solo en pagos con divisas en efectivo.
#   - Doble moneda: precios en divisas, totales tambien en Bs.
#   - Descuento atomico de inventario (a prueba de concurrencia).
# ============================================================
from datetime import date

from flask import Blueprint, request

from app.config import Configuracion
from app.extensions import db
from app.models.inventario import Producto
from app.models.ventas import (
    AbonoCxC,
    CuentaPorCobrar,
    PagoVenta,
    Venta,
    VentaDetalle,
)
from app.services import bcv_service, fiscal_service, inventario_service
from app.services.auditoria_service import registrar
from app.services.inventario_service import StockInsuficiente
from app.utils.contexto import empresa_activa_id, parametros_paginacion
from app.utils.fechas import a_fecha
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto

ventas_bp = Blueprint("ventas", __name__, url_prefix="/api/ventas")


@ventas_bp.route("", methods=["GET"])
@requiere_sesion
def listar():
    """Lista las ventas con filtros por fecha y estado."""
    empresa_id = empresa_activa_id()
    pagina, por_pagina = parametros_paginacion()
    consulta = Venta.query.filter_by(empresa_id=empresa_id)

    desde = a_fecha(request.args.get("desde"))
    hasta = a_fecha(request.args.get("hasta"))
    if desde:
        consulta = consulta.filter(Venta.fecha >= desde)
    if hasta:
        consulta = consulta.filter(Venta.fecha <= hasta)
    estado = request.args.get("estado")
    if estado:
        consulta = consulta.filter_by(estado=estado)

    total = consulta.count()
    ventas = consulta.order_by(Venta.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    datos = []
    for venta in ventas:
        item = venta.a_diccionario()
        item["cliente_nombre"] = venta.cliente.nombre if venta.cliente else "Consumidor final"
        item["cliente_rif"] = venta.cliente.rif if venta.cliente else ""
        datos.append(item)
    return exito({"items": datos, "total": total, "pagina": pagina, "por_pagina": por_pagina}, "Ventas")


@ventas_bp.route("/<int:venta_id>", methods=["GET"])
@requiere_sesion
def obtener(venta_id: int):
    venta = Venta.query.get(venta_id)
    if venta is None:
        return error("Venta no encontrada", 404)
    datos = venta.a_diccionario()
    datos["cliente_nombre"] = venta.cliente.nombre if venta.cliente else "Consumidor final"
    datos["cliente_rif"] = venta.cliente.rif if venta.cliente else ""
    datos["detalles"] = [d.a_diccionario() for d in venta.detalles]
    datos["pagos"] = [p.a_diccionario() for p in venta.pagos]
    return exito(datos, "Venta")


@ventas_bp.route("", methods=["POST"])
@requiere_sesion
def crear():
    """Registra una venta nueva desde el POS."""
    datos = request.get_json(silent=True) or {}
    lineas = datos.get("lineas") or []
    if not lineas:
        return error("Debe agregar al menos un producto a la venta", 400)

    empresa_id = empresa_activa_id()
    usuario = usuario_actual()["email"]
    condicion = (datos.get("condicion") or "contado").lower()
    tipo = (datos.get("tipo") or "factura").lower()

    # Tasa del dia (debe existir para poder facturar).
    tasa_datos = bcv_service.obtener_tasa_actual()
    tasa = float(tasa_datos["valor"] or 0)
    if tasa <= 0:
        return error("No hay una tasa de cambio valida. Actualicela antes de facturar", 409)

    # Recalculamos los totales en el servidor (no confiamos en el frontend).
    resumen = fiscal_service.resumir_lineas(lineas)
    if resumen["base_imponible"] <= 0:
        return error("El total de la venta debe ser mayor que cero", 400)

    pagos = datos.get("pagos") or []
    if condicion == "credito" and not datos.get("cliente_id"):
        return error("Para vender a credito debe seleccionar un cliente", 400)

    # IGTF: 3% sobre pagos en divisas en efectivo.
    igtf_total = 0.0
    pagos_preparados = []
    for pago in pagos:
        metodo = (pago.get("metodo") or "efectivo_bs").lower()
        monto = float(pago.get("monto") or 0)
        igtf_pago = 0.0
        if metodo == "efectivo_divisa":
            igtf_pago = fiscal_service.calcular_igtf(monto, tasa, Configuracion.PORCENTAJE_IGTF)
            igtf_total += igtf_pago
        pagos_preparados.append(
            {
                "metodo": metodo,
                "moneda": pago.get("moneda") or ("USD" if metodo == "efectivo_divisa" else "VES"),
                "monto": monto,
                "referencia": limpiar_texto(pago.get("referencia"), 60),
                "igtf_aplicado": igtf_pago,
            }
        )

    total_divisas = round(resumen["base_imponible"] + resumen["iva"], 2)
    total_bolivares = round(total_divisas * tasa + igtf_total, 2)

    try:
        # 1) Creamos la venta.
        venta = Venta(
            empresa_id=empresa_id,
            cliente_id=datos.get("cliente_id") or None,
            numero_factura=fiscal_service.siguiente_numero_factura(empresa_id, "venta"),
            numero_control=fiscal_service.siguiente_numero_control(empresa_id, "venta"),
            fecha=a_fecha(datos.get("fecha")) or date.today(),
            tipo=tipo,
            condicion=condicion,
            subtotal=resumen["subtotal"],
            descuento=resumen["descuento"],
            base_imponible=resumen["base_imponible"],
            iva=resumen["iva"],
            igtf=igtf_total,
            total_divisas=total_divisas,
            total_bolivares=total_bolivares,
            tasa_aplicada=tasa,
            observaciones=limpiar_texto(datos.get("observaciones"), 255),
            usuario=usuario,
        )
        db.session.add(venta)
        db.session.flush()  # para obtener el id antes de los detalles

        # 2) Detalles y descuento de inventario.
        for linea, calculado in zip(lineas, resumen["detalle"]):
            producto_id = linea.get("producto_id")
            cantidad = float(linea.get("cantidad") or 0)
            detalle = VentaDetalle(
                venta_id=venta.id,
                producto_id=producto_id,
                descripcion=limpiar_texto(linea.get("descripcion"), 180),
                cantidad=cantidad,
                precio_unitario=float(linea.get("precio_unitario") or 0),
                iva_porcentaje=float(linea.get("iva_porcentaje") or 0),
                descuento=float(linea.get("descuento") or 0),
                total=calculado["total"],
            )
            db.session.add(detalle)

            # Descontamos stock de forma atomica.
            if producto_id:
                inventario_service.descontar_stock(
                    producto_id, cantidad, "Venta", venta.numero_factura, usuario
                )
                # Actualizamos el nombre por si el producto cambio.
                producto = Producto.query.get(producto_id)
                if producto and not detalle.descripcion:
                    detalle.descripcion = producto.nombre

        # 3) Pagos.
        for pago in pagos_preparados:
            db.session.add(
                PagoVenta(
                    venta_id=venta.id,
                    metodo=pago["metodo"],
                    moneda=pago["moneda"],
                    monto=pago["monto"],
                    tasa=tasa,
                    igtf_aplicado=pago["igtf_aplicado"],
                    referencia=pago["referencia"],
                )
            )

        # 4) Cuenta por cobrar si es a credito.
        if condicion == "credito":
            from datetime import timedelta

            vencimiento = (a_fecha(datos.get("fecha")) or date.today()) + timedelta(days=int(datos.get("dias_credito") or 30))
            db.session.add(
                CuentaPorCobrar(
                    empresa_id=empresa_id,
                    cliente_id=datos["cliente_id"],
                    venta_id=venta.id,
                    monto_total=total_divisas,
                    saldo=total_divisas,
                    fecha_emision=venta.fecha,
                    fecha_vencimiento=vencimiento,
                    estado="pendiente",
                )
            )
            from app.models.terceros import Cliente

            cliente = Cliente.query.get(datos["cliente_id"])
            if cliente:
                cliente.saldo_pendiente = round((cliente.saldo_pendiente or 0) + total_divisas, 2)

        db.session.commit()
    except StockInsuficiente as exc:
        db.session.rollback()
        return error(str(exc), 409)
    except Exception as exc:
        db.session.rollback()
        return error("No se pudo registrar la venta. Verifique los datos ingresados", 500)

    registrar("crear", "ventas", "ventas", venta.id,
              f"Venta {venta.numero_factura} por Bs. {total_bolivares:.2f}",
              usuario=usuario, ip=request.remote_addr)
    return exito({"id": venta.id, "numero_factura": venta.numero_factura}, "Venta registrada", 201)


@ventas_bp.route("/<int:venta_id>/anular", methods=["POST"])
@requiere_sesion
def anular(venta_id: int):
    """Anula una venta y devuelve el inventario."""
    venta = Venta.query.get(venta_id)
    if venta is None:
        return error("Venta no encontrada", 404)
    if venta.estado == "anulada":
        return error("La venta ya estaba anulada", 400)

    usuario = usuario_actual()["email"]
    try:
        for detalle in venta.detalles:
            if detalle.producto_id:
                inventario_service.aumentar_stock(
                    detalle.producto_id,
                    detalle.cantidad,
                    detalle.precio_unitario,
                    "Anulacion de venta",
                    venta.numero_factura,
                    usuario,
                )
        # Anulamos la cuenta por cobrar si existia.
        cuenta = CuentaPorCobrar.query.filter_by(venta_id=venta.id).first()
        if cuenta and cuenta.estado != "pagada":
            cuenta.estado = "anulada"
            from app.models.terceros import Cliente

            cliente = Cliente.query.get(cuenta.cliente_id)
            if cliente:
                cliente.saldo_pendiente = round((cliente.saldo_pendiente or 0) - cuenta.saldo, 2)
        venta.estado = "anulada"
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo anular la venta", 500)

    registrar("anular", "ventas", "ventas", venta.id, f"Anulacion de {venta.numero_factura}",
              usuario=usuario, ip=request.remote_addr)
    return exito(None, "Venta anulada")


def _datos_documento(venta: Venta) -> tuple[dict, dict, list[dict], dict]:
    """Prepara (empresa, venta, detalles, plantilla) para los documentos."""
    from app.models.documentos import PlantillaDocumento
    from app.models.empresa import Empresa

    empresa = Empresa.query.get(venta.empresa_id)
    empresa_datos = empresa.a_diccionario() if empresa else {"nombre": "Fiskor ERP"}
    venta_datos = venta.a_diccionario()
    venta_datos["cliente_nombre"] = venta.cliente.nombre if venta.cliente else "Consumidor final"
    venta_datos["cliente_rif"] = venta.cliente.rif if venta.cliente else ""
    venta_datos["pagos"] = [p.a_diccionario() for p in venta.pagos]
    detalles = [d.a_diccionario() for d in venta.detalles]
    plantilla = PlantillaDocumento.obtener_para(venta.empresa_id, venta.tipo)
    return empresa_datos, venta_datos, detalles, (plantilla.a_diccionario() if plantilla else {})


@ventas_bp.route("/<int:venta_id>/pdf", methods=["GET"])
@requiere_sesion
def exportar_pdf(venta_id: int):
    """Genera la factura/nota de entrega en PDF (con logo y sello)."""
    from pathlib import Path

    from app.services import export_service

    venta = Venta.query.get(venta_id)
    if venta is None:
        return error("Venta no encontrada", 404)

    empresa_datos, venta_datos, detalles, plantilla = _datos_documento(venta)
    try:
        ruta = export_service.generar_factura_pdf(empresa_datos, venta_datos, detalles, plantilla)
    except Exception:
        return error("No se pudo generar el documento PDF", 500)
    return exito(
        {"archivo": ruta, "categoria": "pdf", "nombre": Path(ruta).name}, "Documento generado"
    )


@ventas_bp.route("/<int:venta_id>/word", methods=["GET"])
@requiere_sesion
def exportar_word(venta_id: int):
    """Genera la factura en Word (editable)."""
    from pathlib import Path

    from app.services import export_service

    venta = Venta.query.get(venta_id)
    if venta is None:
        return error("Venta no encontrada", 404)
    empresa_datos, venta_datos, detalles, _ = _datos_documento(venta)
    ruta = export_service.generar_factura_word(empresa_datos, venta_datos, detalles)
    return exito(
        {"archivo": ruta, "categoria": "word", "nombre": Path(ruta).name}, "Documento generado"
    )


@ventas_bp.route("/<int:venta_id>/fiscal", methods=["POST"])
@requiere_sesion
def imprimir_fiscal(venta_id: int):
    """Envia la venta a la impresora fiscal (SENIAT)."""
    from app.services import impresora_fiscal_service

    venta = Venta.query.get(venta_id)
    if venta is None:
        return error("Venta no encontrada", 404)
    if venta.estado != "emitida":
        return error("Solo se pueden imprimir fiscalmente ventas emitidas", 400)

    empresa_datos, venta_datos, detalles, _ = _datos_documento(venta)
    resultado = impresora_fiscal_service.imprimir_venta(
        empresa_datos, venta_datos, detalles, usuario=usuario_actual()["email"]
    )
    if not resultado.get("exito"):
        return error(resultado.get("mensaje", "Fallo la impresion fiscal"), 502, resultado)
    return exito(resultado, resultado.get("mensaje", "Documento fiscal emitido"))


# ------------------------------------------------------------
# Cuentas por cobrar
# ------------------------------------------------------------
@ventas_bp.route("/cxc", methods=["GET"])
@requiere_sesion
def listar_cxc():
    empresa_id = empresa_activa_id()
    estado = request.args.get("estado", "pendiente")
    consulta = CuentaPorCobrar.query.filter_by(empresa_id=empresa_id)
    if estado and estado != "todas":
        consulta = consulta.filter_by(estado=estado)
    cuentas = consulta.order_by(CuentaPorCobrar.fecha_vencimiento).all()
    datos = []
    for cuenta in cuentas:
        item = cuenta.a_diccionario()
        item["cliente_nombre"] = cuenta.cliente.nombre if cuenta.cliente else ""
        item["dias_vencida"] = (
            (date.today() - cuenta.fecha_vencimiento).days
            if cuenta.fecha_vencimiento and cuenta.estado == "pendiente"
            else 0
        )
        datos.append(item)
    return exito(datos, "Cuentas por cobrar")


@ventas_bp.route("/cxc/<int:cuenta_id>/abono", methods=["POST"])
@requiere_sesion
def abonar_cxc(cuenta_id: int):
    """Registra un abono a una cuenta por cobrar."""
    cuenta = CuentaPorCobrar.query.get(cuenta_id)
    if cuenta is None:
        return error("Cuenta por cobrar no encontrada", 404)
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
            AbonoCxC(
                cuenta_id=cuenta.id,
                monto=monto,
                moneda=datos.get("moneda") or "USD",
                tasa=float(datos.get("tasa") or 1),
                metodo=datos.get("metodo") or "efectivo_bs",
                referencia=limpiar_texto(datos.get("referencia"), 60),
                usuario=usuario_actual()["email"],
            )
        )
        from app.models.terceros import Cliente

        cliente = Cliente.query.get(cuenta.cliente_id)
        if cliente:
            cliente.saldo_pendiente = round(max((cliente.saldo_pendiente or 0) - monto, 0), 2)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo registrar el abono", 500)

    registrar("crear", "ventas", "cuentas_por_cobrar", cuenta_id, f"Abono {monto}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(cuenta.a_diccionario(), "Abono registrado")
