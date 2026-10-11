# ============================================================
# Modelos de seguridad local.
#
# El login vive en Supabase, pero guardamos una copia local
# (cache) de los usuarios para poder entrar aunque no haya
# internet. Tambien registramos la auditoria de todas las
# operaciones realizadas por los usuarios.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class UsuarioCache(ModeloBase):
    """Copia local del usuario para permitir acceso sin internet."""

    __tablename__ = "usuarios_cache"

    id = db.Column(db.Integer, primary_key=True)
    usuario_supabase_id = db.Column(db.Integer, unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    nombre = db.Column(db.String(150), default="")
    cargo = db.Column(db.String(80), default="")
    rol = db.Column(db.String(30), default="Cajero")
    activo = db.Column(db.Boolean, default=True)
    password_hash = db.Column(db.String(255), default="")
    empresas = db.Column(db.Text, default="[]")
    sincronizado_en = db.Column(db.DateTime, default=None)


class Auditoria(ModeloBase):
    """Bitacora de operaciones (quien hizo que y cuando)."""

    __tablename__ = "auditoria"

    id = db.Column(db.Integer, primary_key=True)
    usuario_email = db.Column(db.String(150), default="")
    accion = db.Column(db.String(40), default="")  # crear/modificar/eliminar/anular
    modulo = db.Column(db.String(60), default="")
    tabla = db.Column(db.String(60), default="")
    registro_id = db.Column(db.Integer, nullable=True)
    detalle = db.Column(db.Text, default="")
    ip = db.Column(db.String(45), default="")
