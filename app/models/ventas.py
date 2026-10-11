# ============================================================
# Ventas, facturacion (POS) y cuentas por cobrar.
#
# Reglas fiscales de Venezuela aplicadas aqui:
#  - IVA general del 16%.
#  - IGTF del 3% cuando se paga en divisas en efectivo.
#  - Doble moneda: los precios base estan en divisas y se
#    convierten a bolivares con la tasa del dia.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Venta(ModeloBase):
    """Factura o nota de entrega emitida a un cliente."""

    __tablename__ = "ventas"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)

    numero_factura = db.Column(db.String(40), default="")
    numero_control = db.Column(db.String(40), default="")
    fecha = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(20), default="factura")  # factura/nota_entrega
    condicion = db.Column(db.String(20), default="contado")  # contado/credito

    # Montos: los base en divisas, los totales tambien en bolivares.
    subtotal = db.Column(db.Float, default=0.0)
    descuento = db.Column(db.Float, default=0.0)
    base_imponible = db.Column(db.Float, default=0.0)
    iva = db.Column(db.Float, default=0.0)
    igtf = db.Column(db.Float, default=0.0)
    total_divisas = db.Column(db.Float, default=0.0)
    total_bolivares = db.Column(db.Float, default=0.0)
    tasa_aplicada = db.Column(db.Float, default=0.0)

    estado = db.Column(db.String(20), default="emitida")  # emitida/anulada/pagada
    observaciones = db.Column(db.String(255), default="")
    usuario = db.Column(db.String(150), default="")

    cliente = db.relationship("Cliente", backref="ventas", lazy=True)
    detalles = db.relationship(
        "VentaDetalle", backref="venta", cascade="all, delete-orphan", lazy=True
    )
    pagos = db.relationship(
        "PagoVenta", backref="venta", cascade="all, delete-orphan", lazy=True
    )


class VentaDetalle(ModeloBase):
    """Renglon de una venta."""

    __tablename__ = "ventas_detalle"

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=True)
    descripcion = db.Column(db.String(180), default="")
    cantidad = db.Column(db.Float, default=0.0)
    precio_unitario = db.Column(db.Float, default=0.0)  # en divisas
    iva_porcentaje = db.Column(db.Float, default=16.0)
    descuento = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)  # en divisas

    producto = db.relationship("Producto", lazy=True)


class PagoVenta(ModeloBase):
    """Forma de pago asociada a una venta (puede haber varias)."""

    __tablename__ = "pagos_venta"

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False)
    # metodo: efectivo_divisa, efectivo_bs, pago_movil, transferencia,
    #         punto_debito, credito
    metodo = db.Column(db.String(30), default="efectivo_bs")
    moneda = db.Column(db.String(10), default="VES")
    monto = db.Column(db.Float, default=0.0)
    tasa = db.Column(db.Float, default=1.0)
    igtf_aplicado = db.Column(db.Float, default=0.0)
    referencia = db.Column(db.String(60), default="")


class CuentaPorCobrar(ModeloBase):
    """Deuda pendiente de un cliente."""

    __tablename__ = "cuentas_por_cobrar"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=True)

    monto_total = db.Column(db.Float, default=0.0)  # en divisas
    saldo = db.Column(db.Float, default=0.0)
    fecha_emision = db.Column(db.Date, nullable=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(20), default="pendiente")  # pendiente/pagada/vencida

    cliente = db.relationship("Cliente", backref="cuentas_por_cobrar", lazy=True)
    abonos = db.relationship(
        "AbonoCxC", backref="cuenta", cascade="all, delete-orphan", lazy=True
    )


class AbonoCxC(ModeloBase):
    """Abono recibido de un cliente sobre su deuda."""

    __tablename__ = "abonos_cxc"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_por_cobrar.id"), nullable=False)
    monto = db.Column(db.Float, default=0.0)  # en divisas
    moneda = db.Column(db.String(10), default="USD")
    tasa = db.Column(db.Float, default=1.0)
    metodo = db.Column(db.String(30), default="efectivo_bs")
    referencia = db.Column(db.String(60), default="")
    usuario = db.Column(db.String(150), default="")
