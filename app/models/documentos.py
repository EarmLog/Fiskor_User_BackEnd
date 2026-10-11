# ============================================================
# Plantillas de documentos (formatos).
#
# El usuario puede "montar" un formato por tipo de documento
# (factura, nota de entrega, recibo, comprobante de retencion) y
# decidir que se imprime: logo, sello, firma, IVA, IGTF, etc.
# El logo y el sello se suben y reemplazan por separado (ver
# empresa.py), aqui solo se controla como se usan.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class PlantillaDocumento(ModeloBase):
    """Formato imprimible configurable para cada tipo de documento."""

    __tablename__ = "plantillas_documento"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)

    # tipo: factura / nota_entrega / recibo / retencion / cotizacion
    tipo = db.Column(db.String(30), default="factura")
    nombre = db.Column(db.String(120), default="Formato estandar")

    # Textos editables del formato.
    titulo_encabezado = db.Column(db.String(150), default="")
    leyenda_superior = db.Column(db.Text, default="")
    leyenda_inferior = db.Column(db.Text, default="")

    # Interruptores de contenido.
    mostrar_logo = db.Column(db.Boolean, default=True)
    mostrar_sello = db.Column(db.Boolean, default=True)
    mostrar_firma = db.Column(db.Boolean, default=True)
    mostrar_iva = db.Column(db.Boolean, default=True)
    mostrar_igtf = db.Column(db.Boolean, default=True)
    mostrar_datos_bancarios = db.Column(db.Boolean, default=False)
    datos_bancarios = db.Column(db.Text, default="")

    # Color de acento del documento en formato #RRGGBB.
    color = db.Column(db.String(10), default="#1d4ed8")

    activo = db.Column(db.Boolean, default=True)

    @staticmethod
    def obtener_para(empresa_id: int, tipo: str) -> "PlantillaDocumento | None":
        """Devuelve la plantilla activa de un tipo (o None si no hay)."""
        return (
            PlantillaDocumento.query.filter_by(
                empresa_id=empresa_id, tipo=tipo, activo=True
            )
            .order_by(PlantillaDocumento.id.desc())
            .first()
        )
