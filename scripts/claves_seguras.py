"""Utilidades compartidas por los scripts de alta de usuarios.

Las claves de cuentas nuevas se generan al azar. No se escriben en archivos ni en
logs: se muestran por consola solo si el operador pasa --mostrar-claves.
"""

import secrets

CONFIRMACION = "SI"


def generar_clave():
    """Devuelve una clave aleatoria para una cuenta nueva o una regeneración."""
    return secrets.token_urlsafe(16)


def confirmar(mensaje):
    """Pide confirmación escrita. Sin entrada disponible (stdin cerrado) devuelve False."""
    try:
        respuesta = input(f"{mensaje} Escribí {CONFIRMACION} para confirmar: ")
    except EOFError:
        return False
    return respuesta.strip() == CONFIRMACION
