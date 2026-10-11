# ============================================================
# Tasa de cambio del dolar (BCV) y otras monedas.
# Guardamos el historial completo: si la API externa falla, el
# sistema trabaja con la ultima tasa conocida sin caerse.
# ============================================================
from datetime import date, datetime

from app.extensions import db
from app.models.base import ModeloBase


class TasaCambio(ModeloBase):
    """Valor de una moneda para una fecha determinada."""

    __tablename__ = "tasas_cambio"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=date.today, nullable=False)
    moneda = db.Column(db.String(10), default="USD")
    moneda_destino = db.Column(db.String(10), default="VES")
    valor = db.Column(db.Float, nullable=False)
    # fuente: "api" (automatica), "manual" (cargada por el usuario)
    fuente = db.Column(db.String(20), default="api")
    es_oficial = db.Column(db.Boolean, default=True)
    creado_por = db.Column(db.String(150), default="sistema")

    @staticmethod
    def ultima(moneda: str = "USD") -> "TasaCambio | None":
        """Tasa mas reciente registrada para una moneda."""
        return (
            TasaCambio.query.filter_by(moneda=moneda)
            .order_by(TasaCambio.fecha.desc(), TasaCambio.id.desc())
            .first()
        )

    @staticmethod
    def del_dia(moneda: str = "USD") -> "TasaCambio | None":
        """Tasa registrada para la fecha de hoy (si existe)."""
        return (
            TasaCambio.query.filter_by(moneda=moneda, fecha=date.today())
            .order_by(TasaCambio.id.desc())
            .first()
        )

    def a_diccionario(self, excluir: tuple = ()) -> dict:
        datos = super().a_diccionario(excluir)
        if isinstance(self.fecha, date):
            datos["fecha"] = self.fecha.isoformat()
        return datos
