# ============================================================
# Servicio de empresas por usuario.
#
# Cada usuario tiene su propio negocio (empresa). Asi la informacion
# de inventario, ventas, clientes, etc. queda separada por usuario:
# al filtrar todo por empresa_id, cada quien ve solo lo suyo.
# ============================================================
import logging
import re
from datetime import date

from app.extensions import db
from app.models.empresa import Empresa
from app.models.inventario import Almacen
from app.models.nomina import CargoEmpleado, Departamento
from app.utils.fechas import periodo_ejercicio

registro = logging.getLogger("fiskor")


def empresa_del_usuario(email: str) -> Empresa | None:
    """Devuelve la empresa cuyo dueño es el correo indicado."""
    correo = (email or "").strip().lower()
    if not correo:
        return None
    return (
        Empresa.query.filter(db.func.lower(Empresa.propietario_email) == correo)
        .order_by(Empresa.id)
        .first()
    )


def _codigo_unico(email: str) -> str:
    """Genera un codigo corto y unico para la empresa del usuario."""
    base = re.sub(r"[^a-z0-9]", "", (email or "").lower())[:8] or "user"
    codigo = f"U{base}"
    contador = 1
    while Empresa.query.filter_by(codigo=codigo).first():
        contador += 1
        codigo = f"U{base}{contador}"
    return codigo[:10]


def _crear_bases(empresa: Empresa) -> None:
    """Crea el almacen principal y los catalogos base del negocio."""
    db.session.add(
        Almacen(
            empresa_id=empresa.id,
            codigo="ALM01",
            nombre="Almacen Principal",
            direccion="Sede principal",
            activo=True,
        )
    )
    db.session.add(Departamento(empresa_id=empresa.id, nombre="Administracion"))
    db.session.add(CargoEmpleado(empresa_id=empresa.id, nombre="Vendedor"))
    db.session.commit()


def crear_empresa_personal(email: str, nombre: str = "") -> Empresa:
    """Crea el negocio propio de un usuario nuevo (vacio, sin datos demo)."""
    correo = (email or "").strip().lower()
    anio = date.today().year
    inicio, cierre = periodo_ejercicio(anio)

    nombre_negocio = (nombre or "").strip() or f"Negocio de {correo.split('@')[0]}"
    empresa = Empresa(
        codigo=_codigo_unico(correo),
        propietario_email=correo,
        nombre=nombre_negocio,
        nombre_fiscal=nombre_negocio,
        inicio_ejercicio=inicio,
        cierre_ejercicio=cierre,
        porcentaje_iva=16.0,
        porcentaje_igtf=3.0,
        activa=True,
    )
    db.session.add(empresa)
    db.session.commit()
    _crear_bases(empresa)
    registro.info("Empresa personal creada para %s (id %s)", correo, empresa.id)
    return empresa


def asegurar_empresa_usuario(email: str, nombre: str = "") -> Empresa:
    """Devuelve la empresa del usuario, creandola si aun no existe."""
    empresa = empresa_del_usuario(email)
    if empresa is None:
        empresa = crear_empresa_personal(email, nombre)
    return empresa
