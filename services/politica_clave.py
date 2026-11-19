"""Política de la clave nueva al cambiarla (C1 usuarios, decisión D11).

Reglas: mínimo 12 caracteres y máximo 200; sin caracteres de control (códigos menores que 32
y 127) ni solo espacios; distinta de la clave actual; distinta del nombre de usuario; fuera de
la lista corta de claves comunes. Sin reglas de complejidad.
La clave actual se verifica antes, en la vista. No hay historial de claves: «distinta de la
anterior» se resuelve como distinta de la clave que se reemplaza.

Los mensajes son afirmativos y ligados al campo. Nunca incluyen ni registran la clave.
"""

MINIMO_CARACTERES = 12
MAXIMO_CARACTERES = 200

# Claves comunes en español e inglés. Todas en minúsculas (la comparación usa casefold).
CLAVES_COMUNES = frozenset({
    # Secuencias numéricas y de teclado
    "123456789012", "1234567890123", "12345678901234", "123123123123", "123456123456",
    "111111111111", "000000000000", "abcdefghijkl", "abc123abc123", "aaaaaaaaaaaa",
    "qwerty123456", "qwertyuiop12", "qwertyuiopas", "qwertyasdfgh", "asdfghjkl123",
    "zxcvbnm12345", "1q2w3e4r5t6y", "qazwsxedcrfv",
    # Español
    "contraseña123", "contrasena123", "contraseña1234", "contrasena1234",
    "contraseñasegura", "contrasenasegura", "clavesegura123", "clavesecreta12",
    "clave1234567", "clave123456789", "miclavesecreta", "micontrasena12",
    "bienvenido1234", "bienvenido2026", "bienvenidos123", "administrador1",
    "administrador123", "adminadmin1234", "holamundo12345", "queseyo1234567",
    "empresa1234567", "tecnologia123", "sinclave12345", "hola1234567890",
    # Inglés
    "password1234", "password12345", "password123456", "passwordpassword",
    "iloveyou12345", "iloveyou2026", "letmein123456", "welcome123456", "welcome2026!!",
    "monkey1234567", "dragon1234567", "football12345", "superman12345", "sunshine12345",
    "princess12345", "master1234567", "shadow1234567", "changeme12345", "trustno1trust",
    "adminpassword", "administrator1", "password2026!",
    # Del entorno de la app
    "app360123456", "vyp1234567890", "analiticastudio", "analitica1234",
})


def errores_clave_nueva(clave_nueva, clave_repetida, nombre_usuario, clave_actual):
    """Devuelve {campo: mensaje} con los errores de la clave nueva. Vacío si la clave sirve."""
    errores = {}
    nueva = clave_nueva or ""
    if not nueva:
        errores["clave_nueva"] = "Ingresá la clave nueva."
    elif any(ord(caracter) < 32 or ord(caracter) == 127 for caracter in nueva):
        errores["clave_nueva"] = "La clave no puede tener caracteres de control."
    elif nueva.isspace():
        errores["clave_nueva"] = "La clave no puede ser solo espacios."
    elif len(nueva) < MINIMO_CARACTERES:
        errores["clave_nueva"] = f"La clave nueva debe tener al menos {MINIMO_CARACTERES} caracteres."
    elif len(nueva) > MAXIMO_CARACTERES:
        errores["clave_nueva"] = f"La clave nueva no puede tener más de {MAXIMO_CARACTERES} caracteres."
    elif nueva == (clave_actual or ""):
        errores["clave_nueva"] = "Elegí una clave distinta de la actual."
    elif nueva.casefold() == (nombre_usuario or "").casefold():
        errores["clave_nueva"] = "La clave no puede ser igual a tu nombre de usuario."
    elif nueva.casefold() in CLAVES_COMUNES:
        errores["clave_nueva"] = "Esa clave es muy común. Elegí una más difícil de adivinar."

    if not clave_repetida:
        errores["repetir_clave"] = "Repetí la clave nueva."
    elif clave_repetida != nueva:
        errores["repetir_clave"] = "Las claves no coinciden."
    return errores
