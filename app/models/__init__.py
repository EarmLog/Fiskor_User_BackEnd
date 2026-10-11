# ============================================================
# Paquete de modelos de Fiskor ERP.
# Se importan todos aqui para que SQLAlchemy los descubra al
# crear las tablas con db.create_all().
# ============================================================
from app.models.base import ModeloBase
from app.models.empresa import Empresa, ParametroSistema
from app.models.seguridad import Auditoria, UsuarioCache
from app.models.tasa import TasaCambio
from app.models.inventario import Almacen, Categoria, MovimientoInventario, Producto
from app.models.terceros import Cliente, Proveedor
from app.models.compras import AbonoCxP, Compra, CompraDetalle, CuentaPorPagar
from app.models.ventas import (
    AbonoCxC,
    CuentaPorCobrar,
    PagoVenta,
    Venta,
    VentaDetalle,
)
from app.models.tesoreria import CuentaBancaria, MovimientoCaja, SesionCaja
from app.models.nomina import (
    CargoEmpleado,
    Departamento,
    Empleado,
    NominaDetalle,
    NominaProcesada,
)
from app.models.fiscal import Retencion
from app.models.respaldo import Respaldo

__all__ = [
    "ModeloBase",
    "Empresa",
    "ParametroSistema",
    "UsuarioCache",
    "Auditoria",
    "TasaCambio",
    "Almacen",
    "Categoria",
    "Producto",
    "MovimientoInventario",
    "Cliente",
    "Proveedor",
    "Compra",
    "CompraDetalle",
    "CuentaPorPagar",
    "AbonoCxP",
    "Venta",
    "VentaDetalle",
    "PagoVenta",
    "CuentaPorCobrar",
    "AbonoCxC",
    "CuentaBancaria",
    "SesionCaja",
    "MovimientoCaja",
    "Departamento",
    "CargoEmpleado",
    "Empleado",
    "NominaProcesada",
    "NominaDetalle",
    "Retencion",
    "Respaldo",
]
