# ============================================================
# Empresa y configuracion del negocio.
# Fiskor permite manejar varias empresas dentro de la misma
# base de datos local, separando la informacion por empresa_id.
# ============================================================
from app.extensions import db
from app.models.base import ModeloBase


class Empresa(ModeloBase):
    """Datos fiscales y contables de la empresa."""

    __tablename__ = "empresas"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(10), unique=True, nullable=False)
    # Correo del usuario dueño del negocio. Sirve para que cada usuario
    # vea SOLO su propia informacion (aislamiento por usuario).
    propietario_email = db.Column(db.String(150), default="", index=True)
    nombre = db.Column(db.String(120), nullable=False)
    nombre_fiscal = db.Column(db.String(180), default="")
    rif = db.Column(db.String(20), default="")
    direccion = db.Column(db.String(255), default="")
    telefono = db.Column(db.String(40), default="")
    email = db.Column(db.String(120), default="")

    # Ejercicio economico
    inicio_ejercicio = db.Column(db.Date, nullable=True)
    cierre_ejercicio = db.Column(db.Date, nullable=True)

    # Condiciones tributarias
    contribuyente_especial = db.Column(db.Boolean, default=False)
    porcentaje_iva = db.Column(db.Float, default=16.0)
    porcentaje_igtf = db.Column(db.Float, default=3.0)
    serial_onat = db.Column(db.String(60), default="")

    # Imagen corporativa e identidad de los documentos.
    # Se guardan rutas RELATIVAS dentro de app/static/uploads.
    logo_ruta = db.Column(db.String(255), default="")
    sello_ruta = db.Column(db.String(255), default="")
    firma_ruta = db.Column(db.String(255), default="")
    firma_nombre = db.Column(db.String(120), default="")
    firma_cargo = db.Column(db.String(120), default="")
    color_marca = db.Column(db.String(10), default="#1d4ed8")
    # Texto libre que se imprime al pie de la factura/nota de entrega.
    pie_documento = db.Column(db.Text, default="")

    activa = db.Column(db.Boolean, default=True)

    def sello_activo(self) -> bool:
        """Indica si la empresa tiene configurada una imagen de sello."""
        return bool(self.sello_ruta)

    def a_diccionario(self, excluir: tuple = ()) -> dict:
        """Agrega banderas utiles para el frontend (tiene logo/sello)."""
        datos = super().a_diccionario(excluir)
        datos["tiene_logo"] = bool(self.logo_ruta)
        datos["tiene_sello"] = bool(self.sello_ruta)
        datos["tiene_firma"] = bool(self.firma_ruta)
        return datos


class ParametroSistema(ModeloBase):
    """Tabla clave-valor para guardar preferencias generales."""

    __tablename__ = "parametros_sistema"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(80), unique=True, nullable=False)
    valor = db.Column(db.Text, default="")
    descripcion = db.Column(db.String(200), default="")

    @staticmethod
    def obtener(clave: str, por_defecto: str = "") -> str:
        """Lee un parametro por su clave."""
        registro = ParametroSistema.query.filter_by(clave=clave).first()
        return registro.valor if registro else por_defecto

    @staticmethod
    def guardar(clave: str, valor: str, descripcion: str = "") -> "ParametroSistema":
        """Crea o actualiza un parametro."""
        registro = ParametroSistema.query.filter_by(clave=clave).first()
        if registro:
            registro.valor = valor
        else:
            registro = ParametroSistema(clave=clave, valor=valor, descripcion=descripcion)
            db.session.add(registro)
        return registro
