# ============================================================
# Servicio de tasa de cambio (dolar BCV) con plan de respaldo.
#
# Regla de oro del ERP: NUNCA depender 100% de internet.
#   1. Al arrancar (o a una hora fija) intentamos bajar la tasa
#      de una API publica y la guardamos en SQLite.
#   2. Cuando se factura NO consultamos internet: leemos la
#      tasa ya guardada en la base de datos local.
#   3. Si no hay internet, el administrador puede cargarla a
#      mano y el sistema sigue funcionando sin caerse.
# ============================================================
import logging
from datetime import date, datetime

from app.config import Configuracion
from app.extensions import db
from app.models.tasa import TasaCambio

registro = logging.getLogger("fiskor")


def _consultar_api() -> float | None:
    """Consulta las APIs de respaldo en cascada y devuelve la tasa.

    Probamos una a una; la primera que responda gana. Asi no
    dependemos de que un solo servicio este en linea.
    """
    try:
        import requests

        for url in Configuracion.TASA_API_URLS:
            try:
                respuesta = requests.get(url, timeout=Configuracion.TASA_TIMEOUT)
                respuesta.raise_for_status()
                cuerpo = respuesta.json()
                # Soportamos ambos formatos de la API (conversion_rates o rates).
                conversiones = cuerpo.get("conversion_rates") or cuerpo.get("rates") or {}
                valor = conversiones.get(Configuracion.TASA_MONEDA_DESTINO)
                if valor:
                    return float(valor)
            except Exception as exc:  # pragma: no cover - depende de la red
                registro.warning("Falló la API %s: %s", url, exc)
    except Exception as exc:  # pragma: no cover
        registro.warning("No se pudo consultar las APIs de tasa: %s", exc)
    return None


def actualizar_tasa_automatica() -> dict:
    """Intenta actualizar la tasa del dia. Devuelve el estado.

    Si la API falla, se conserva la ultima tasa conocida.
    """
    hoy = date.today()
    existente = TasaCambio.del_dia(Configuracion.TASA_MONEDA)
    # Si un usuario cargó la tasa a mano hoy, la respetamos.
    # (La tasa "sistema" es solo el relleno inicial de emergencia.)
    if existente and existente.fuente == "manual" and existente.creado_por != "sistema":
        return {"actualizada": False, "motivo": "tasa manual del dia", "valor": existente.valor}

    valor = _consultar_api()
    if valor is None:
        ultima = TasaCambio.ultima(Configuracion.TASA_MONEDA)
        return {
            "actualizada": False,
            "motivo": "sin conexion a la API, se mantiene la ultima tasa",
            "valor": ultima.valor if ultima else 0.0,
        }

    if existente:
        existente.valor = valor
        existente.fuente = "api"
        existente.creado_por = "sistema"
    else:
        existente = TasaCambio(
            fecha=hoy,
            moneda=Configuracion.TASA_MONEDA,
            moneda_destino=Configuracion.TASA_MONEDA_DESTINO,
            valor=valor,
            fuente="api",
            es_oficial=True,
            creado_por="sistema",
        )
        db.session.add(existente)
    db.session.commit()
    registro.info("Tasa %s actualizada a %s", Configuracion.TASA_MONEDA, valor)
    return {"actualizada": True, "valor": valor, "fecha": hoy.isoformat()}


def obtener_tasa_actual() -> dict:
    """Devuelve la tasa vigente sin consultar internet.

    Prioridad: tasa de hoy -> ultima conocida -> cero (por configurar).
    """
    tasa = TasaCambio.del_dia(Configuracion.TASA_MONEDA) or TasaCambio.ultima(
        Configuracion.TASA_MONEDA
    )
    if tasa is None:
        return {
            "valor": 0.0,
            "fecha": None,
            "fuente": "sin_definir",
            "es_oficial": False,
            "moneda": Configuracion.TASA_MONEDA,
        }
    return {
        "valor": tasa.valor,
        "fecha": tasa.fecha.isoformat() if tasa.fecha else None,
        "fuente": tasa.fuente,
        "es_oficial": tasa.es_oficial,
        "moneda": tasa.moneda,
        "es_de_hoy": bool(tasa.fecha == date.today()),
    }


def establecer_tasa_manual(valor: float, usuario: str = "sistema", fecha: date | None = None) -> TasaCambio:
    """Carga manual de la tasa (modo de respaldo sin internet)."""
    fecha = fecha or date.today()
    existente = (
        TasaCambio.query.filter_by(moneda=Configuracion.TASA_MONEDA, fecha=fecha)
        .order_by(TasaCambio.id.desc())
        .first()
    )
    if existente:
        existente.valor = float(valor)
        existente.fuente = "manual"
        existente.creado_por = usuario
        tasa = existente
    else:
        tasa = TasaCambio(
            fecha=fecha,
            moneda=Configuracion.TASA_MONEDA,
            moneda_destino=Configuracion.TASA_MONEDA_DESTINO,
            valor=float(valor),
            fuente="manual",
            es_oficial=True,
            creado_por=usuario,
        )
        db.session.add(tasa)
    db.session.commit()
    return tasa


def historial(limite: int = 30) -> list[dict]:
    """Ultimas tasas registradas, para la grafica del dashboard."""
    filas = (
        TasaCambio.query.filter_by(moneda=Configuracion.TASA_MONEDA)
        .order_by(TasaCambio.fecha.desc())
        .limit(limite)
        .all()
    )
    return [
        {"fecha": fila.fecha.isoformat(), "valor": fila.valor, "fuente": fila.fuente}
        for fila in filas
    ]
