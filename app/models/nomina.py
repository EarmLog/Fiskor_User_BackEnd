# ============================================================
# Nomina y recursos humanos (adaptado a la LOTTT).
# La ley venezolana exige deducciones de:
#   - SSO  (Seguro Social Obligatorio)
#   - RPE  (Regimen Prestacional de Empleo / paro forzoso)
#   - FAOV (Fondo de Ahorro Obligatorio para la Vivienda)
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Departamento(ModeloBase):
    """Departamento de la empresa."""

    __tablename__ = "departamentos"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.String(200), default="")


class CargoEmpleado(ModeloBase):
    """Cargo o puesto de trabajo."""

    __tablename__ = "cargos_empleado"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.String(200), default="")


class Empleado(ModeloBase):
    """Trabajador de la empresa."""

    __tablename__ = "empleados"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    cedula = db.Column(db.String(20), nullable=False)
    nombres = db.Column(db.String(120), nullable=False)
    apellidos = db.Column(db.String(120), nullable=False)
    cargo = db.Column(db.String(120), default="")
    departamento_id = db.Column(db.Integer, db.ForeignKey("departamentos.id"), nullable=True)
    fecha_ingreso = db.Column(db.Date, nullable=True)

    sueldo_base = db.Column(db.Float, default=0.0)  # en bolivares
    bono_alimentacion = db.Column(db.Float, default=0.0)
    tipo_nomina = db.Column(db.String(20), default="mensual")  # semanal/quincenal/mensual

    # Numero de cuenta para la dispersion bancaria
    banco = db.Column(db.String(80), default="")
    numero_cuenta = db.Column(db.String(30), default="")
    afiliado_ivss = db.Column(db.Boolean, default=True)
    activo = db.Column(db.Boolean, default=True)

    departamento = db.relationship("Departamento", backref="empleados", lazy=True)


class NominaProcesada(ModeloBase):
    """Cabecera de una nomina calculada."""

    __tablename__ = "nominas_procesadas"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    periodo = db.Column(db.String(60), default="")  # ej: 2026-01 Mensual
    tipo = db.Column(db.String(20), default="mensual")
    fecha_desde = db.Column(db.Date, nullable=True)
    fecha_hasta = db.Column(db.Date, nullable=True)
    total_asignaciones = db.Column(db.Float, default=0.0)
    total_deducciones = db.Column(db.Float, default=0.0)
    total_neto = db.Column(db.Float, default=0.0)
    estado = db.Column(db.String(20), default="procesada")
    usuario = db.Column(db.String(150), default="")

    detalles = db.relationship(
        "NominaDetalle", backref="nomina", cascade="all, delete-orphan", lazy=True
    )


class NominaDetalle(ModeloBase):
    """Calculo individual de un trabajador dentro de una nomina."""

    __tablename__ = "nominas_detalle"

    id = db.Column(db.Integer, primary_key=True)
    nomina_id = db.Column(db.Integer, db.ForeignKey("nominas_procesadas.id"), nullable=False)
    empleado_id = db.Column(db.Integer, db.ForeignKey("empleados.id"), nullable=False)

    sueldo_base = db.Column(db.Float, default=0.0)
    cestaticket = db.Column(db.Float, default=0.0)
    otras_asignaciones = db.Column(db.Float, default=0.0)
    total_asignaciones = db.Column(db.Float, default=0.0)

    sso = db.Column(db.Float, default=0.0)
    rpe = db.Column(db.Float, default=0.0)
    faov = db.Column(db.Float, default=0.0)
    islr = db.Column(db.Float, default=0.0)
    otras_deducciones = db.Column(db.Float, default=0.0)
    total_deducciones = db.Column(db.Float, default=0.0)

    neto_pagar = db.Column(db.Float, default=0.0)

    empleado = db.relationship("Empleado", lazy=True)
