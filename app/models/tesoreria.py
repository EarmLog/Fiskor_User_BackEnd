# ============================================================
# Caja y bancos.
# Controlamos los ingresos y egresos de efectivo, pago movil,
# transferencias y punto de venta, ademas de la caja chica.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class CuentaBancaria(ModeloBase):
    """Cuenta bancaria de la empresa."""

    __tablename__ = "cuentas_bancarias"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    banco = db.Column(db.String(80), nullable=False)
    numero_cuenta = db.Column(db.String(30), default="")
    tipo = db.Column(db.String(20), default="corriente")  # corriente/ahorro
    moneda = db.Column(db.String(10), default="VES")
    titular = db.Column(db.String(150), default="")
    rif_titular = db.Column(db.String(20), default="")
    saldo = db.Column(db.Float, default=0.0)
    activo = db.Column(db.Boolean, default=True)


class SesionCaja(ModeloBase):
    """Apertura y cierre de la caja de un cajero."""

    __tablename__ = "sesiones_caja"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    usuario = db.Column(db.String(150), default="")
    monto_inicial = db.Column(db.Float, default=0.0)
    abierta_en = db.Column(db.DateTime, nullable=True)
    monto_cierre = db.Column(db.Float, nullable=True)
    cerrada_en = db.Column(db.DateTime, nullable=True)
    diferencia = db.Column(db.Float, default=0.0)
    observaciones = db.Column(db.String(255), default="")
    estado = db.Column(db.String(20), default="abierta")  # abierta/cerrada

    movimientos = db.relationship(
        "MovimientoCaja", backref="sesion", cascade="all, delete-orphan", lazy=True
    )


class MovimientoCaja(ModeloBase):
    """Cada ingreso o egreso de dinero."""

    __tablename__ = "movimientos_caja"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    sesion_caja_id = db.Column(db.Integer, db.ForeignKey("sesiones_caja.id"), nullable=True)

    tipo = db.Column(db.String(20), default="ingreso")  # ingreso/egreso
    concepto = db.Column(db.String(180), default="")
    categoria = db.Column(db.String(60), default="venta")  # venta/caja_chica/otros
    # metodo: efectivo_bs, efectivo_divisa, pago_movil, transferencia, punto
    metodo = db.Column(db.String(30), default="efectivo_bs")
    moneda = db.Column(db.String(10), default="VES")
    monto = db.Column(db.Float, default=0.0)
    tasa = db.Column(db.Float, default=1.0)
    referencia = db.Column(db.String(60), default="")
    usuario = db.Column(db.String(150), default="")
    fecha = db.Column(db.Date, nullable=True)
