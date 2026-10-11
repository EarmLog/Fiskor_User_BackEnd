# ============================================================
# Respuestas JSON estandarizadas.
# Todos los endpoints devuelven la misma forma para que el
# frontend siempre sepa que esperar:
#   { "exito": true|false, "datos": ..., "mensaje": ... }
# ============================================================
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from flask import jsonify


def _normalizar(valor: Any) -> Any:
    """Convierte tipos que JSON no entiende (Decimal, fechas) a texto."""
    if isinstance(valor, Decimal):
        return float(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {clave: _normalizar(dato) for clave, dato in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(dato) for dato in valor]
    return valor


def exito(datos: Any = None, mensaje: str = "Operacion realizada con exito", codigo: int = 200):
    """Respuesta correcta."""
    return jsonify({"exito": True, "datos": _normalizar(datos), "mensaje": mensaje}), codigo


def error(mensaje: str = "Ocurrio un error", codigo: int = 400, detalles: Any = None):
    """Respuesta con fallo controlado."""
    cuerpo = {"exito": False, "datos": None, "mensaje": mensaje}
    if detalles is not None:
        cuerpo["detalles"] = _normalizar(detalles)
    return jsonify(cuerpo), codigo


def redondear(valor: float, decimales: int = 2) -> float:
    """Redondea a la cantidad de decimales indicada (comun en montos)."""
    cuantia = Decimal(str(valor)).quantize(
        Decimal("1." + "0" * decimales), rounding=ROUND_HALF_UP
    )
    return float(cuantia)
