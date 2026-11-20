"""TOTP según RFC 6238 con la biblioteca estándar (C6 de administración de usuarios).

HMAC-SHA1, paso de 30 segundos y 6 dígitos (RFC 4226 para el truncado dinámico). Sin dependencias
nuevas: hmac, hashlib, struct, base64 y secrets. Verificado con los vectores del RFC 6238 en
tests/test_usuarios_c6.py. La ventana de aceptación es de ±1 paso.
"""

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

PASO_SEGUNDOS = 30
DIGITOS = 6
BYTES_SECRETO = 20
VENTANA_PASOS = 1
EMISOR = "App360"


def generar_secreto():
    """20 bytes aleatorios (160 bits), el tamaño recomendado por el RFC 4226 para HMAC-SHA1."""
    return secrets.token_bytes(BYTES_SECRETO)


def secreto_a_base32(secreto):
    """Clave en base32 sin relleno, para que la persona la escriba en su aplicación."""
    return base64.b32encode(secreto).decode("ascii").rstrip("=")


def secreto_desde_base32(texto):
    limpio = "".join(str(texto or "").split()).upper()
    relleno = "=" * (-len(limpio) % 8)
    return base64.b32decode(limpio + relleno)


def agrupar_en_bloques(texto_base32):
    """Grupos de cuatro caracteres separados por espacio, como se muestran en pantalla."""
    return " ".join(texto_base32[i : i + 4] for i in range(0, len(texto_base32), 4))


def codigo_en_paso(secreto, paso, digitos=DIGITOS):
    """Código de 6 dígitos para un contador de pasos (RFC 4226, sección 5.3)."""
    mensaje = struct.pack(">Q", paso)
    digesto = hmac.new(secreto, mensaje, hashlib.sha1).digest()
    desplazamiento = digesto[-1] & 0x0F
    entero = struct.unpack(">I", digesto[desplazamiento : desplazamiento + 4])[0] & 0x7FFFFFFF
    return f"{entero % (10 ** digitos):0{digitos}d}"


def paso_de(instante_epoch):
    return int(instante_epoch) // PASO_SEGUNDOS


def pasos_coincidentes(secreto, codigo, instante_epoch, ventana=VENTANA_PASOS):
    """Pasos de la ventana (±ventana) en los que el código coincide. Compara en tiempo constante."""
    if not isinstance(codigo, str) or len(codigo) != DIGITOS or not codigo.isdigit():
        return []
    centro = paso_de(instante_epoch)
    coincidentes = []
    for paso in range(centro - ventana, centro + ventana + 1):
        if paso < 0:
            continue
        if hmac.compare_digest(codigo_en_paso(secreto, paso), codigo):
            coincidentes.append(paso)
    return coincidentes


def uri_otpauth(secreto_base32, cuenta):
    """Enlace otpauth:// para las aplicaciones de códigos. Se muestra como texto, sin QR."""
    etiqueta = f"{quote(EMISOR)}:{quote(cuenta)}"
    return (
        f"otpauth://totp/{etiqueta}?secret={secreto_base32}&issuer={quote(EMISOR)}"
        f"&algorithm=SHA1&digits={DIGITOS}&period={PASO_SEGUNDOS}"
    )
