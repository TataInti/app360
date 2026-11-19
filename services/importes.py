"""Parser único de importes escritos en formularios (formato es-AR).

Reglas (corte D1, punto D-1):
- «.» separa miles y «,» separa decimales. Si aparecen los dos, el último es el decimal.
- Un único «.» seguido de exactamente 3 dígitos son miles: «1.234» = 1234.
- Un único «.» seguido de 1 o 2 dígitos es decimal: «12.5» = 12.5, «1234.56» = 1234.56.
- «1.234,56» = 1234.56 y «1.234.567,89» = 1234567.89.
- Se aceptan hasta 2 decimales. Más decimales se rechazan: no se redondea en silencio.
- Texto no numérico, vacío, decimales ambiguos o fuera de rango se RECHAZAN con
  ImporteInvalido. Nunca devuelven 0 en silencio.
- Un símbolo «$» inicial y los espacios de los extremos se ignoran.

Los números nativos (int, float, Decimal) llegan de JSON ya normalizados y se toman
tal cual. Para texto usar siempre parse_importe, no Decimal(texto.replace(...)).
"""

import math
import re
from decimal import Decimal, InvalidOperation

MENSAJE_IMPORTE_INVALIDO = "Ingresá un importe válido, por ejemplo 1.234,56"
MENSAJE_IMPORTE_FUERA_DE_RANGO = "El importe supera el máximo permitido (9.999.999.999,99)"
MAXIMO_NUMERIC_12_2 = Decimal("9999999999.99")

_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


class ImporteInvalido(ValueError, InvalidOperation):
    """Importe que no se puede interpretar.

    Hereda de ValueError (para except ValueError) y de InvalidOperation (para los
    except InvalidOperation que ya existían en el código).
    """

    def __init__(self, mensaje=MENSAJE_IMPORTE_INVALIDO):
        super().__init__(mensaje)
        self.mensaje = mensaje


def _grupos_de_miles_validos(grupos):
    """El primer grupo tiene de 1 a 3 dígitos y el resto, exactamente 3."""
    if not grupos or not grupos[0].isdigit() or not 1 <= len(grupos[0]) <= 3:
        return False
    return all(len(grupo) == 3 and grupo.isdigit() for grupo in grupos[1:])


def _separar(texto):
    """Devuelve (parte_entera_sin_separadores, decimales) o lanza ImporteInvalido."""
    if not _NUMERO.fullmatch(texto):
        raise ImporteInvalido()
    separadores = {caracter for caracter in texto if caracter in ".,"}
    if not separadores:
        return texto, ""

    if len(separadores) == 2:
        # Ambos: el último es el decimal y debe aparecer una sola vez.
        decimal = "," if texto.rfind(",") > texto.rfind(".") else "."
        miles = "." if decimal == "," else ","
        if texto.count(decimal) != 1:
            raise ImporteInvalido()
        entero, decimales = texto.rsplit(decimal, 1)
        grupos = entero.split(miles)
        if not _grupos_de_miles_validos(grupos):
            raise ImporteInvalido()
        return "".join(grupos), decimales

    separador = separadores.pop()
    partes = texto.split(separador)
    if len(partes) == 2:
        izquierda, derecha = partes
        if separador == ",":
            return izquierda, derecha
        # Un único punto: 3 dígitos son miles; 1 o 2, decimales.
        if len(derecha) == 3:
            if not _grupos_de_miles_validos(partes):
                raise ImporteInvalido()
            return "".join(partes), ""
        if len(derecha) in (1, 2):
            return izquierda, derecha
        raise ImporteInvalido()

    # Varios separadores iguales: solo los puntos pueden ser miles.
    if separador == ",":
        raise ImporteInvalido()
    if not _grupos_de_miles_validos(partes):
        raise ImporteInvalido()
    return "".join(partes), ""


def parse_importe(valor, maximo=None):
    """Convierte un importe escrito en formato es-AR (o un número) a Decimal.

    maximo: tope absoluto opcional (por ejemplo MAXIMO_NUMERIC_12_2 para columnas
    Numeric(12, 2)). Lanza ImporteInvalido si el valor no se puede interpretar o
    supera el tope.
    """
    if isinstance(valor, bool) or valor is None:
        raise ImporteInvalido()
    if isinstance(valor, Decimal):
        importe = valor
    elif isinstance(valor, int):
        importe = Decimal(valor)
    elif isinstance(valor, float):
        if not math.isfinite(valor):
            raise ImporteInvalido()
        importe = Decimal(str(valor))
    else:
        texto = str(valor).strip()
        if texto.startswith("$"):
            texto = texto[1:].strip()
        signo = ""
        if texto[:1] in ("+", "-"):
            signo = "-" if texto[0] == "-" else ""
            texto = texto[1:]
        entero, decimales = _separar(texto)
        if len(decimales) > 2:
            raise ImporteInvalido()
        numero = f"{signo}{entero}" + (f".{decimales}" if decimales else "")
        try:
            importe = Decimal(numero)
        except InvalidOperation as error:
            raise ImporteInvalido() from error

    if not importe.is_finite():
        raise ImporteInvalido()
    if maximo is not None and abs(importe) > maximo:
        raise ImporteInvalido(MENSAJE_IMPORTE_FUERA_DE_RANGO)
    return importe
