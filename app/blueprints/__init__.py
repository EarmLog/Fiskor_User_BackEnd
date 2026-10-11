# ============================================================
# Registro de blueprints (modulos de la API).
# ============================================================
from app.blueprints.auth import auth_bp
from app.blueprints.clientes import clientes_bp
from app.blueprints.compras import compras_bp
from app.blueprints.descargas import descargas_bp
from app.blueprints.documentos import documentos_bp
from app.blueprints.empresa import empresa_bp
from app.blueprints.fiscal import fiscal_bp
from app.blueprints.inventario import inventario_bp
from app.blueprints.nomina import nomina_bp
from app.blueprints.proveedores import proveedores_bp
from app.blueprints.reportes import reportes_bp
from app.blueprints.tasas import tasas_bp
from app.blueprints.tesoreria import tesoreria_bp
from app.blueprints.usuarios import usuarios_bp
from app.blueprints.ventas import ventas_bp
from app.blueprints.auditoria import auditoria_bp
from app.blueprints.excel import excel_bp


def registrar_blueprints(app) -> None:
    """Engancha todos los blueprints a la aplicacion."""
    blueprints = [
        auth_bp,
        usuarios_bp,
        empresa_bp,
        tasas_bp,
        inventario_bp,
        clientes_bp,
        proveedores_bp,
        compras_bp,
        ventas_bp,
        tesoreria_bp,
        nomina_bp,
        fiscal_bp,
        documentos_bp,
        reportes_bp,
        descargas_bp,
        auditoria_bp,
        excel_bp,
    ]
    for blue_print in blueprints:
        app.register_blueprint(blue_print)