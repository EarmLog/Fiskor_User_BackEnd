# ============================================================
# API de nomina y recursos humanos (LOTTT).
# ============================================================
from flask import Blueprint, request

from app.extensions import db
from app.models.nomina import (
    CargoEmpleado,
    Departamento,
    Empleado,
    NominaDetalle,
    NominaProcesada,
)
from app.services import nomina_service
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id, parametros_paginacion
from app.utils.fechas import a_fecha
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual
from app.utils.validaciones import limpiar_texto, validar_cedula

nomina_bp = Blueprint("nomina", __name__, url_prefix="/api/nomina")


# ------------------------------------------------------------
# Catalogos
# ------------------------------------------------------------
@nomina_bp.route("/departamentos", methods=["GET"])
@requiere_sesion
def listar_departamentos():
    empresa_id = empresa_activa_id()
    registros = Departamento.query.filter_by(empresa_id=empresa_id).order_by(Departamento.nombre).all()
    return exito([d.a_diccionario() for d in registros], "Departamentos")


@nomina_bp.route("/departamentos", methods=["POST"])
@requiere_sesion
def crear_departamento():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 120)
    if not nombre:
        return error("El nombre del departamento es obligatorio", 400)
    registro = Departamento(empresa_id=empresa_activa_id(), nombre=nombre,
                            descripcion=limpiar_texto(datos.get("descripcion"), 200))
    db.session.add(registro)
    db.session.commit()
    return exito(registro.a_diccionario(), "Departamento creado", 201)


@nomina_bp.route("/cargos", methods=["GET"])
@requiere_sesion
def listar_cargos():
    empresa_id = empresa_activa_id()
    registros = CargoEmpleado.query.filter_by(empresa_id=empresa_id).order_by(CargoEmpleado.nombre).all()
    return exito([c.a_diccionario() for c in registros], "Cargos")


@nomina_bp.route("/cargos", methods=["POST"])
@requiere_sesion
def crear_cargo():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 120)
    if not nombre:
        return error("El nombre del cargo es obligatorio", 400)
    registro = CargoEmpleado(empresa_id=empresa_activa_id(), nombre=nombre,
                             descripcion=limpiar_texto(datos.get("descripcion"), 200))
    db.session.add(registro)
    db.session.commit()
    return exito(registro.a_diccionario(), "Cargo creado", 201)


# ------------------------------------------------------------
# Empleados
# ------------------------------------------------------------
@nomina_bp.route("/empleados", methods=["GET"])
@requiere_sesion
def listar_empleados():
    empresa_id = empresa_activa_id()
    pagina, por_pagina = parametros_paginacion()
    busqueda = (request.args.get("buscar") or "").strip()
    consulta = Empleado.query.filter_by(empresa_id=empresa_id, activo=True)
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(
            db.or_(
                Empleado.nombres.ilike(patron),
                Empleado.apellidos.ilike(patron),
                Empleado.cedula.ilike(patron),
            )
        )
    total = consulta.count()
    empleados = consulta.order_by(Empleado.apellidos).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    return exito({"items": [e.a_diccionario() for e in empleados], "total": total}, "Empleados")


@nomina_bp.route("/empleados", methods=["POST"])
@requiere_sesion
def crear_empleado():
    datos = request.get_json(silent=True) or {}
    valido, mensaje = validar_cedula(datos.get("cedula"))
    if not valido:
        return error(mensaje, 400)
    if not datos.get("nombres") or not datos.get("apellidos"):
        return error("Los nombres y apellidos son obligatorios", 400)

    empleado = Empleado(
        empresa_id=empresa_activa_id(),
        cedula=limpiar_texto(datos.get("cedula"), 20),
        nombres=limpiar_texto(datos.get("nombres"), 120),
        apellidos=limpiar_texto(datos.get("apellidos"), 120),
        cargo=limpiar_texto(datos.get("cargo"), 120),
        departamento_id=datos.get("departamento_id") or None,
        fecha_ingreso=a_fecha(datos.get("fecha_ingreso")),
        sueldo_base=float(datos.get("sueldo_base") or 0),
        bono_alimentacion=float(datos.get("bono_alimentacion") or 0),
        tipo_nomina=(datos.get("tipo_nomina") or "mensual").lower(),
        banco=limpiar_texto(datos.get("banco"), 80),
        numero_cuenta=limpiar_texto(datos.get("numero_cuenta"), 30),
        afiliado_ivss=bool(datos.get("afiliado_ivss", True)),
        activo=True,
    )
    db.session.add(empleado)
    db.session.commit()
    registrar("crear", "nomina", "empleados", empleado.id,
              f"{empleado.nombres} {empleado.apellidos}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(empleado.a_diccionario(), "Empleado registrado", 201)


@nomina_bp.route("/empleados/<int:empleado_id>", methods=["PUT"])
@requiere_sesion
def actualizar_empleado(empleado_id: int):
    empleado = Empleado.query.get(empleado_id)
    if empleado is None:
        return error("Empleado no encontrado", 404)
    datos = request.get_json(silent=True) or {}
    for campo in ("nombres", "apellidos", "cargo", "banco", "numero_cuenta"):
        if campo in datos:
            setattr(empleado, campo, limpiar_texto(datos[campo], 120))
    for campo in ("sueldo_base", "bono_alimentacion"):
        if campo in datos and datos[campo] is not None:
            setattr(empleado, campo, float(datos[campo]))
    if "departamento_id" in datos:
        empleado.departamento_id = datos["departamento_id"] or None
    if "fecha_ingreso" in datos:
        empleado.fecha_ingreso = a_fecha(datos["fecha_ingreso"])
    if "tipo_nomina" in datos:
        empleado.tipo_nomina = (datos["tipo_nomina"] or "mensual").lower()
    if "afiliado_ivss" in datos:
        empleado.afiliado_ivss = bool(datos["afiliado_ivss"])
    if "activo" in datos:
        empleado.activo = bool(datos["activo"])
    db.session.commit()
    registrar("modificar", "nomina", "empleados", empleado.id, "Actualizacion de empleado",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(empleado.a_diccionario(), "Empleado actualizado")


# ------------------------------------------------------------
# Proceso de nomina
# ------------------------------------------------------------
def _calcular_detalle(empleado: Empleado) -> dict:
    """Calcula el renglon de nomina de un empleado."""
    return nomina_service.calcular_renglon(
        sueldo_base_mensual=empleado.sueldo_base,
        tipo_nomina=empleado.tipo_nomina,
        cestaticket=empleado.bono_alimentacion,
        afiliado_ivss=empleado.afiliado_ivss,
    )


@nomina_bp.route("/previsualizar", methods=["POST"])
@requiere_sesion
def previsualizar():
    """Calcula la nomina sin guardarla (vista previa)."""
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "mensual").lower()
    empleados = Empleado.query.filter_by(empresa_id=empresa_activa_id(), activo=True).all()
    if tipo != "todas":
        empleados = [e for e in empleados if e.tipo_nomina == tipo]

    detalles = []
    total_asignaciones = total_deducciones = total_neto = 0.0
    for empleado in empleados:
        calculo = _calcular_detalle(empleado)
        total_asignaciones += calculo["total_asignaciones"]
        total_deducciones += calculo["total_deducciones"]
        total_neto += calculo["neto_pagar"]
        detalles.append(
            {
                "empleado_id": empleado.id,
                "cedula": empleado.cedula,
                "empleado": f"{empleado.nombres} {empleado.apellidos}",
                **calculo,
            }
        )
    return exito(
        {
            "detalles": detalles,
            "total_asignaciones": round(total_asignaciones, 2),
            "total_deducciones": round(total_deducciones, 2),
            "total_neto": round(total_neto, 2),
        },
        "Previsualizacion de nomina",
    )


@nomina_bp.route("/procesar", methods=["POST"])
@requiere_sesion
def procesar():
    """Procesa y guarda la nomina del periodo indicado."""
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "mensual").lower()
    periodo = limpiar_texto(datos.get("periodo"), 60)
    if not periodo:
        return error("Debe indicar el periodo de la nomina", 400)

    empleados = Empleado.query.filter_by(empresa_id=empresa_activa_id(), activo=True).all()
    if tipo != "todas":
        empleados = [e for e in empleados if e.tipo_nomina == tipo]
    if not empleados:
        return error("No hay empleados activos para ese tipo de nomina", 400)

    try:
        nomina = NominaProcesada(
            empresa_id=empresa_activa_id(),
            periodo=periodo,
            tipo=tipo,
            fecha_desde=a_fecha(datos.get("fecha_desde")),
            fecha_hasta=a_fecha(datos.get("fecha_hasta")),
            usuario=usuario_actual()["email"],
        )
        db.session.add(nomina)
        db.session.flush()

        total_asignaciones = total_deducciones = total_neto = 0.0
        for empleado in empleados:
            calculo = _calcular_detalle(empleado)
            total_asignaciones += calculo["total_asignaciones"]
            total_deducciones += calculo["total_deducciones"]
            total_neto += calculo["neto_pagar"]
            db.session.add(
                NominaDetalle(
                    nomina_id=nomina.id,
                    empleado_id=empleado.id,
                    **{k: v for k, v in calculo.items()},
                )
            )
        nomina.total_asignaciones = round(total_asignaciones, 2)
        nomina.total_deducciones = round(total_deducciones, 2)
        nomina.total_neto = round(total_neto, 2)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error("No se pudo procesar la nomina", 500)

    registrar("crear", "nomina", "nominas_procesadas", nomina.id,
              f"Nomina {periodo} ({tipo})",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(nomina.a_diccionario(), "Nomina procesada", 201)


@nomina_bp.route("", methods=["GET"])
@requiere_sesion
def listar_nominas():
    empresa_id = empresa_activa_id()
    nominas = NominaProcesada.query.filter_by(empresa_id=empresa_id).order_by(NominaProcesada.id.desc()).all()
    return exito([n.a_diccionario() for n in nominas], "Nominas procesadas")


@nomina_bp.route("/<int:nomina_id>", methods=["GET"])
@requiere_sesion
def obtener_nomina(nomina_id: int):
    nomina = NominaProcesada.query.get(nomina_id)
    if nomina is None:
        return error("Nomina no encontrada", 404)
    datos = nomina.a_diccionario()
    datos["detalles"] = [
        {
            **detalle.a_diccionario(),
            "empleado": f"{detalle.empleado.nombres} {detalle.empleado.apellidos}" if detalle.empleado else "",
            "cedula": detalle.empleado.cedula if detalle.empleado else "",
        }
        for detalle in nomina.detalles
    ]
    return exito(datos, "Nomina")


@nomina_bp.route("/<int:nomina_id>/txt", methods=["GET"])
@requiere_sesion
def txt_dispersion(nomina_id: int):
    """Genera el TXT de dispersion bancaria de una nomina."""
    import os

    nomina = NominaProcesada.query.get(nomina_id)
    if nomina is None:
        return error("Nomina no encontrada", 404)

    detalles = [
        {
            "neto_pagar": detalle.neto_pagar,
            "empleado": {
                "numero_cuenta": detalle.empleado.numero_cuenta if detalle.empleado else "",
                "cedula": detalle.empleado.cedula if detalle.empleado else "",
                "nombres": detalle.empleado.nombres if detalle.empleado else "",
                "apellidos": detalle.empleado.apellidos if detalle.empleado else "",
            },
        }
        for detalle in nomina.detalles
    ]
    contenido = nomina_service.generar_txt_dispersion(detalles)

    from app.config import Configuracion

    carpeta = Configuracion.RUTA_EXPORTADOS / "nomina"
    os.makedirs(carpeta, exist_ok=True)
    ruta = carpeta / f"dispersion_{nomina.id}.txt"
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)
    return exito({"archivo": str(ruta), "contenido": contenido}, "TXT de dispersion generado")
