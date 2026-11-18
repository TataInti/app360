#!/usr/bin/env python3
"""
Crear / actualizar usuarios para roles caja y director.

Uso:
    python scripts/setup_users.py                   # crea los faltantes; no reasigna claves existentes
    python scripts/setup_users.py --mostrar-claves  # además muestra una vez las claves generadas
    python scripts/setup_users.py --reset           # regenera claves de usuarios existentes (pide confirmación)

Las claves se generan con secrets.token_urlsafe(16). No se escriben en archivos ni en logs.
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from claves_seguras import confirmar, generar_clave
from models import db
from models.core.user import User

# Definición de usuarios a crear/actualizar
USERS = [
    {"username": "tesoreria", "role": "caja"},
    {"username": "direccion", "role": "director"},
]


def setup_users(reset_passwords: bool = False, mostrar_claves: bool = False):
    app = create_app()
    with app.app_context():
        credentials = []
        for u in USERS:
            user = User.query.filter_by(username=u["username"]).first()
            password = None

            if not user:
                password = generar_clave()
                user = User(
                    username=u["username"],
                    role=u["role"],
                    active=True,
                )
                user.set_password(password)
                db.session.add(user)
                print(f"  + Creado: {u['username']} ({u['role']})")
            elif reset_passwords:
                password = generar_clave()
                user.set_password(password)
                user.role = u["role"]
                user.active = True
                print(f"  ~ Reset: {u['username']} ({u['role']})")
            else:
                # Asegurar rol y active
                user.role = u["role"]
                user.active = True
                print(f"  = Existe: {u['username']} ({u['role']}) — sin cambio de contraseña")

            credentials.append(
                {"username": u["username"], "role": u["role"], "password": password}
            )

        db.session.commit()

        generadas = [c for c in credentials if c["password"]]
        if generadas and mostrar_claves:
            print("\n--- Claves generadas (se muestran una sola vez; no se guardan) ---")
            for c in generadas:
                print(f"  {c['username']} / {c['password']}  (rol: {c['role']})")
            print("----------------------------------------------")
        elif generadas:
            print(
                "\nHay claves generadas que no se muestran. Usar --mostrar-claves "
                "para verlas una vez (no se guardan)."
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Crea o actualiza los usuarios caja y director.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Regenera las claves de usuarios existentes. Pide confirmación.",
    )
    parser.add_argument(
        "--mostrar-claves",
        action="store_true",
        help="Muestra una vez las claves generadas en esta corrida.",
    )
    args = parser.parse_args(argv)

    reset = args.reset
    if reset and not confirmar("Se regenerarán las claves de los usuarios existentes."):
        print("Sin confirmación: no se regeneran claves.")
        reset = False

    setup_users(reset_passwords=reset, mostrar_claves=args.mostrar_claves)


if __name__ == "__main__":
    main()
