# ============================================================
# Utilidades de fechas y periodos contables.
# En Venezuela el ejercicio economico suele ir del 01/01 al 31/12.
# ============================================================
from datetime import date, datetime

FORMATO_FECHA = "%Y-%m-%d"


def hoy() -> date:
    """Fecha actual del servidor."""
    return date.today()


def a_fecha(valor) -> date | None:
    """Convierte texto o fecha a un objeto date. Devuelve None si falla."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in (FORMATO_FECHA, "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            continue
    return None


def periodo_ejercicio(anio: int) -> tuple[date, date]:
    """Devuelve el inicio y cierre de un ejercicio contable por anio."""
    return date(anio, 1, 1), date(anio, 12, 31)


def primer_dia_mes(anio: int | None = None, mes: int | None = None) -> date:
    """Primer dia del mes indicado (o del mes actual)."""
    referencia = hoy()
    return date(anio or referencia.year, mes or referencia.month, 1)


def generar_calendario_fiscal(anio: int) -> list[dict]:
    """Genera el calendario fiscal de Venezuela para un anio.

    Los contribuyentes especiales declaran y pagan el IVA de forma
    quincenal (dias 15 y ultimo dia del mes). A modo informativo,
    construimos las quincenas con sus fechas limite.
    """
    calendario = []
    for mes in range(1, 13):
        calendario.append(
            {
                "mes": mes,
                "periodo": f"1ra quincena {mes:02d}/{anio}",
                "desde": date(anio, mes, 1).isoformat(),
                "hasta": date(anio, mes, 15).isoformat(),
                "vence": date(anio, mes, 15).isoformat(),
            }
        )
        ultimo_dia = date(anio, mes + 1, 1).toordinal() - 1 if mes < 12 else date(anio, 12, 31).toordinal()
        cierre = date.fromordinal(ultimo_dia)
        calendario.append(
            {
                "mes": mes,
                "periodo": f"2da quincena {mes:02d}/{anio}",
                "desde": date(anio, mes, 16).isoformat(),
                "hasta": cierre.isoformat(),
                "vence": cierre.isoformat(),
            }
        )
    return calendario
