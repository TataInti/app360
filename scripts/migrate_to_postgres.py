#!/usr/bin/env python3
"""
Script para migrar datos de SQLite a PostgreSQL
Uso: python scripts/migrate_to_postgres.py
"""

import os
import sys
from sqlalchemy import create_engine, MetaData, Table, select, insert, delete

# Configuración de bases de datos
SQLITE_URL = "sqlite:///instance/360.db"
POSTGRES_URL = os.getenv("DATABASE_URL")
if not POSTGRES_URL:
    raise SystemExit("Definí DATABASE_URL (ver .env.example) antes de migrar a PostgreSQL.")

def migrate_data():
    """Migra datos de SQLite a PostgreSQL"""

    print("🚀 Iniciando migración de SQLite a PostgreSQL...")

    # Conectar a SQLite
    sqlite_engine = create_engine(SQLITE_URL)
    sqlite_metadata = MetaData()
    sqlite_metadata.reflect(sqlite_engine)

    # Conectar a PostgreSQL
    postgres_engine = create_engine(POSTGRES_URL)
    postgres_metadata = MetaData()
    postgres_metadata.reflect(postgres_engine)

    try:
        # Obtener todas las tablas
        tables = sqlite_metadata.sorted_tables

        for table in tables:
            print(f"📋 Migrando tabla: {table.name}")

            # Obtener datos de SQLite
            sqlite_table = Table(table.name, sqlite_metadata, autoload_with=sqlite_engine)
            with sqlite_engine.connect() as conn:
                result = conn.execute(select(sqlite_table))
                rows = result.fetchall()

            if not rows:
                print(f"   ℹ️  Tabla {table.name} está vacía")
                continue

            # Insertar datos en PostgreSQL
            postgres_table = Table(table.name, postgres_metadata, autoload_with=postgres_engine)

            with postgres_engine.connect() as conn:
                # Limpiar tabla destino si tiene datos
                conn.execute(delete(postgres_table))
                conn.commit()

                # Insertar datos
                for row in rows:
                    conn.execute(insert(postgres_table).values(dict(row)))
                    conn.commit()

            print(f"   ✅ Migrados {len(rows)} registros")

        print("🎉 Migración completada exitosamente!")

    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Verificar que las bases de datos existan
    if not os.path.exists("instance/silva360.db"):
        print("❌ Base de datos SQLite no encontrada en instance/silva360.db")
        print("   Asegúrate de tener datos existentes antes de migrar.")
        sys.exit(1)

    migrate_data()