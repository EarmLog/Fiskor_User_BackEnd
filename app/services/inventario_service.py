# ============================================================
# Operaciones de stock atomicas.
#
# Para evitar el "stock en negativo" cuando dos cajeros venden
# el ultimo articulo al mismo tiempo, NO leemos y luego
# escribimos: hacemos un UPDATE condicionado.
#
#   UPDATE productos SET stock = stock - N WHERE id = X AND stock >= N
#
# Si la base de datos no actualizo ninguna fila, es porque ya no
# habia existencia. Asi el descuento es seguro aunque haya
# concurrencia.
# ============================================================
from sqlalchemy import update

from app.extensions import db
from app.models.inventario import MovimientoInventario, Producto


class StockInsuficiente(Exception):
    """Se lanza cuando no hay existencia suficiente."""

    def __init__(self, producto: str, disponible: float):
        self.producto = producto
        self.disponible = disponible
        super().__init__(f"Stock insuficiente para {producto} (disponible {disponible:.2f})")


def descontar_stock(producto_id: int, cantidad: float, motivo: str, referencia: str, usuario: str) -> None:
    """Descuenta stock de forma atomica. Lanza StockInsuficiente si falta."""
    if cantidad <= 0:
        return
    resultado = db.session.execute(
        update(Producto)
        .where(Producto.id == producto_id, Producto.stock_actual >= cantidad)
        .values(stock_actual=Producto.stock_actual - cantidad)
    )
    if resultado.rowcount == 0:
        producto = Producto.query.get(producto_id)
        nombre = producto.nombre if producto else f"ID {producto_id}"
        disponible = producto.stock_actual if producto else 0.0
        raise StockInsuficiente(nombre, disponible)

    producto = Producto.query.get(producto_id)
    db.session.add(
        MovimientoInventario(
            empresa_id=producto.empresa_id,
            producto_id=producto_id,
            tipo="salida",
            cantidad=cantidad,
            costo_unitario=producto.costo_divisa,
            stock_resultante=producto.stock_actual,
            motivo=motivo,
            referencia=referencia,
            usuario=usuario,
        )
    )


def aumentar_stock(producto_id: int, cantidad: float, costo: float, motivo: str, referencia: str, usuario: str) -> None:
    """Suma stock y deja el movimiento de entrada."""
    if cantidad <= 0:
        return
    db.session.execute(
        update(Producto)
        .where(Producto.id == producto_id)
        .values(stock_actual=Producto.stock_actual + cantidad)
    )
    producto = Producto.query.get(producto_id)
    db.session.add(
        MovimientoInventario(
            empresa_id=producto.empresa_id,
            producto_id=producto_id,
            tipo="entrada",
            cantidad=cantidad,
            costo_unitario=costo or producto.costo_divisa,
            stock_resultante=producto.stock_actual,
            motivo=motivo,
            referencia=referencia,
            usuario=usuario,
        )
    )
