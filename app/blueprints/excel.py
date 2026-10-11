# ============================================================
# Importacion/Exportacion Excel para auditoria (Supabase).
# Permite al usuario corregir en masa desde su equipo.
# ============================================================
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Blueprint, request
from werkzeug.utils import secure_filename

from app.config import Configuracion
from app.services import supabase_client
from app.services.excel_supabase_service import exportar_lista, leer_excel
from app.services.repo_supabase import RepoSB
from app.utils.contexto import empresa_activa_id
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, usuario_actual

excel_bp = Blueprint("excel", __name__, url_prefix="/api/excel")

EXTS = {".xlsx", ".xls"}


def _validar_archivo(archivo):
    nombre = archivo.filename or ""
    ext = Path(nombre).suffix.lower()
    if ext not in EXTS:
        raise ValueError("Solo se permiten archivos .xlsx/.xls")
    return nombre, ext


@excel_bp.route("/exportar/<string:tabla>", methods=["GET"])
@requiere_sesion
def exportar(tabla: str):
    try:
        empresa_id = empresa_activa_id()
        repo = RepoSB(tabla)
        filas = repo.listar(empresa_id=empresa_id)
        columnas_map = {
            "productos": ["id", "codigo", "nombre", "precio_usd", "precio_bolivares", "stock_actual", "stock_minimo", "categoria_id", "empresa_id"],
            "clientes": ["id", "rif", "nombre", "telefono", "direccion", "email", "empresa_id", "saldo_pendiente"],
            "ventas": ["id", "numero_factura", "fecha", "cliente_id", "estado", "subtotal", "iva", "total", "total_bolivares", "empresa_id"],
            "facturas": ["id", "numero", "cliente_id", "items", "total_usd", "tasa_bcv", "fecha", "empresa_id"],
        }
        ruta = exportar_lista(filas, columnas_map.get(tabla), f"{tabla}_export")
        return exito({"archivo": Path(ruta).name, "ruta": ruta}, "Exportado a Excel")
    except Exception as exc:
        return error(str(exc), 500)


@excel_bp.route("/importar/<string:tabla>", methods=["POST"])
@requiere_sesion
def importar(tabla: str):
    archivo = request.files.get("archivo")
    if not archivo:
        return error("Debe adjuntar un archivo .xlsx", 400)
    try:
        _validar_archivo(archivo)
        Configuracion.RUTA_EXPORTADOS.mkdir(parents=True, exist_ok=True)
        nombre_seguro = secure_filename(archivo.filename or f"{tabla}_import.xlsx")
        destino = Configuracion.RUTA_EXPORTADOS / f"import_{tabla}_{datetime.now():%Y%m%d_%H%M%S}_{nombre_seguro}"
        archivo.save(destino)
        df = leer_excel(destino)
        empresa_id = empresa_activa_id()
        if "empresa_id" in df.columns:
            df["empresa_id"] = empresa_id
        elif empresa_id is not None:
            df["empresa_id"] = empresa_id
        repo = RepoSB(tabla)
        filas = df.to_dict(orient="records")
        actualizados = repo.upsert(filas) if filas else []
        return exito({"procesados": len(actualizados), "actualizados": actualizados}, "Importacion completada")
    except ValueError as ve:
        return error(str(ve), 400)
    except Exception as exc:
        return error(str(exc), 500)
