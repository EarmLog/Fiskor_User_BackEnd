# ============================================================
# Modelo base compartido.
# Aporta la serializacion a diccionario y campos de auditoria.
# ============================================================
from datetime import datetime

from app.extensions import db


class ModeloBase(db.Model):
    """Clase padre abstracta para todos los modelos del ERP."""

    __abstract__ = True

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def a_diccionario(self, excluir: tuple = ()) -> dict:
        """Convierte el registro en diccionario, listo para JSON."""
        datos = {}
        for columna in self.__table__.columns:
            if columna.name in excluir:
                continue
            valor = getattr(self, columna.name)
            if isinstance(valor, datetime):
                valor = valor.isoformat()
            datos[columna.name] = valor
        return datos
