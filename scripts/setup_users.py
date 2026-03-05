#!/usr/bin/env python3
"""
Crear / actualizar usuarios para roles caja y director.

Uso:
    python scripts/setup_users.py          # crea usuarios e imprime credenciales
    python scripts/setup_users.py --reset  # regenera contraseñas

Las contraseñas se generan con secrets.token_hex(12) (24 char hex).
"""

import os
import sys
import secrets

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from models import db
from models.core.user import User

# Definición de usuarios a crear/actualizar
USERS = [
    {"username": "tesoreria", "role": "caja"},
    {"username": "direccion", "role": "director"},
]


def setup_users(reset_passwords: bool = False):
    app = create_app()
    with app.app_context():
        credentials = []
        for u in USERS:
            user = User.query.filter_by(username=u["username"]).first()
            password = None

            if not user:
                password = secrets.token_hex(12)
                user = User(
                    username=u["username"],
                    role=u["role"],
                    active=True,
                )
                user.set_password(password)
                db.session.add(user)
                print(f"  + Creado: {u['username']} ({u['role']})")
            elif reset_passwords:
                password = secrets.token_hex(12)
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

        print("\n--- Credenciales (guardar en lugar seguro) ---")
        for c in credentials:
            if c["password"]:
                print(f"  {c['username']} / {c['password']}  (rol: {c['role']})")
            else:
                print(f"  {c['username']}  (rol: {c['role']}) — contraseña sin cambios")
        print("----------------------------------------------")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    setup_users(reset_passwords=reset)
