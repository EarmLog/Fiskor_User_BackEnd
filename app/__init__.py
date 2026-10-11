# ============================================================
# Fabrica de la aplicacion (App Factory) de Fiskor ERP.
#
# Aqui se prepara todo: base de datos local en modo WAL,
# extensiones, blueprints, manejadores de error y el registro
# de logs. Nada de esto puede tumbar el servidor: cualquier
# error inesperado se captura y se responde con un JSON limpio.
# ============================================================
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from app.config import Configuracion, obtener_configuracion
from app.extensions import db, jwt


def _preparar_carpetas() -> None:
    """Crea las carpetas de trabajo si no existen."""
    for ruta in (
        Configuracion.RUTA_INSTANCIA,
        Configuracion.RUTA_RESPALDOS,
        Configuracion.RUTA_LOGS,
        Configuracion.RUTA_EXPORTADOS,
    ):
        ruta.mkdir(parents=True, exist_ok=True)


def _configurar_logs(app: Flask) -> None:
    """Configura el log rotativo de errores en logs/error.log."""
    manejador = RotatingFileHandler(
        Configuracion.RUTA_LOGS / "error.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    manejador.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    manejador.setLevel(logging.WARNING)

    registro_app = logging.getLogger("fiskor")
    registro_app.setLevel(logging.INFO)
    if not registro_app.handlers:
        registro_app.addHandler(manejador)
        consola = logging.StreamHandler()
        consola.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        registro_app.addHandler(consola)

    app.logger.handlers = registro_app.handlers
    app.logger.setLevel(logging.INFO)


def _activar_wal(app: Flask) -> None:
    """Activa el modo WAL de SQLite para soportar varios usuarios.

    WAL permite que varios usuarios LEAN al mismo tiempo mientras
    otro ESCRIBE, evitando el clasico "database is locked".
    """
    try:
        with app.app_context():
            # journal_mode=WAL se guarda en el propio archivo .db,
            # por lo que solo hace falta aplicarlo una vez.
            db.session.execute(text("PRAGMA journal_mode=WAL;"))
            db.session.execute(text("PRAGMA synchronous=NORMAL;"))
            db.session.execute(text("PRAGMA busy_timeout=30000;"))
            db.session.execute(text("PRAGMA foreign_keys=ON;"))
            db.session.commit()
    except Exception as exc:  # pragma: no cover
        app.logger.warning("No se pudo activar el modo WAL: %s", exc)


def _registrar_manejadores_error(app: Flask) -> None:
    """Captura cualquier excepcion y responde con un JSON limpio."""

    @app.errorhandler(HTTPException)
    def manejar_http(error_http: HTTPException):
        # Errores conocidos (404, 405, 401, etc.) sin ruido en los logs.
        return (
            {
                "exito": False,
                "datos": None,
                "mensaje": error_http.description or "Recurso no encontrado",
            },
            error_http.code,
        )

    @app.errorhandler(Exception)
    def manejar_error_global(error_excepcion: Exception):  # noqa: ANN001
        # Registramos TODO el error internamente para poder depurar.
        app.logger.exception(
            "Error no controlado en %s %s: %s",
            request.method,
            request.path,
            error_excepcion,
        )
        # Al usuario le devolvemos un mensaje amable, nunca el stacktrace.
        return (
            {
                "exito": False,
                "datos": None,
                "mensaje": "Por favor, verifique los datos ingresados. "
                "Si el problema continua, revise el archivo de logs.",
            },
            500,
        )


def _registrar_callbacks_jwt() -> None:
    """Devuelve JSON limpio cuando el token falta, expiro o es invalido."""

    @jwt.unauthorized_loader
    def sin_token(motivo: str):
        return {"exito": False, "datos": None, "mensaje": "Debe iniciar sesion para continuar"}, 401

    @jwt.invalid_token_loader
    def token_invalido(motivo: str):
        return {"exito": False, "datos": None, "mensaje": "La sesion no es valida"}, 401

    @jwt.expired_token_loader
    def token_expirado(encabezado, carga):
        return {"exito": False, "datos": None, "mensaje": "La sesion expiro, vuelva a entrar"}, 401


def crear_aplicacion() -> Flask:
    """Construye y configura la aplicacion Flask completa."""
    _preparar_carpetas()

    app = Flask(__name__, instance_path=str(Configuracion.RUTA_INSTANCIA))
    app.config.from_object(obtener_configuracion())

    _configurar_logs(app)

    # Inicializamos las extensiones.
    db.init_app(app)
    jwt.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": Configuracion.ORIGENES_PERMITIDOS}},
        supports_credentials=True,
    )

    # Importamos los modelos para que SQLAlchemy los registre.
    from app import models  # noqa: F401

    with app.app_context():
        db.create_all()

    _activar_wal(app)
    _registrar_callbacks_jwt()
    _registrar_manejadores_error(app)

    # Registramos todos los modulos de la API.
    from app.blueprints import registrar_blueprints

    registrar_blueprints(app)

    # Rutas basicas de salud y raiz.
    @app.route("/api/salud")
    def salud():
        return {"exito": True, "datos": {"estado": "ok", "app": "Fiskor ERP"}, "mensaje": "Servidor activo"}

    # Sembramos los datos iniciales (admin, empresa demo, parametros).
    from app.seed import sembrar_datos_iniciales

    with app.app_context():
        sembrar_datos_iniciales(app)

    app.logger.info("Fiskor ERP iniciado correctamente.")
    return app
