# ============================================================
# API de reportes, panel principal y respaldos.
# ============================================================
import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Blueprint, request

from app.config import Configuracion
from app.extensions import db
from app.models.compras import Compra, CuentaPorPagar
from app.models.inventario import Producto
from app.models.respaldo import Respaldo
from app.models.terceros import Cliente, Proveedor
from app.models.ventas import CuentaPorCobrar, Venta
from app.services import bcv_service
from app.services.auditoria_service import registrar
from app.services.google.drive_service import drive_service, DriveError
from app.utils.contexto import empresa_activa_id
from app.utils.fechas import a_fecha
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, solo_administrador, usuario_actual

reportes_bp = Blueprint("reportes", __name__, url_prefix="/api/reportes")


@reportes_bp.route("/dashboard", methods=["GET"])
@requiere_sesion
def dashboard():
    """Indicadores del panel principal."""
    empresa_id = empresa_activa_id()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    ventas_hoy = Venta.query.filter_by(empresa_id=empresa_id, estado="emitida", fecha=hoy).all()
    ventas_mes = (
        Venta.query.filter_by(empresa_id=empresa_id, estado="emitida")
        .filter(Venta.fecha >= inicio_mes)
        .all()
    )

    productos_bajo_stock = (
        Producto.query.filter_by(empresa_id=empresa_id, activo=True)
        .filter(Producto.stock_actual <= Producto.stock_minimo)
        .count()
    )

    cxc = CuentaPorCobrar.query.filter_by(empresa_id=empresa_id, estado="pendiente").all()
    cxp = CuentaPorPagar.query.filter_by(empresa_id=empresa_id, estado="pendiente").all()

    # Ventas de los ultimos 7 dias para la grafica.
    serie = []
    for indice in range(6, -1, -1):
        dia = hoy - timedelta(days=indice)
        total = sum(v.total_bolivares or 0 for v in ventas_mes if v.fecha == dia)
        total_dia = (
            sum(v.total_bolivares or 0 for v in ventas_hoy)
            if dia == hoy
            else total
        )
        serie.append({"fecha": dia.strftime("%d/%m"), "total": round(total_dia, 2)})

    return exito(
        {
            "tasa": bcv_service.obtener_tasa_actual(),
            "ventas_hoy_bs": round(sum(v.total_bolivares or 0 for v in ventas_hoy), 2),
            "ventas_hoy_cantidad": len(ventas_hoy),
            "ventas_mes_bs": round(sum(v.total_bolivares or 0 for v in ventas_mes), 2),
            "productos_bajo_stock": productos_bajo_stock,
            "total_clientes": Cliente.query.filter_by(empresa_id=empresa_id, activo=True).count(),
            "total_proveedores": Proveedor.query.filter_by(empresa_id=empresa_id, activo=True).count(),
            "por_cobrar_usd": round(sum(c.saldo for c in cxc), 2),
            "por_pagar_usd": round(sum(c.saldo for c in cxp), 2),
            "serie_ventas": serie,
        },
        "Indicadores del panel",
    )


@reportes_bp.route("/exportar/<string:tipo>", methods=["GET"])
@requiere_sesion
def exportar(tipo: str):
    """Exporta informacion a Excel segun el tipo solicitado."""
    from app.services import export_service

    empresa_id = empresa_activa_id()
    desde = a_fecha(request.args.get("desde"))
    hasta = a_fecha(request.args.get("hasta"))

    if tipo == "inventario":
        filas = [
            {
                "Codigo": p.codigo,
                "Nombre": p.nombre,
                "Costo USD": p.costo_divisa,
                "Precio USD": p.precio_divisa,
                "Stock": p.stock_actual,
                "Stock minimo": p.stock_minimo,
            }
            for p in Producto.query.filter_by(empresa_id=empresa_id).all()
        ]
        titulo = "Inventario"
    elif tipo == "ventas":
        consulta = Venta.query.filter_by(empresa_id=empresa_id)
        if desde:
            consulta = consulta.filter(Venta.fecha >= desde)
        if hasta:
            consulta = consulta.filter(Venta.fecha <= hasta)
        filas = [
            {
                "Fecha": v.fecha.isoformat() if v.fecha else "",
                "Factura": v.numero_factura,
                "Cliente": v.cliente.nombre if v.cliente else "Consumidor final",
                "Base USD": v.base_imponible,
                "IVA USD": v.iva,
                "IGTF Bs": v.igtf,
                "Total Bs": v.total_bolivares,
                "Estado": v.estado,
            }
            for v in consulta.order_by(Venta.fecha).all()
        ]
        titulo = "Ventas"
    elif tipo == "compras":
        filas = [
            {
                "Fecha": c.fecha.isoformat() if c.fecha else "",
                "Factura": c.numero_factura,
                "Proveedor": c.proveedor.nombre if c.proveedor else "",
                "Subtotal USD": c.subtotal,
                "IVA USD": c.iva,
                "Total USD": c.total,
            }
            for c in Compra.query.filter_by(empresa_id=empresa_id).order_by(Compra.fecha).all()
        ]
        titulo = "Compras"
    elif tipo == "cxc":
        filas = [
            {
                "Cliente": c.cliente.nombre if c.cliente else "",
                "Monto USD": c.monto_total,
                "Saldo USD": c.saldo,
                "Vence": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else "",
                "Estado": c.estado,
            }
            for c in CuentaPorCobrar.query.filter_by(empresa_id=empresa_id).all()
        ]
        titulo = "Cuentas por cobrar"
    elif tipo == "cxp":
        filas = [
            {
                "Proveedor": c.proveedor.nombre if c.proveedor else "",
                "Monto USD": c.monto_total,
                "Saldo USD": c.saldo,
                "Vence": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else "",
                "Estado": c.estado,
            }
            for c in CuentaPorPagar.query.filter_by(empresa_id=empresa_id).all()
        ]
        titulo = "Cuentas por pagar"
    elif tipo == "clientes":
        filas = [
            {"Nombre": c.nombre, "RIF": c.rif, "Telefono": c.telefono, "Saldo USD": c.saldo_pendiente}
            for c in Cliente.query.filter_by(empresa_id=empresa_id).all()
        ]
        titulo = "Clientes"
    elif tipo == "proveedores":
        filas = [
            {"Nombre": p.nombre, "RIF": p.rif, "Telefono": p.telefono, "Saldo USD": p.saldo_pendiente}
            for p in Proveedor.query.filter_by(empresa_id=empresa_id).all()
        ]
        titulo = "Proveedores"
    else:
        return error("Tipo de reporte no reconocido", 400)

    ruta = export_service.exportar_excel(filas, titulo, f"{tipo}_{datetime.now():%Y%m%d_%H%M%S}")
    return exito({"archivo": ruta}, "Reporte exportado")


# ------------------------------------------------------------
# Respaldos
# ------------------------------------------------------------
@reportes_bp.route("/respaldos", methods=["GET"])
@requiere_sesion
def listar_respaldos():
    respaldos = Respaldo.query.order_by(Respaldo.id.desc()).limit(50).all()
    return exito([r.a_diccionario() for r in respaldos], "Respaldos")


@reportes_bp.route("/respaldos", methods=["POST"])
@solo_administrador
def crear_respaldo():
    """Crea una copia de seguridad de la base de datos local."""
    try:
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"respaldo_fiskor_{marca}.db"
        ruta = Configuracion.RUTA_RESPALDOS / nombre
        # Usamos la API de respaldo de sqlite para copiar de forma segura.
        origen = sqlite3.connect(Configuracion.RUTA_SQLITE)
        destino = sqlite3.connect(str(ruta))
        with destino:
            origen.backup(destino)
        destino.close()
        origen.close()

        respaldo = Respaldo(
            nombre_archivo=nombre,
            ruta=str(ruta),
            tipo="completo",
            tamano_bytes=os.path.getsize(ruta),
            generado_por=usuario_actual()["email"],
            nota="Respaldo manual",
        )
        db.session.add(respaldo)
        db.session.flush()  # para obtener id antes de commit completo

        # Subida opcional a Google Drive si esta configurado.
        if drive_service.disponible():
            try:
                subida = drive_service.subir_respaldo(str(ruta), nombre, "Respaldo manual Fiskor ERP")
                respaldo.drive_id = subida.get("id", "")
                respaldo.drive_link = subida.get("webViewLink", "")
                respaldo.drive_subido = True
                registrar("subir", "reportes", "respaldos", respaldo.id, "Subido a Google Drive",
                          usuario=usuario_actual()["email"], ip=request.remote_addr)
            except DriveError as exc:
                registro.warning("No se pudo subir el respaldo a Google Drive: %s", exc)
            except Exception as exc:
                registro.warning("Error inesperado al subir respaldo a Drive: %s", exc)

        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo generar el respaldo", 500)

    registrar("crear", "reportes", "respaldos", respaldo.id, nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(respaldo.a_diccionario(), "Respaldo generado", 201)
