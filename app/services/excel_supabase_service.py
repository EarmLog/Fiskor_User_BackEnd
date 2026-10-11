# ============================================================
# Exportacion/Importacion de datos a Excel con validacion.
# Usado para auditoria y correcciones masivas.
# ============================================================
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.utils import get_column_letter

from app.config import Configuracion

registro = logging.getLogger("fiskor")


def exportar_dataframe(df: pd.DataFrame, nombre_base: str) -> str:
    Configuracion.RUTA_EXPORTADOS.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    ruta = Configuracion.RUTA_EXPORTADOS / f"{nombre_base}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Datos", index=False)
    return str(ruta)


def exportar_lista(filas: list[dict[str, Any]], columnas: list[str] | None, nombre_base: str) -> str:
    df = pd.DataFrame(filas)
    if columnas:
        columnas_orden = [c for c in columnas if c in df.columns] + [c for c in df.columns if c not in (columnas or [])]
        df = df.reindex(columns=columnas_orden)
    return exportar_dataframe(df, nombre_base)


def leer_excel(ruta: Path | str) -> pd.DataFrame:
    ruta_p = Path(ruta)
    df = pd.read_excel(ruta_p)
    df.columns = [str(c).strip() for c in df.columns]
    return df.where(pd.notna(df), None)
