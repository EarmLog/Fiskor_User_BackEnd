# ============================================================
# Capa de conexion fiscal (SENIAT).
#
# Envuelve la comunicacion con impresoras fiscales venezolanas por
# puerto serie/USB. El ERP NO se cae si no hay impresora: hay un
# modo SIMULACION que genera la trama y la registra, para poder
# probar todo el flujo sin hardware.
#
# Protocolo inicial: HKA (The Factory HKA y compatibles 2.2.3+).
#   Los comandos exactos varian entre modelos, por eso estan
#   centralizados en COMANDOS y en formatear_venta() para que se
#   puedan ajustar a la impresora real sin tocar el resto del ERP.
#
# Formato de trama usado (ASCII, ajustable):
#   STX(0x02) + CODIGO + "|" + DATOS + ETX(0x03) + CHECKSUM
#   El checksum es la suma de los bytes previos modulo 256.
# ============================================================
import logging
from datetime import datetime

from app.config import Configuracion
from app.extensions import db
from app.models.fiscal import LogImpresionFiscal

registro = logging.getLogger("fiskor")

STX = b"\x02"
ETX = b"\x03"

# Tabla de comandos por protocolo. Se puede ampliar segun el modelo.
COMANDOS = {
    "HKA": {
        "abrir_documento": "S1",
        "cerrar_documento": "S2",
        "anular_documento": "S3",
        "encabezado": "H1",
        "cliente": "C1",
        "item": "I1",
        "subtotal": "T1",
        "total": "T2",
        "iva": "T3",
        "igtf": "T4",
        "pago": "P1",
        "abrir_cajon": "K1",
        "reporte_x": "R1",
        "reporte_z": "R2",
        "estado": "E1",
    },
    "GENERICO": {
        "abrir_documento": "ABRIR",
        "cerrar_documento": "CERRAR",
        "anular_documento": "ANULAR",
        "encabezado": "ENC",
        "cliente": "CLI",
        "item": "ITEM",
        "subtotal": "SUBTOTAL",
        "total": "TOTAL",
        "iva": "IVA",
        "igtf": "IGTF",
        "pago": "PAGO",
        "abrir_cajon": "CAJON",
        "reporte_x": "REPX",
        "reporte_z": "REPZ",
        "estado": "STATUS",
    },
}


def _comandos() -> dict:
    """Devuelve la tabla de comandos del protocolo configurado."""
    protocolo = Configuracion.IMPRESORA_PROTOCOLO
    return COMANDOS.get(protocolo, COMANDOS["GENERICO"])


def _checksum(paquete: bytes) -> bytes:
    """Suma de verificacion simple (modulo 256), comun en estos equipos."""
    return bytes([sum(paquete) % 256])


def construir_trama(codigo: str, datos: str = "") -> bytes:
    """Arma una trama completa STX + codigo|datos + ETX + checksum."""
    interior = f"{codigo}|{datos}".encode("latin-1", errors="replace")
    return STX + interior + ETX + _checksum(interior)


def _fmt(valor, decimales: int = 2) -> str:
    try:
        return f"{float(valor):.{decimales}f}"
    except (TypeError, ValueError):
        return "0.00"


# ------------------------------------------------------------
# Formateo de la venta a tramas
# ------------------------------------------------------------
def formatear_venta(empresa: dict, venta: dict, detalles: list[dict]) -> list[bytes]:
    """Convierte una venta en la secuencia de tramas para la impresora.

    Devuelve una lista de tramas (bytes) listas para enviar por serie.
    """
    cmd = _comandos()
    tramas: list[bytes] = []

    tramas.append(construir_trama(cmd["abrir_documento"], empresa.get("rif", "")))
    tramas.append(
        construir_trama(
            cmd["encabezado"],
            "|".join(
                [
                    empresa.get("nombre_fiscal") or empresa.get("nombre", ""),
                    empresa.get("rif", ""),
                    empresa.get("direccion", ""),
                    empresa.get("telefono", ""),
                ]
            ),
        )
    )
    tramas.append(
        construir_trama(
            cmd["cliente"],
            "|".join(
                [
                    venta.get("cliente_rif") or "V-00000000",
                    venta.get("cliente_nombre") or "Consumidor final",
                ]
            ),
        )
    )

    for detalle in detalles:
        tramas.append(
            construir_trama(
                cmd["item"],
                "|".join(
                    [
                        str(detalle.get("descripcion") or "")[:40],
                        _fmt(detalle.get("cantidad")),
                        _fmt(detalle.get("precio_unitario")),
                        _fmt(detalle.get("iva_porcentaje"), 0),
                        _fmt(detalle.get("total")),
                    ]
                ),
            )
        )

    # Totales en bolivares (la impresora fiscal trabaja en moneda local).
    tasa = float(venta.get("tasa_aplicada") or 0)
    tramas.append(construir_trama(cmd["subtotal"], _fmt(venta.get("subtotal", 0) * tasa)))
    tramas.append(construir_trama(cmd["iva"], _fmt(venta.get("iva", 0) * tasa)))
    if float(venta.get("igtf") or 0) > 0:
        tramas.append(construir_trama(cmd["igtf"], _fmt(venta.get("igtf"))))
    tramas.append(construir_trama(cmd["total"], _fmt(venta.get("total_bolivares", 0))))

    for pago in venta.get("pagos", []) or []:
        tramas.append(
            construir_trama(
                cmd["pago"],
                "|".join([str(pago.get("metodo") or ""), _fmt(pago.get("monto"))]),
            )
        )

    tramas.append(construir_trama(cmd["cerrar_documento"], ""))
    return tramas


# ------------------------------------------------------------
# Comunicacion con el puerto serie
# ------------------------------------------------------------
def _abrir_puerto():
    """Abre el puerto serie de la impresora fiscal.

    Importamos pyserial de forma diferida: si no esta instalado, el
    ERP sigue funcionando en modo simulacion.
    """
    import serial  # noqa: F401  (import diferido)

    return serial.Serial(
        port=Configuracion.IMPRESORA_PUERTO,
        baudrate=Configuracion.IMPRESORA_BAUDIOS,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=Configuracion.IMPRESORA_TIMEOUT,
        write_timeout=Configuracion.IMPRESORA_TIMEOUT,
    )


def estado_impresora() -> dict:
    """Reporta la configuracion y si la impresora responde."""
    info = {
        "puerto": Configuracion.IMPRESORA_PUERTO,
        "baudios": Configuracion.IMPRESORA_BAUDIOS,
        "protocolo": Configuracion.IMPRESORA_PROTOCOLO,
        "simular": Configuracion.IMPRESORA_SIMULAR,
        "conectada": False,
        "mensaje": "",
    }
    if Configuracion.IMPRESORA_SIMULAR:
        info["conectada"] = True
        info["mensaje"] = "Modo simulacion activo (no se usa hardware real)."
        return info
    try:
        with _abrir_puerto() as puerto:
            puerto.write(construir_trama(_comandos()["estado"], ""))
            respuesta = puerto.readline().decode("latin-1", errors="ignore").strip()
        info["conectada"] = True
        info["mensaje"] = respuesta or "Puerto abierto correctamente."
    except Exception as exc:
        info["conectada"] = False
        info["mensaje"] = f"No se pudo abrir el puerto: {exc}"
    return info


def _registrar_log(operacion, empresa_id, venta_id, trama, respuesta, exito, simulado, mensaje, usuario):
    """Guarda el intento de impresion en la bitacora fiscal."""
    try:
        db.session.add(
            LogImpresionFiscal(
                empresa_id=empresa_id,
                venta_id=venta_id,
                operacion=operacion,
                puerto=Configuracion.IMPRESORA_PUERTO,
                protocolo=Configuracion.IMPRESORA_PROTOCOLO,
                trama=trama,
                respuesta=respuesta or "",
                exito=exito,
                simulado=simulado,
                mensaje=(mensaje or "")[:255],
                usuario=usuario or "",
            )
        )
        db.session.commit()
    except Exception as exc:  # pragma: no cover
        db.session.rollback()
        registro.warning("No se pudo guardar el log de impresion fiscal: %s", exc)


def _enviar_tramas(tramas: list[bytes]) -> tuple[bool, str, bool]:
    """Envia las tramas a la impresora. Devuelve (exito, respuesta, simulado)."""
    trama_completa = b"\n".join(tramas).decode("latin-1", errors="replace")

    # Modo simulacion: no toca el hardware.
    if Configuracion.IMPRESORA_SIMULAR:
        return True, "SIMULADO: trama generada correctamente", True

    try:
        with _abrir_puerto() as puerto:
            respuestas = []
            for trama in tramas:
                puerto.write(trama)
                puerto.flush()
                # Muchas impresoras responden una linea por comando.
                linea = puerto.readline().decode("latin-1", errors="ignore").strip()
                if linea:
                    respuestas.append(linea)
                # Un 0x05 (ENQ) o "NAK" indican error de comunicacion.
                if "NAK" in linea or "\x15" in linea:
                    return False, "|".join(respuestas) or "La impresora respondio NAK", False
        return True, "|".join(respuestas) or "Documento fiscal emitido", False
    except Exception as exc:
        return False, str(exc), False


def imprimir_venta(empresa: dict, venta: dict, detalles: list[dict], usuario: str = "") -> dict:
    """Emite la venta en la impresora fiscal. Devuelve el resultado.

    Nunca lanza excepcion: si falla, informa para que el cajero pueda
    reintentar sin perder la venta ya registrada en el sistema.
    """
    tramas = formatear_venta(empresa, venta, detalles)
    exito, respuesta, simulado = _enviar_tramas(tramas)
    trama_txt = "[[STX]]".join(t.decode("latin-1", errors="replace") for t in tramas)
    _registrar_log(
        "venta",
        venta.get("empresa_id"),
        venta.get("id"),
        trama_txt,
        respuesta,
        exito,
        simulado,
        "Documento fiscal emitido" if exito else "Fallo la emision fiscal",
        usuario,
    )
    return {
        "exito": exito,
        "simulado": simulado,
        "respuesta": respuesta,
        "numero_tramas": len(tramas),
        "mensaje": (
            "Venta enviada a la impresora fiscal (modo simulacion)"
            if simulado and exito
            else "Venta emitida en la impresora fiscal"
            if exito
            else f"No se pudo emitir en la impresora fiscal: {respuesta}"
        ),
    }


def _operacion_simple(codigo_operacion: str, operacion: str, usuario: str = "") -> dict:
    """Ejecuta una operacion fiscal simple (reporte X/Z, abrir cajon)."""
    trama = construir_trama(_comandos()[codigo_operacion], "")
    exito, respuesta, simulado = _enviar_tramas([trama])
    _registrar_log(
        operacion,
        None,
        None,
        trama.decode("latin-1", errors="replace"),
        respuesta,
        exito,
        simulado,
        f"Operacion {operacion}",
        usuario,
    )
    return {"exito": exito, "simulado": simulado, "respuesta": respuesta}


def reporte_x(usuario: str = "") -> dict:
    """Reporte X (lectura parcial, no cierra el dia)."""
    return _operacion_simple("reporte_x", "reporte_x", usuario)


def reporte_z(usuario: str = "") -> dict:
    """Reporte Z (cierre fiscal del dia)."""
    return _operacion_simple("reporte_z", "reporte_z", usuario)


def abrir_cajon(usuario: str = "") -> dict:
    """Abre el cajon de dinero conectado a la impresora."""
    return _operacion_simple("abrir_cajon", "abrir_cajon", usuario)
