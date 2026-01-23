#!/usr/bin/env python3
"""
Script para verificar la integridad de la base de datos después de la migración
Uso: python scripts/verify_migration.py
"""

import os
import sys

# Agregar el directorio raíz al path de Python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db

def verify_migration():
    """Verifica que la migración a PostgreSQL fue exitosa"""

    print("🔍 Verificando migración a PostgreSQL...")

    app = create_app()

    with app.app_context():
        try:
            # Verificar conexión
            db.engine.execute(db.text("SELECT 1"))
            print("✅ Conexión a PostgreSQL exitosa")

            # Obtener todas las tablas
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()

            if not tables:
                print("⚠️  No se encontraron tablas en la base de datos")
                return

            print(f"📋 Tablas encontradas: {len(tables)}")

            total_records = 0
            for table in tables:
                try:
                    # Contar registros en cada tabla
                    result = db.session.execute(db.text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    total_records += count
                    print(f"   {table}: {count} registros")
                except Exception as e:
                    print(f"   ❌ Error en tabla {table}: {e}")

            print(f"📊 Total de registros: {total_records}")

            # Verificar tablas críticas
            critical_tables = ['users', 'products', 'locations']
            missing_tables = []

            for table in critical_tables:
                if table not in tables:
                    missing_tables.append(table)

            if missing_tables:
                print(f"❌ Faltan tablas críticas: {missing_tables}")
                return False

            print("✅ Verificación completada exitosamente")
            return True

        except Exception as e:
            print(f"❌ Error durante la verificación: {e}")
            return False

if __name__ == "__main__":
    success = verify_migration()
    sys.exit(0 if success else 1)