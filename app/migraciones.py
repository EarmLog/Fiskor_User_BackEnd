# ============================================================
# Migraciones ligeras para SQLite.
#
# db.create_all() solo crea tablas que faltan, NO agrega columnas
# nuevas a tablas que ya existen. Como Fiskor evoluciona (por
# ejemplo, cuando agregamos logo_ruta a las empresas), aqui
# revisamos cada tabla y agregamos las columnas que falten.
#
# Es seguro ejecutarlo en cada arranque: solo actua si detecta
# diferencias y nunca borra informacion.
# ============================================================
import logging

from sqlalchemy import inspect, text

from app.extensions import db

registro = logging.getLogger("fiskor")


def _valor_por_defecto(columna) -> str | None:
    """Devuelve la clausula DEFAULT lista para SQL, o None.

    Solo aceptamos valores escalares (numeros, textos, booleanos).
    Los valores calculados (fechas actuales) se dejan como NULL.
    """
    defecto = columna.default
    if defecto is None or not getattr(defecto, "arg", None):
        return None
    valor = defecto.arg
    if callable(valor):
        return None
    if isinstance(valor, bool):
        return f"DEFAULT {1 if valor else 0}"
    if isinstance(valor, (int, float)):
        return f"DEFAULT {valor}"
    texto = str(valor).replace("'", "''")
    return f"DEFAULT '{texto}'"


def aplicar_migraciones_ligeras() -> None:
    """Agrega las columnas que falten en las tablas existentes."""
    inspector = inspect(db.engine)
    tablas_existentes = set(inspector.get_table_names())

    for tabla in db.metadata.sorted_tables:
        if tabla.name not in tablas_existentes:
            continue  # db.create_all() ya se encargo de los faltantes

        columnas_db = {c["name"] for c in inspector.get_columns(tabla.name)}
        for columna in tabla.columns:
            if columna.name in columnas_db:
                continue
            tipo = columna.type.compile(dialect=db.engine.dialect)
            sentencia = f'ALTER TABLE {tabla.name} ADD COLUMN {columna.name} {tipo}'
            defecto = _valor_por_defecto(columna)
            if defecto:
                sentencia += f" {defecto}"
            try:
                with db.engine.begin() as conexion:
                    conexion.execute(text(sentencia))
                registro.info("Migracion aplicada: %s.%s", tabla.name, columna.name)
            except Exception as exc:  # pragma: no cover
                registro.warning(
                    "No se pudo agregar la columna %s.%s: %s", tabla.name, columna.name, exc
                )
