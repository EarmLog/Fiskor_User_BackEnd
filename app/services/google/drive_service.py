# ============================================================
# Servicio de Google Drive (cuenta de servicio) para respaldos.
# Permite subir archivos de respaldo generados en el servidor.
#
# Requisitos: credenciales JSON de cuenta de servicio + carpeta
# compartida con el correo de la cuenta de servicio (email en JSON).
# ============================================================
import json
import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.config import Configuracion

registro = logging.getLogger("fiskor")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveError(Exception):
    """Error personalizado al operar con Google Drive."""


class DriveService:
    """Cliente ligero para Google Drive con cuenta de servicio."""

    def __init__(self) -> None:
        self._cred_path = Configuracion.GDRIVE_CREDENCIALES
        self._folder_id = Configuracion.GDRIVE_CARPETA_ID
        self._service = None

    def _cargar_credenciales(self) -> service_account.Credentials:
        if not self._cred_path:
            raise DriveError("Falta FISKOR_GDRIVE_CREDENCIALES")
        ruta = Path(self._cred_path)
        if not ruta.is_absolute():
            ruta = Configuracion.RUTA_BACKEND / ruta
        if not ruta.exists():
            raise DriveError(f"No existe el archivo de credenciales: {ruta}")
        return service_account.Credentials.from_service_account_file(str(ruta), scopes=SCOPES)

    def _obtener_servicio(self):
        if self._service is None:
            creds = self._cargar_credenciales()
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def disponible(self) -> bool:
        """Indica si la configuracion para Drive esta completa."""
        return bool(self._cred_path and self._folder_id)

    def subir_respaldo(self, ruta_archivo: str, nombre_archivo: str, descripcion: str = "Respaldo Fiskor") -> dict[str, Any]:
        """Sube un archivo al Drive en la carpeta configurada.

        Returns: {id, nombre, webViewLink, webContentLink}
        """
        ruta = Path(ruta_archivo)
        if not ruta.exists():
            raise DriveError(f"No existe el respaldo: {ruta}")
        try:
            servicio = self._obtener_servicio()
            archivo = {
                "name": nombre_archivo,
                "description": descripcion,
                "parents": [self._folder_id] if self._folder_id else [],
                "mimeType": "application/octet-stream",
            }
            media = MediaFileUpload(str(ruta), mimetype="application/octet-stream", resumable=False)
            resultado = servicio.files().create(
                body=archivo,
                media_body=media,
                fields="id,name,webViewLink,webContentLink",
            ).execute()
            return {
                "id": resultado.get("id"),
                "nombre": resultado.get("name"),
                "webViewLink": resultado.get("webViewLink"),
                "webContentLink": resultado.get("webContentLink"),
            }
        except HttpError as exc:
            registro.error("Error de Google Drive: %s", exc)
            raise DriveError("No se pudo subir el respaldo a Google Drive") from exc
        except Exception as exc:
            registro.error("Error al subir respaldo a Drive: %s", exc)
            raise DriveError("Error inesperado al subir a Google Drive") from exc


drive_service = DriveService()
