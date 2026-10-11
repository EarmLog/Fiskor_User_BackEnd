# ============================================================
# Inventario, almacenes y movimientos de stock.
# Los costos y precios se manejan en divisas (USD) y se
# convierten a bolivares usando la tasa del dia.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Almacen(ModeloBase):
    """Deposito o almacen donde se guarda la mercancia."""

    __tablename__ = "almacenes"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    codigo = db.Column(db.String(20), default="")
    nombre = db.Column(db.String(120), nullable=False)
    direccion = db.Column(db.String(200), default="")
    activo = db.Column(db.Boolean, default=True)


class Categoria(ModeloBase):
    """Agrupacion de productos por familia."""

    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.String(200), default="")


class Producto(ModeloBase):
    """Articulo del inventario."""

    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=True)
    codigo = db.Column(db.String(40), nullable=False)
    codigo_barras = db.Column(db.String(60), default="")
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(255), default="")
    unidad_medida = db.Column(db.String(20), default="UND")

    # Los costos se expresan en divisas; el frontend calcula en Bs.
    costo_divisa = db.Column(db.Float, default=0.0)
    precio_divisa = db.Column(db.Float, default=0.0)
    iva_porcentaje = db.Column(db.Float, default=16.0)

    stock_actual = db.Column(db.Float, default=0.0)
    stock_minimo = db.Column(db.Float, default=0.0)
    activo = db.Column(db.Boolean, default=True)

    categoria = db.relationship("Categoria", backref="productos", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("empresa_id", "codigo", name="uq_producto_empresa_codigo"),
    )

    @property
    def alerta_stock(self) -> bool:
        """Aviso cuando el producto esta por debajo del minimo."""
        return self.stock_actual <= self.stock_minimo


class MovimientoInventario(ModeloBase):
    """Kardex: cada entrada o salida de mercancia."""

    __tablename__ = "movimientos_inventario"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    almacen_id = db.Column(db.Integer, db.ForeignKey("almacenes.id"), nullable=True)
    # tipo: entrada, salida, ajuste
    tipo = db.Column(db.String(20), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, default=0.0)
    stock_resultante = db.Column(db.Float, default=0.0)
    motivo = db.Column(db.String(150), default="")
    referencia = db.Column(db.String(60), default="")
    usuario = db.Column(db.String(150), default="")

    producto = db.relationship("Producto", backref="movimientos", lazy=True)
