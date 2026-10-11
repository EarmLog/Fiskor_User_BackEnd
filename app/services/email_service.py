# ============================================================
# Servicio de correo saliente (SMTP).
#
# Se usa para:
#   - Enviar el enlace de recuperacion de contrasena.
#   - Avisar al administrador de una solicitud de registro.
#
# Diseno a prueba de fallos: si el SMTP no esta configurado o el
# envio falla, NO se rompe la operacion. Se registra en el log y
# se devuelve el resultado para que el llamador decida.
# ============================================================
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import Configuracion

registro = logging.getLogger("fiskor")


def correo_configurado() -> bool:
    """Indica si hay un servidor SMTP listo para enviar correos."""
    return bool(Configuracion.SMTP_HOST)


def enviar_correo(destinatario: str, asunto: str, cuerpo_texto: str, cuerpo_html: str | None = None) -> dict:
    """Envia un correo simple (texto y, opcionalmente, HTML).

    Devuelve un diccionario: {"enviado": bool, "motivo": str}.
    Nunca lanza excepcion hacia arriba.
    """
    if not correo_configurado():
        registro.warning(
            "SMTP no configurado. Correo a %s ('%s') no enviado.", destinatario, asunto
        )
        return {"enviado": False, "motivo": "smtp_no_configurado"}

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = formataddr(
        (Configuracion.CORREO_NOMBRE, _extraer_direccion(Configuracion.CORREO_REMITENTE))
    )
    mensaje["To"] = destinatario
    mensaje.set_content(cuerpo_texto)
    if cuerpo_html:
        mensaje.add_alternative(cuerpo_html, subtype="html")

    try:
        contexto = ssl.create_default_context()
        if Configuracion.SMTP_USAR_TLS:
            with smtplib.SMTP(Configuracion.SMTP_HOST, Configuracion.SMTP_PORT, timeout=15) as servidor:
                servidor.starttls(context=contexto)
                if Configuracion.SMTP_USUARIO:
                    servidor.login(Configuracion.SMTP_USUARIO, Configuracion.SMTP_CLAVE)
                servidor.send_message(mensaje)
        else:
            with smtplib.SMTP_SSL(
                Configuracion.SMTP_HOST, Configuracion.SMTP_PORT, timeout=15, context=contexto
            ) as servidor:
                if Configuracion.SMTP_USUARIO:
                    servidor.login(Configuracion.SMTP_USUARIO, Configuracion.SMTP_CLAVE)
                servidor.send_message(mensaje)
        registro.info("Correo enviado a %s: %s", destinatario, asunto)
        return {"enviado": True, "motivo": "ok"}
    except Exception as exc:  # pragma: no cover - depende de la red/servidor
        registro.error("No se pudo enviar el correo a %s: %s", destinatario, exc)
        return {"enviado": False, "motivo": str(exc)}


def _extraer_direccion(remitente: str) -> str:
    """Extrae la direccion pura de un remitente tipo 'Nombre <correo>'."""
    if "<" in remitente and ">" in remitente:
        return remitente.split("<", 1)[1].split(">", 1)[0].strip()
    return remitente.strip()


def enviar_recuperacion(destinatario: str, nombre: str, enlace: str) -> dict:
    """Envia el enlace para restablecer la contrasena."""
    asunto = "Fiskor ERP - Recuperacion de contrasena"
    texto = (
        f"Hola {nombre or 'usuario'},\n\n"
        "Recibimos una solicitud para restablecer la contrasena de tu cuenta.\n"
        f"Abre este enlace para crear una nueva (vence pronto):\n\n{enlace}\n\n"
        "Si no solicitaste este cambio, ignora este mensaje.\n\n"
        "— Fiskor ERP"
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
      <h2 style="color:#1d4ed8">Recuperacion de contrasena</h2>
      <p>Hola {nombre or 'usuario'},</p>
      <p>Recibimos una solicitud para restablecer la contrasena de tu cuenta.</p>
      <p style="text-align:center;margin:24px 0">
        <a href="{enlace}" style="background:#1d4ed8;color:#fff;padding:12px 22px;
           border-radius:8px;text-decoration:none;font-weight:bold">
          Crear nueva contrasena
        </a>
      </p>
      <p style="color:#64748b;font-size:13px">Si el boton no funciona, copia este enlace:<br>
        <a href="{enlace}">{enlace}</a></p>
      <p style="color:#94a3b8;font-size:12px">Si no solicitaste este cambio, ignora este mensaje.</p>
    </div>
    """
    return enviar_correo(destinatario, asunto, texto, html)


def enviar_aviso_registro(destinatario_admin: str, solicitud: dict) -> dict:
    """Avisa al administrador que hay una solicitud de registro nueva."""
    asunto = "Fiskor ERP - Nueva solicitud de registro"
    texto = (
        "Se recibio una solicitud de registro:\n\n"
        f"Nombre: {solicitud.get('nombre', '')}\n"
        f"Correo: {solicitud.get('email', '')}\n"
        f"Cargo: {solicitud.get('cargo', '')}\n"
        f"Telefono: {solicitud.get('telefono', '')}\n\n"
        "Ingresa al modulo de Usuarios para aprobarla o rechazarla.\n\n"
        "— Fiskor ERP"
    )
    return enviar_correo(destinatario_admin, asunto, texto)
