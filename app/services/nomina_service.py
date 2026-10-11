# ============================================================
# Calculo de nomina adaptado a la LOTTT (Venezuela).
#
# Deducciones de ley del trabajador:
#   - SSO: 4% sobre el sueldo, con tope de 5 salarios minimos.
#   - RPE (paro forzoso): 0.5% con tope de 10 salarios minimos.
#   - FAOV: 1% sobre el sueldo (el patrono aporta 2% adicional).
# ============================================================
from app.models.empresa import ParametroSistema
from app.utils.respuestas import redondear

# Porcentajes de ley del trabajador.
PCT_SSO = 4.0
PCT_RPE = 0.5
PCT_FAOV = 1.0
# Topes en salarios minimos.
TOPE_SSO_SALARIOS = 5
TOPE_RPE_SALARIOS = 10

# Salario minimo de referencia por defecto (configurable por el usuario).
SALARIO_MINIMO_POR_DEFECTO = 130.0

# Divisor segun la frecuencia de pago.
DIVISOR_PERIODO = {"semanal": 4.0, "quincenal": 2.0, "mensual": 1.0}


def salario_minimo() -> float:
    """Lee el salario minimo de referencia desde los parametros."""
    valor = ParametroSistema.obtener("salario_minimo", str(SALARIO_MINIMO_POR_DEFECTO))
    try:
        return float(valor)
    except (TypeError, ValueError):
        return SALARIO_MINIMO_POR_DEFECTO


def calcular_deducciones(sueldo_periodo: float, afiliado_ivss: bool = True) -> dict:
    """Calcula SSO, RPE y FAOV del trabajador para un periodo."""
    minimo = salario_minimo()
    sueldo_periodo = float(sueldo_periodo or 0)

    if afiliado_ivss:
        base_sso = min(sueldo_periodo, TOPE_SSO_SALARIOS * minimo)
        sso = redondear(base_sso * PCT_SSO / 100.0)
        base_rpe = min(sueldo_periodo, TOPE_RPE_SALARIOS * minimo)
        rpe = redondear(base_rpe * PCT_RPE / 100.0)
    else:
        sso = 0.0
        rpe = 0.0

    faov = redondear(sueldo_periodo * PCT_FAOV / 100.0)
    total = redondear(sso + rpe + faov)
    return {"sso": sso, "rpe": rpe, "faov": faov, "total_deducciones_ley": total}


def calcular_renglon(
    sueldo_base_mensual: float,
    tipo_nomina: str,
    cestaticket: float = 0.0,
    otras_asignaciones: float = 0.0,
    otras_deducciones: float = 0.0,
    islr: float = 0.0,
    afiliado_ivss: bool = True,
) -> dict:
    """Calcula la nomina completa de un trabajador en un periodo."""
    divisor = DIVISOR_PERIODO.get(tipo_nomina, 1.0)
    sueldo_periodo = redondear(float(sueldo_base_mensual or 0) / divisor)
    cestaticket_periodo = redondear(float(cestaticket or 0))

    asignaciones = redondear(sueldo_periodo + cestaticket_periodo + float(otras_asignaciones or 0))
    deducciones = calcular_deducciones(sueldo_periodo + cestaticket_periodo, afiliado_ivss)
    total_deducciones = redondear(
        deducciones["total_deducciones_ley"] + float(islr or 0) + float(otras_deducciones or 0)
    )
    neto = redondear(asignaciones - total_deducciones)

    return {
        "sueldo_base": sueldo_periodo,
        "cestaticket": cestaticket_periodo,
        "otras_asignaciones": redondear(float(otras_asignaciones or 0)),
        "total_asignaciones": asignaciones,
        "sso": deducciones["sso"],
        "rpe": deducciones["rpe"],
        "faov": deducciones["faov"],
        "islr": redondear(float(islr or 0)),
        "otras_deducciones": redondear(float(otras_deducciones or 0)),
        "total_deducciones": total_deducciones,
        "neto_pagar": neto,
    }


def generar_txt_dispersion(detalles: list[dict], banco: str = "") -> str:
    """Genera el TXT de dispersion bancaria (nomina).

    Formato simple y compatible con la mayoria de los bancos
    venezolanos: cuenta;cedula;nombre;monto por linea.
    """
    lineas = []
    for detalle in detalles:
        empleado = detalle.get("empleado", {})
        numero_cuenta = str(empleado.get("numero_cuenta", "")).strip()
        cedula = str(empleado.get("cedula", "")).strip()
        nombre = f"{empleado.get('nombres', '')} {empleado.get('apellidos', '')}".strip()
        monto = f"{detalle.get('neto_pagar', 0):.2f}"
        lineas.append(";".join([numero_cuenta, cedula, nombre[:40], monto]))
    return "\n".join(lineas)
