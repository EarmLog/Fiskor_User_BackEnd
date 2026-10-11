# ============================================================
# Clientes y proveedores (los "terceros" del negocio).
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Cliente(ModeloBase):
    """Persona o empresa a la que le vendemos."""

    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    codigo = db.Column(db.String(20), default="")
    nombre = db.Column(db.String(150), nullable=False)
    rif = db.Column(db.String(20), default="")  # RIF o cedula
    tipo_documento = db.Column(db.String(20), default="RIF")  # RIF, V, E, J
    direccion = db.Column(db.String(255), default="")
    telefono = db.Column(db.String(40), default="")
    email = db.Column(db.String(120), default="")

    contribuyente_especial = db.Column(db.Boolean, default=False)
    retencion_iva = db.Column(db.Float, default=0.0)  # % que se le retiene

    limite_credito = db.Column(db.Float, default=0.0)  # en divisas
    saldo_pendiente = db.Column(db.Float, default=0.0)  # en divisas
    activo = db.Column(db.Boolean, default=True)


class Proveedor(ModeloBase):
    """Persona o empresa que nos surte mercancia."""

    __tablename__ = "proveedores"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    codigo = db.Column(db.String(20), default="")
    nombre = db.Column(db.String(150), nullable=False)
    rif = db.Column(db.String(20), default="")
    direccion = db.Column(db.String(255), default="")
    telefono = db.Column(db.String(40), default="")
    email = db.Column(db.String(120), default="")
    contacto = db.Column(db.String(120), default="")

    contribuyente_especial = db.Column(db.Boolean, default=False)
    retencion_iva = db.Column(db.Float, default=75.0)  # % retencion de IVA a proveedores
    retencion_islr = db.Column(db.Float, default=5.0)  # % de ISLR a aplicar
    dias_credito = db.Column(db.Integer, default=30)

    saldo_pendiente = db.Column(db.Float, default=0.0)  # en divisas
    activo = db.Column(db.Boolean, default=True)
