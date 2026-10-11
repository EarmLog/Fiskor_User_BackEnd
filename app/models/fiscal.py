# ============================================================
# Modulo fiscal y tributario (SENIAT).
# Guardamos los comprobantes de retencion de IVA e ISLR.
# Los libros de compras y ventas se generan por consulta a
# partir de las facturas registradas.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Retencion(ModeloBase):
    """Comprobante de retencion (IVA o ISLR)."""

    __tablename__ = "retenciones"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)

    tipo = db.Column(db.String(10), default="IVA")  # IVA / ISLR
    numero_comprobante = db.Column(db.String(40), default="")
    fecha = db.Column(db.Date, nullable=False)
    periodo = db.Column(db.String(20), default="")  # MM/YYYY

    # Sujeto retenido
    sujeto_tipo = db.Column(db.String(20), default="proveedor")  # proveedor/cliente
    sujeto_id = db.Column(db.Integer, nullable=True)
    sujeto_nombre = db.Column(db.String(180), default="")
    sujeto_rif = db.Column(db.String(20), default="")

    # Referencia del documento
    numero_documento = db.Column(db.String(40), default="")
    numero_control = db.Column(db.String(40), default="")

    base_imponible = db.Column(db.Float, default=0.0)
    porcentaje = db.Column(db.Float, default=0.0)
    monto_retenido = db.Column(db.Float, default=0.0)
    sustraendo = db.Column(db.Float, default=0.0)
    moneda = db.Column(db.String(10), default="VES")
    tasa = db.Column(db.Float, default=1.0)

    estado = db.Column(db.String(20), default="emitida")  # emitida/anulada
    usuario = db.Column(db.String(150), default="")


class LogImpresionFiscal(ModeloBase):
    """Bitacora de cada intento de impresion en la impresora fiscal.

    Guardamos la trama enviada, el puerto usado y el resultado. Esto
    sirve de respaldo legal: deja constancia de que se intento emitir
    el documento fiscal y que respondio la impresora (SENIAT).
    """

    __tablename__ = "log_impresion_fiscal"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=True)

    # Tipo de operacion fiscal: venta / nota_credito / reporte_z / reporte_x
    operacion = db.Column(db.String(30), default="venta")
    puerto = db.Column(db.String(60), default="")
    protocolo = db.Column(db.String(30), default="HKA")
    trama = db.Column(db.Text, default="")
    respuesta = db.Column(db.Text, default="")
    exito = db.Column(db.Boolean, default=False)
    simulado = db.Column(db.Boolean, default=False)
    mensaje = db.Column(db.String(255), default="")
    usuario = db.Column(db.String(150), default="")
