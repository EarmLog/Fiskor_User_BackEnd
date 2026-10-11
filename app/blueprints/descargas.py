# ============================================================
# API de descargas.
#
# Los documentos y reportes se generan en disco (exportados/). Como
# el navegador no puede leer rutas del servidor, aqui exponemos una
# ruta segura que entrega el archivo como adjunto.
# ============================================================
from pathlib import Path

from flask import Blueprint, send_file

from app.config import Configuracion
from app.utils.respuestas import error
from app.utils.seguridad import requiere_sesion

descargas_bp = Blueprint("descargas", __name__, url_prefix="/api/descargas")

# Solo permitimos descargar archivos generados por el propio ERP.
CATEGORIAS_VALIDAS = {"excel", "pdf", "word", "nomina"}


@descargas_bp.route("/<string:categoria>/<path:nombre>", methods=["GET"])
@requiere_sesion
def descargar(categoria: str, nombre: str):
    """Entrega un archivo generado en la carpeta exportados/<categoria>."""
    if categoria not in CATEGORIAS_VALIDAS:
        return error("Categoria de descarga no valida", 404)

    # Bloqueamos cualquier intento de salir de la carpeta (path traversal).
    nombre_limpio = Path(nombre).name
    if nombre_limpio != nombre or ".." in nombre:
        return error("Nombre de archivo no valido", 400)

    ruta = (Configuracion.RUTA_EXPORTADOS / categoria / nombre_limpio).resolve()
    # Confirmamos que la ruta final siga dentro de la carpeta permitida.
    base = (Configuracion.RUTA_EXPORTADOS / categoria).resolve()
    if base not in ruta.parents and ruta.parent != base:
        return error("Ruta no permitida", 400)
    if not ruta.exists() or not ruta.is_file():
        return error("El archivo ya no esta disponible", 404)

    return send_file(ruta, as_attachment=True, download_name=nombre_limpio)
