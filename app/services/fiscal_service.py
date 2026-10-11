# ============================================================
# Logica de calculo fiscal para Venezuela.
#   - IVA general (16% por defecto)
#   - IGTF (3%) en pagos con divisas en efectivo
#   - Retenciones de IVA e ISLR
#   - Correlativos de facturas y notas
# ============================================================
from datetime import date

from app.config import Configuracion
from app.extensions import db
from app.models.compras import Compra
from app.models.ventas import Venta
from app.utils.respuestas import redondear


def calcular_iva(base_imponible: float, porcentaje: float | None = None) -> float:
    """Calcula el IVA sobre una base imponible."""
    porcentaje = Configuracion.PORCENTAJE_IVA if porcentaje is None else porcentaje
    return redondear(float(base_imponible) * float(porcentaje) / 100.0)


def calcular_igtf(monto_en_divisas: float, tasa: float, porcentaje: float | None = None) -> float:
    """Calcula el IGTF (3%) para pagos en divisas en efectivo.

    El IGTF se aplica sobre el monto en bolivares del pago en efectivo
    en moneda extranjera.
    """
    porcentaje = Configuracion.PORCENTAJE_IGTF if porcentaje is None else porcentaje
    monto_bolivares = float(monto_en_divisas) * float(tasa)
    return redondear(monto_bolivares * float(porcentaje) / 100.0)


def calcular_retencion_iva(base_imponible: float, porcentaje: float) -> float:
    """Retencion de IVA: es un porcentaje del IVA facturado.

    En Venezuela se retiene el 75% del IVA a contribuyentes especiales
    y el 100% a los demas. El porcentaje se define por proveedor.
    """
    porcentaje = 75.0 if porcentaje is None else float(porcentaje)
    iva_facturado = calcular_iva(base_imponible)
    return redondear(iva_facturado * porcentaje / 100.0)


def calcular_retencion_islr(base_imponible: float, porcentaje: float, sustraendo: float = 0.0) -> float:
    """Retencion de ISLR: tarifa por porcentaje sobre el monto, menos sustraendo."""
    if not porcentaje:
        return 0.0
    monto = float(base_imponible) * float(porcentaje) / 100.0
    resultado = monto - float(sustraendo or 0.0)
    return redondear(max(resultado, 0.0))


def resumir_lineas(lineas: list[dict]) -> dict:
    """Recalcula los totales de un grupo de renglones.

    Cada linea debe traer: cantidad, precio_unitario, iva_porcentaje,
    y opcionalmente descuento.
    """
    subtotal = 0.0
    descuento_total = 0.0
    base_imponible = 0.0
    iva_total = 0.0
    detalle = []
    for linea in lineas:
        cantidad = float(linea.get("cantidad") or 0)
        precio = float(linea.get("precio_unitario") or 0)
        descuento = float(linea.get("descuento") or 0)
        porcentaje_iva = float(linea.get("iva_porcentaje") or 0)
        bruto = cantidad * precio
        neto = bruto - descuento
        iva_linea = redondear(neto * porcentaje_iva / 100.0)
        subtotal += bruto
        descuento_total += descuento
        base_imponible += neto
        iva_total += iva_linea
        detalle.append(
            {
                **linea,
                "total": redondear(neto + iva_linea),
                "iva_monto": iva_linea,
            }
        )
    return {
        "subtotal": redondear(subtotal),
        "descuento": redondear(descuento_total),
        "base_imponible": redondear(base_imponible),
        "iva": redondear(iva_total),
        "detalle": detalle,
    }


# ------------------------------------------------------------
# Correlativos de documentos
# ------------------------------------------------------------
def siguiente_numero_factura(empresa_id: int, tipo: str = "venta") -> str:
    """Genera el proximo numero de factura/nota de forma incremental."""
    if tipo == "venta":
        ultimo = (
            Venta.query.filter_by(empresa_id=empresa_id, tipo="factura")
            .order_by(Venta.id.desc())
            .first()
        )
        prefijo = "F"
    else:
        ultimo = (
            Compra.query.filter_by(empresa_id=empresa_id, tipo="factura")
            .order_by(Compra.id.desc())
            .first()
        )
        prefijo = "C"
    consecutivo = (ultimo.id + 1) if ultimo else 1
    anio = date.today().year
    return f"{prefijo}{anio}-{consecutivo:06d}"


def siguiente_numero_control(empresa_id: int, tipo: str = "venta") -> str:
    """Genera el correlativo del numero de control fiscal."""
    if tipo == "venta":
        total = Venta.query.filter_by(empresa_id=empresa_id).count()
    else:
        total = Compra.query.filter_by(empresa_id=empresa_id).count()
    return f"{total + 1:08d}"


def siguiente_numero_retencion(empresa_id: int, tipo: str = "IVA") -> str:
    """Genera el correlativo de un comprobante de retencion."""
    from app.models.fiscal import Retencion

    cantidad = Retencion.query.filter_by(empresa_id=empresa_id, tipo=tipo).count()
    return f"{tipo}-{date.today().year}-{cantidad + 1:06d}"
