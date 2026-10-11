# ============================================================
# Configuracion general de Fiskor ERP
# Aqui centralizamos todo lo que el sistema necesita para
# arrancar: rutas, credenciales y reglas fiscales del pais.
# ============================================================
import os
from pathlib import Path

from dotenv import load_dotenv

# Cargamos el archivo .env que vive en la raiz del backend.
# RUTA_BACKEND = .../BackEnd
RUTA_BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(RUTA_BACKEND / ".env")


def _obtener(clave: str, por_defecto: str = "") -> str:
    """Lee una variable de entorno y quita espacios sobrantes."""
    return (os.getenv(clave) or por_defecto).strip()


class Configuracion:
    """Configuracion base, compartida por todos los entornos."""

    # --- Claves y sesion ---
    CLAVE_SECRETA = _obtener("FISKOR_JWT_SECRET", "clave_de_desarrollo_insegura")
    JWT_SECRET_KEY = CLAVE_SECRETA
    JWT_HORAS_VALIDEZ = int(_obtener("FISKOR_JWT_HORAS", "12"))
    ENTORNO = _obtener("FISKOR_ENTORNO", "desarrollo")
    EN_PRODUCCION = ENTORNO.lower() in ("produccion", "production")

    # --- Carpetas del proyecto ---
    RUTA_BACKEND = RUTA_BACKEND
    RUTA_INSTANCIA = RUTA_BACKEND / "instancia"
    RUTA_RESPALDOS = RUTA_BACKEND / "respaldos"
    RUTA_LOGS = RUTA_BACKEND / "logs"
    RUTA_EXPORTADOS = RUTA_BACKEND / "exportados"
    # Carpeta donde se guardan las imagenes corporativas (logos, sellos,
    # firmas) y cualquier archivo subido por el usuario.
    RUTA_UPLOADS = RUTA_BACKEND / "app" / "static" / "uploads"
    # Tamano maximo de archivo permitido al subir (16 MB).
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    # Carpeta con la app compilada del frontend (FrontEnd/dist). Si existe,
    # Flask tambien sirve la interfaz y las rutas del SPA (registro, login...).
    # Se puede sobreescribir con FISKOR_FRONTEND_DIST.
    RUTA_FRONTEND_DIST = Path(
        _obtener("FISKOR_FRONTEND_DIST", str(RUTA_BACKEND.parent / "FrontEnd" / "dist"))
    )

    # --- Base de datos local del ERP (SQLite) ---
    RUTA_SQLITE = _obtener("FISKOR_SQLITE_RUTA") or str(RUTA_INSTANCIA / "fiskor.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{RUTA_SQLITE}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # timeout alto para que SQLite espere en vez de lanzar "database is locked"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30, "check_same_thread": False},
        "pool_pre_ping": True,
    }

    # --- Supabase (solo login y usuarios) ---
    SUPABASE_HOST = _obtener("SUPABASE_HOST")
    SUPABASE_PORT = int(_obtener("SUPABASE_PORT", "5432"))
    SUPABASE_DB = _obtener("SUPABASE_DB", "postgres")
    SUPABASE_USER = _obtener("SUPABASE_USER", "postgres")
    SUPABASE_PASSWORD = _obtener("SUPABASE_PASSWORD")
    SUPABASE_URL = _obtener("SUPABASE_URL")
    SUPABASE_ANON_KEY = _obtener("SUPABASE_ANON_KEY")

    # --- Tasa de cambio / BCV ---
    TASA_API_URL = _obtener(
        "TASA_API_URL",
        "https://v6.exchangerate-api.com/v6/becfb2759aa20c88eea88fc/latest/USD",
    )
    # Funciona en modo cascada: si la primera API falla, probamos la siguiente,
    # asi el ERP siempre consigue una tasa y nunca depende de un solo servicio.
    TASA_API_URLS = [
        _obtener(
            "TASA_API_URL",
            "https://v6.exchangerate-api.com/v6/becfb2759aa20c88eea88fc/latest/USD",
        ),
        "https://open.er-api.com/v6/latest/USD",
    ]
    TASA_MONEDA = _obtener("TASA_MONEDA", "USD")
    TASA_MONEDA_DESTINO = _obtener("TASA_MONEDA_DESTINO", "VES")
    TASA_TIMEOUT = 8  # segundos maximos de espera a la API externa

    # --- Reglas fiscales Venezuela ---
    PORCENTAJE_IVA = float(_obtener("FISKOR_IVA", "16.0"))
    PORCENTAJE_IGTF = float(_obtener("FISKOR_IGTF", "3.0"))

    # --- Usuario administrador inicial ---
    ADMIN_EMAIL = _obtener("ADMIN_EMAIL", "earm2771@gmail.com")
    ADMIN_PASSWORD = _obtener("ADMIN_PASSWORD", "E27712316e")
    ADMIN_NOMBRE = _obtener("ADMIN_NOMBRE", "Administrador")

    # --- CORS: permitimos el frontend de desarrollo ---
    ORIGENES_PERMITIDOS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ]

    # --- Registro de usuarios y recuperacion de contrasena ---
    # URL publica del frontend; se usa para armar los enlaces de correo.
    URL_FRONTEND = _obtener("FISKOR_URL_FRONTEND", "http://localhost:5173")
    # Minutos que vive un enlace de recuperacion de contrasena.
    MINUTOS_TOKEN_RECUPERACION = int(_obtener("FISKOR_MINUTOS_TOKEN", "60"))
    # Si es "true", los registros nuevos deben ser aprobados por un admin.
    REGISTRO_REQUIERE_APROBACION = _obtener("FISKOR_REGISTRO_APROBACION", "true").lower() in (
        "1",
        "true",
        "si",
        "yes",
    )

    # --- Correo saliente (SMTP) ---
    # Si no se configura, el sistema NO falla: registra el mensaje en los
    # logs y (solo en desarrollo) devuelve el enlace al frontend.
    SMTP_HOST = _obtener("FISKOR_SMTP_HOST")
    SMTP_PORT = int(_obtener("FISKOR_SMTP_PORT", "587"))
    SMTP_USUARIO = _obtener("FISKOR_SMTP_USUARIO")
    SMTP_CLAVE = _obtener("FISKOR_SMTP_CLAVE")
    SMTP_USAR_TLS = _obtener("FISKOR_SMTP_TLS", "true").lower() in ("1", "true", "si", "yes")
    CORREO_REMITENTE = _obtener("FISKOR_CORREO_REMITENTE", "Fiskor ERP <no-responder@fiskor.local>")
    CORREO_NOMBRE = _obtener("FISKOR_CORREO_NOMBRE", "Fiskor ERP")

    @classmethod
    def correo_configurado(cls) -> bool:
        """Indica si hay un servidor SMTP listo para enviar correos."""
        return bool(cls.SMTP_HOST)

    # --- Capa fiscal: impresoras fiscales (SENIAT) ---
    # Puerto serie/USB donde esta conectada la impresora fiscal.
    #   Linux:  /dev/ttyUSB0, /dev/ttyS0
    #   Windows: COM3, COM4
    IMPRESORA_PUERTO = _obtener("FISKOR_IMPRESORA_PUERTO", "/dev/ttyUSB0")
    IMPRESORA_BAUDIOS = int(_obtener("FISKOR_IMPRESORA_BAUDIOS", "9600"))
    IMPRESORA_TIMEOUT = float(_obtener("FISKOR_IMPRESORA_TIMEOUT", "3"))
    # Protocolo/ marca soportada: HKA, THE_FACTORY, GENERICO.
    IMPRESORA_PROTOCOLO = _obtener("FISKOR_IMPRESORA_PROTOCOLO", "HKA").upper()
    # Cuando es "true" no se abre el puerto real: se simula la impresion.
    # Muy util para probar el flujo sin hardware conectado.
    IMPRESORA_SIMULAR = _obtener("FISKOR_IMPRESORA_SIMULAR", "true").lower() in (
        "1",
        "true",
        "si",
        "yes",
    )

    # --- Respaldos en Google Drive (Cuenta de servicio) ---
    GDRIVE_CREDENCIALES = _obtener("FISKOR_GDRIVE_CREDENCIALES")
    GDRIVE_CARPETA_ID = _obtener("FISKOR_GDRIVE_CARPETA")


class ConfiguracionDesarrollo(Configuracion):
    DEBUG = True


class ConfiguracionProduccion(Configuracion):
    DEBUG = False


def obtener_configuracion() -> type[Configuracion]:
    """Devuelve la clase de configuracion segun el entorno actual."""
    if Configuracion.EN_PRODUCCION:
        return ConfiguracionProduccion
    return ConfiguracionDesarrollo
