# ============================================================
# Extensiones compartidas de Flask.
# Se declaran aqui (sin inicializar) para evitar importaciones
# circulares entre los modelos y la fabrica de la aplicacion.
# ============================================================
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy

# ORM para la base de datos local del ERP (SQLite).
db = SQLAlchemy()

# Manejador de sesiones con tokens firmados.
jwt = JWTManager()

# Permite que React (otro puerto) hable con Flask sin bloqueos.
cors = CORS()
