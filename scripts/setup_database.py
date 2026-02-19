#!/usr/bin/env python3
"""
Script para configurar la base de datos PostgreSQL
Uso: python scripts/setup_database.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Asegurar que la raíz del proyecto esté en sys.path cuando se ejecuta como script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from config import Config


def ensure_admin_user():
    from models import db
    from models.core.user import User

    username = Config.ADMIN_USERNAME
    password = Config.ADMIN_PASSWORD
    if not username or not password:
        return

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, role="admin", active=True)
        db.session.add(user)

    user.active = True
    # No podemos verificar el hash vs password sin conocer algoritmo, así que
    # en dev lo seteamos siempre para asegurar acceso.
    user.set_password(password)
    if not user.role:
        user.role = "admin"

    db.session.commit()

def setup_database():
    """Configura la base de datos PostgreSQL"""

    print("🚀 Configurando base de datos PostgreSQL...")

    db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if not db_url or not db_url.startswith("postgresql"):
        print("❌ DATABASE_URL debe apuntar a PostgreSQL (ej: postgresql://user:pass@localhost:5432/app360)")
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
            ensure_admin_user()
            print("✅ Usuario admin listo")

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
    import importlib.util
    setup_database()