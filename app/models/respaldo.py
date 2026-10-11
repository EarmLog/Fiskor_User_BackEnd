# ============================================================
# Respaldos de la base de datos local.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Respaldo(ModeloBase):
    """Registro de cada respaldo generado."""

    __tablename__ = "respaldos"

    id = db.Column(db.Integer, primary_key=True)
    nombre_archivo = db.Column(db.String(180), default="")
    ruta = db.Column(db.String(255), default="")
    tipo = db.Column(db.String(20), default="completo")  # completo/datos
    tamano_bytes = db.Column(db.Integer, default=0)
    generado_por = db.Column(db.String(150), default="")
    nota = db.Column(db.String(200), default="")
