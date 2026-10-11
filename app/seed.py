# ============================================================
# Datos iniciales del sistema.
# Se ejecuta cada vez que arranca la aplicacion, pero es
# idempotente: solo crea lo que falta. Nunca debe tumbar el
# servidor, por eso todo va dentro de try/except.
# ============================================================
import logging

from app.extensions import db
from app.models.empresa import Empresa, ParametroSistema
from app.models.inventario import Almacen
from app.models.nomina import CargoEmpleado, Departamento
from app.services import auth_service, bcv_service, supabase_db
from app.utils.fechas import periodo_ejercicio

registro = logging.getLogger("fiskor")


def _crear_empresa_demo() -> Empresa:
    """Crea una empresa de ejemplo si aun no hay ninguna."""
    from datetime import date

    anio = date.today().year
    inicio, cierre = periodo_ejercicio(anio)
    empresa = Empresa(
        codigo="0001",
        nombre="Fiskor Demo, C.A.",
        nombre_fiscal="Fiskor Demo, Compania Anonima",
        rif="J-12345678-9",
        direccion="Av. Bolivar, Caracas, Venezuela",
        telefono="0212-0000000",
        email="contacto@fiskor.local",
        inicio_ejercicio=inicio,
        cierre_ejercicio=cierre,
        contribuyente_especial=False,
        porcentaje_iva=16.0,
        porcentaje_igtf=3.0,
        activa=True,
    )
    db.session.add(empresa)
    db.session.commit()
    registro.info("Empresa demo creada con id %s", empresa.id)
    return empresa


def _crear_almacen(empresa_id: int) -> None:
    """Crea el almacen principal de la empresa."""
    existe = Almacen.query.filter_by(empresa_id=empresa_id).first()
    if existe:
        return
    db.session.add(
        Almacen(
            empresa_id=empresa_id,
            codigo="ALM01",
            nombre="Almacen Principal",
            direccion="Sede principal",
            activo=True,
        )
    )
    db.session.commit()


def _crear_parametros() -> None:
    """Define los parametros del sistema por defecto."""
    por_defecto = [
        ("salario_minimo", "130", "Salario minimo de referencia (Bs)"),
        ("porcentaje_iva", "16", "IVA general aplicado en las ventas (%)"),
        ("porcentaje_igtf", "3", "Recargo IGTF en pagos en divisas (%)"),
        ("cesta_ticket_diario", "0", "Monto diario de cesta ticket (Bs)"),
        ("moneda_base", "USD", "Moneda base del inventario"),
    ]
    for clave, valor, descripcion in por_defecto:
        if ParametroSistema.query.filter_by(clave=clave).first() is None:
            ParametroSistema.guardar(clave, valor, descripcion)
    db.session.commit()


def _crear_catalogos(empresa_id: int) -> None:
    """Departamentos y cargos basicos para la nomina."""
    if not Departamento.query.filter_by(empresa_id=empresa_id).first():
        db.session.add(
            Departamento(empresa_id=empresa_id, nombre="Administracion", descripcion="Area administrativa")
        )
    if not CargoEmpleado.query.filter_by(empresa_id=empresa_id).first():
        db.session.add(CargoEmpleado(empresa_id=empresa_id, nombre="Vendedor", descripcion="Atencion al cliente"))
    db.session.commit()


def _inicializar_tasa() -> None:
    """Deja una tasa disponible apenas arranca el sistema."""
    from app.models.tasa import TasaCambio

    if TasaCambio.ultima("USD") is not None:
        return
    # Intentamos bajarla de la API; si falla queda en modo manual.
    resultado = bcv_service.actualizar_tasa_automatica()
    if not resultado.get("actualizada"):
        follower = bcv_service.establecer_tasa_manual(1.0, usuario="sistema")
        follower.fuente = "manual"
        db.session.commit()
        registro.warning(
            "No se pudo obtener la tasa inicial. Carguela manualmente en el modulo de Tasas."
        )


def sembrar_datos_iniciales(app) -> None:
    """Punto de entrada del sembrado de datos."""
    # 1) Administrador (Supabase + copia local de respaldo).
    try:
        supabase_db.asegurar_esquema()
    except Exception as exc:
        registro.warning("No se pudo preparar el esquema de Supabase: %s", exc)
    try:
        auth_service.asegurar_administrador()
    except Exception as exc:
        registro.warning("No se pudo asegurar el administrador: %s", exc)

    # 2) Empresa, catalogos y parametros.
    try:
        empresa = Empresa.query.order_by(Empresa.id).first()
        if empresa is None:
            empresa = _crear_empresa_demo()
        _crear_almacen(empresa.id)
        _crear_catalogos(empresa.id)
        _crear_parametros()
    except Exception as exc:
        db.session.rollback()
        registro.warning("No se pudieron crear los datos base: %s", exc)

    # 3) Tasa de cambio inicial.
    try:
        _inicializar_tasa()
    except Exception as exc:
        db.session.rollback()
        registro.warning("No se pudo inicializar la tasa: %s", exc)
