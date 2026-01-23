#!/usr/bin/env python3
"""
Script para configurar la base de datos PostgreSQL
Uso: python scripts/setup_database.py
"""

import os
import sys
from sqlalchemy import create_engine, text
from app import create_app

def setup_database():
    """Configura la base de datos PostgreSQL"""

    print("🚀 Configurando base de datos PostgreSQL...")

    # Crear aplicación
    app = create_app()

    with app.app_context():
        try:
            # Crear todas las tablas
            from models import db
            print("📋 Creando tablas...")
            db.create_all()
            print("✅ Tablas creadas exitosamente")

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