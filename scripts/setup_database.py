#!/usr/bin/env python3
"""
Script para configurar la base de datos PostgreSQL
Uso:
    python scripts/setup_database.py                         # crea tablas; un admin existente conserva rol y clave
    python scripts/setup_database.py --reset-admin-password  # reasigna la clave del admin con ADMIN_PASSWORD (pide confirmación)
    python scripts/setup_database.py --forzar-roles          # aplica el rol admin a la cuenta existente
"""

import os
import sys
from sqlalchemy import create_engine, text

# Asegurar que la raíz del proyecto esté en sys.path cuando se ejecuta como script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from claves_seguras import confirmar
from config import Config


def ensure_admin_user(reset_password=False, force_roles=False):
    """Crea el admin inicial; una cuenta existente conserva clave y rol por defecto.

    La clave cambia solo con reset_password y el rol solo con force_roles.
    """
    from models import db
    from models.core.user import User
    from services.usuarios_admin import activar_cuenta_existente

    username = Config.ADMIN_USERNAME
    password = Config.ADMIN_PASSWORD
    if not username or not password:
        return None

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, role="admin", active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return "creado"

    # Una cuenta existente conserva el rol; --forzar-roles es la única opción que lo cambia.
    activar_cuenta_existente(user)
    if force_roles:
        user.role = "admin"
    if reset_password:
        user.set_password(password)
        resultado = "clave reasignada"
    else:
        resultado = "existe, sin cambio de clave"
    db.session.commit()
    return resultado

def setup_database(reset_admin_password=False, force_roles=False):
    """Configura la base de datos PostgreSQL"""

    print("🚀 Configurando base de datos PostgreSQL...")

    db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if not db_url or not db_url.startswith("postgresql"):
        print("❌ DATABASE_URL debe apuntar a PostgreSQL (ej: postgresql://usuario:<clave>@host:5432/base)")
        sys.exit(1)

    # Crear aplicación
    app = create_app()

    with app.app_context():
        try:
            # Crear todas las tablas
            from models import db
            print("📋 Creando tablas...")
            db.create_all()
            print("✅ Tablas creadas exitosamente")

            print("👤 Asegurando usuario admin...")
            if reset_admin_password and not confirmar(
                "Se reasignará la clave del admin con ADMIN_PASSWORD."
            ):
                print("Sin confirmación: la clave del admin no se reasigna.")
                reset_admin_password = False
            resultado = ensure_admin_user(reset_password=reset_admin_password, force_roles=force_roles)
            if resultado is None:
                print("⚠️  ADMIN_USERNAME o ADMIN_PASSWORD no definidos: no se creó el admin inicial.")
            else:
                print(f"✅ Usuario admin listo ({resultado})")

            # Ejecutar seed data si existe
            seed_file = "scripts/seed_demo_data.py"
            if os.path.exists(seed_file):
                print("🌱 Ejecutando datos de ejemplo...")
                # Importar y ejecutar el script de seed
                spec = importlib.util.spec_from_file_location("seed", seed_file)
                seed_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(seed_module)

                if hasattr(seed_module, 'main'):
                    seed_module.main()
                    print("✅ Datos de ejemplo insertados")
                else:
                    print("⚠️  No se encontró función main en seed_demo_data.py")

            print("🎉 Base de datos configurada exitosamente!")

        except Exception as e:
            print(f"❌ Error configurando la base de datos: {e}")
            sys.exit(1)

if __name__ == "__main__":
    import argparse
    import importlib.util

    parser = argparse.ArgumentParser(description="Configura la base PostgreSQL y el admin inicial.")
    parser.add_argument(
        "--reset-admin-password",
        action="store_true",
        help="Reasigna la clave del admin con ADMIN_PASSWORD (pide confirmación). "
        "Sin este flag, un admin existente conserva su clave.",
    )
    parser.add_argument(
        "--forzar-roles",
        action="store_true",
        help="Aplica el rol admin a la cuenta existente (apagado por defecto).",
    )
    args = parser.parse_args()
    setup_database(reset_admin_password=args.reset_admin_password, force_roles=args.forzar_roles)