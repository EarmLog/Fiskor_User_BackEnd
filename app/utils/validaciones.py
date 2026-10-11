# ============================================================
# Utilidades de validacion y saneamiento de datos.
# Todo lo que entra por la API pasa por aqui antes de tocar la
# base de datos, para evitar inyecciones y datos basura.
# ============================================================
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

# Letras validas para el RIF venezolano:
# V = Venezolano, E = Extranjero, J = Juridico, P = Pasaporte,
# G = Gubernamental, C = Consejo Comunal.
LETRAS_RIF = "VEJPGCMRN A"
PATRON_RIF_ESTRICTO = re.compile(r"^[VEJPGCM]-?\d{8}-?\d$")
PATRON_CEDULA = re.compile(r"^[VE]?-?\d{6,9}$")
PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PATRON_SOLO_TEXTO = re.compile(r"[<>\"'`;\\]")

# Pesos oficiales para el calculo del digito verificador del RIF.
_PESOS_RIF = [3, 2, 7, 6, 5, 4, 3, 2]
_VALOR_LETRA_RIF = {"V": 1, "E": 2, "J": 3, "P": 4, "G": 5, "C": 6, "M": 7, "R": 8, "N": 9}


def limpiar_texto(valor: Optional[str], maximo: int = 255) -> str:
    """Quita espacios y caracteres peligrosos para evitar XSS.

    Se usa en los campos de nombre, descripcion y direccion.
    """
    if valor is None:
        return ""
    texto = str(valor).strip()
    # Eliminamos etiquetas HTML y caracteres usados en inyecciones.
    texto = texto.replace("<", "").replace(">", "")
    texto = PATRON_SOLO_TEXTO.sub("", texto)
    texto = re.sub(r"\s+", " ", texto)  # espacios multiples -> uno solo
    return texto[:maximo]


def normalizar_rif(rif: Optional[str]) -> str:
    """Deja el RIF en formato estandar J-12345678-9 (mayusculas)."""
    if not rif:
        return ""
    limpio = re.sub(r"[\s\-\.]", "", str(rif)).upper()
    if len(limpio) < 2:
        return limpio
    letra, cuerpo = limpio[0], limpio[1:]
    if len(cuerpo) >= 9:
        return f"{letra}-{cuerpo[:8]}-{cuerpo[8]}"
    return f"{letra}-{cuerpo}"


def validar_rif(rif: Optional[str]) -> tuple[bool, str]:
    """Valida el formato de un RIF venezolano.

    Devuelve (es_valido, mensaje). El formato es obligatorio;
    el digito verificador se valida como verificacion adicional.
    """
    normalizado = normalizar_rif(rif)
    if not normalizado:
        return False, "El RIF es obligatorio"
    if not PATRON_RIF_ESTRICTO.match(normalizado):
        return False, "Formato de RIF invalido. Debe ser tipo J-12345678-9"
    letra = normalizado[0]
    if letra not in _VALOR_LETRA_RIF:
        return False, f"Tipo de RIF '{letra}' no permitido en Venezuela"
    return True, "RIF valido"


def calcular_digito_rif(cuerpo: str) -> int:
    """Calcula el digito verificador de un RIF por el metodo modulo 11."""
    cuerpo = re.sub(r"\D", "", cuerpo)[:8]
    if len(cuerpo) != 8:
        return -1
    suma = sum(int(cuerpo[i]) * _PESOS_RIF[i] for i in range(8))
    resto = suma % 11
    digito = 11 - resto
    if digito >= 10:
        digito -= 9
    return digito


def validar_cedula(cedula: Optional[str]) -> tuple[bool, str]:
    """Valida el formato de una cedula venezolana (V-12345678)."""
    if not cedula:
        return False, "La cedula es obligatoria"
    limpio = re.sub(r"[\s\-\.]", "", str(cedula)).upper()
    if not PATRON_CEDULA.match(limpio):
        return False, "Formato de cedula invalido. Ejemplo: V-12345678"
    return True, "Cedula valida"


def validar_email(correo: Optional[str]) -> tuple[bool, str]:
    """Valida el formato de un correo electronico."""
    if not correo:
        return False, "El correo es obligatorio"
    if not PATRON_EMAIL.match(str(correo).strip()):
        return False, "El correo no tiene un formato valido"
    return True, "Correo valido"


def a_decimal(valor, por_defecto: Decimal = Decimal("0")) -> Optional[Decimal]:
    """Convierte un valor a Decimal controlando errores de formato."""
    if valor is None or valor == "":
        return por_defecto
    try:
        if isinstance(valor, str):
            # Aceptamos coma o punto como separador decimal.
            valor = valor.replace(".", "").replace(",", ".") if valor.count(",") == 1 and "." in valor else valor.replace(",", ".")
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None


def validar_monto(valor, nombre: str = "monto", permitir_negativo: bool = False) -> tuple[bool, str]:
    """Valida que un valor sea numerico y coherente para un monto."""
    numero = a_decimal(valor)
    if numero is None:
        return False, f"El {nombre} debe ser un numero valido"
    if not permitir_negativo and numero < 0:
        return False, f"El {nombre} no puede ser negativo"
    if numero > Decimal("999999999999"):
        return False, f"El {nombre} es demasiado grande"
    return True, "Monto valido"


def validar_entero(valor, nombre: str = "valor", minimo: int = 0) -> tuple[bool, str]:
    """Valida que un valor sea un entero dentro del rango permitido."""
    try:
        numero = int(float(str(valor).replace(",", ".")))
    except (ValueError, TypeError):
        return False, f"El {nombre} debe ser un numero entero"
    if numero < minimo:
        return False, f"El {nombre} no puede ser menor a {minimo}"
    return True, "Valor valido"
