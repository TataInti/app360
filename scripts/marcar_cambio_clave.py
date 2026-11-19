#!/usr/bin/env python3
"""Marca o desmarca la obligación de cambiar la clave de un usuario (C1 usuarios).

Uso:
    python scripts/marcar_cambio_clave.py --usuario anibal.lopez
    python scripts/marcar_cambio_clave.py --usuario anibal.lopez --quitar

Solo cambia la bandera must_change_password. No modifica la clave ni cierra sesiones: la
marca rige desde la siguiente petición, en web y en API. Usa la base de DATABASE_URL del
entorno o del .env del proyecto. No imprime claves.
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def marcar_cambio_clave(usuario_nombre, quitar=False, app=None):
    """Devuelve (codigo, mensaje). Código 0 si se aplicó; 1 si el usuario no existe."""
    from models import db
    from models.core.user import User

    if app is None:
        from app import create_app

        app = create_app()
    with app.app_context():
        usuario = User.query.filter_by(username=usuario_nombre).one_or_none()
        if usuario is None:
            return 1, f"No existe el usuario {usuario_nombre!r}. No se cambió nada."
        usuario.must_change_password = not quitar
        db.session.commit()
        if quitar:
            return 0, f"Listo: {usuario.username} ya no tiene que cambiar la clave al ingresar."
        aviso = "" if usuario.active else " La cuenta está desactivada: no puede ingresar hasta reactivarla."
        return 0, f"Listo: {usuario.username} deberá cambiar su clave al ingresar.{aviso}"


def main(argv=None, app=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usuario", required=True, help="nombre de usuario (username)")
    parser.add_argument("--quitar", action="store_true", help="quita la obligación en vez de ponerla")
    args = parser.parse_args(argv)
    codigo, mensaje = marcar_cambio_clave(args.usuario.strip(), quitar=args.quitar, app=app)
    print(mensaje)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
