# ============================================================
# Compras a proveedores y cuentas por pagar.
# Al registrar una compra se aumenta el inventario y se crea
# (si es a credito) una cuenta por pagar.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Compra(ModeloBase):
    """Factura o nota de entrega recibida de un proveedor."""

    __tablename__ = "compras"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=False)

    numero_factura = db.Column(db.String(40), default="")
    numero_control = db.Column(db.String(40), default="")
    fecha = db.Column(db.Date, nullable=False)
    # tipo: factura, nota_entrega
    tipo = db.Column(db.String(20), default="factura")
    condicion = db.Column(db.String(20), default="contado")  # contado/credito

    # Montos en divisas
    subtotal = db.Column(db.Float, default=0.0)
    iva = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)

    retencion_iva = db.Column(db.Float, default=0.0)
    retencion_islr = db.Column(db.Float, default=0.0)

    estado = db.Column(db.String(20), default="registrada")  # registrada/anulada/pagada
    observaciones = db.Column(db.String(255), default="")
    usuario = db.Column(db.String(150), default="")

    proveedor = db.relationship("Proveedor", backref="compras", lazy=True)
    detalles = db.relationship(
        "CompraDetalle", backref="compra", cascade="all, delete-orphan", lazy=True
    )


class CompraDetalle(ModeloBase):
    """Renglon de una compra."""

    __tablename__ = "compras_detalle"

    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey("compras.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=True)
    descripcion = db.Column(db.String(180), default="")
    cantidad = db.Column(db.Float, default=0.0)
    costo_unitario = db.Column(db.Float, default=0.0)  # en divisas
    iva_porcentaje = db.Column(db.Float, default=16.0)
    total = db.Column(db.Float, default=0.0)

    producto = db.relationship("Producto", lazy=True)


class CuentaPorPagar(ModeloBase):
    """Deuda pendiente con un proveedor."""

    __tablename__ = "cuentas_por_pagar"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=False)
    compra_id = db.Column(db.Integer, db.ForeignKey("compras.id"), nullable=True)

    monto_total = db.Column(db.Float, default=0.0)  # en divisas
    saldo = db.Column(db.Float, default=0.0)
    fecha_emision = db.Column(db.Date, nullable=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(20), default="pendiente")  # pendiente/pagada/vencida

    proveedor = db.relationship("Proveedor", backref="cuentas_por_pagar", lazy=True)
    abonos = db.relationship(
        "AbonoCxP", backref="cuenta", cascade="all, delete-orphan", lazy=True
    )


class AbonoCxP(ModeloBase):
    """Pago parcial o total de una cuenta por pagar."""

    __tablename__ = "abonos_cxp"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_por_pagar.id"), nullable=False)
    monto = db.Column(db.Float, default=0.0)  # en divisas
    moneda = db.Column(db.String(10), default="USD")
    tasa = db.Column(db.Float, default=1.0)
    metodo = db.Column(db.String(30), default="transferencia")
    referencia = db.Column(db.String(60), default="")
    usuario = db.Column(db.String(150), default="")
