#!/usr/bin/env bash
"""
Script completo para migrar App360 a PostgreSQL
Uso: ./scripts/migrate_to_postgres.sh
"""

set -e

echo "🚀 Iniciando migración completa a PostgreSQL..."

# Verificar que estamos en el directorio correcto
if [ ! -f "app.py" ]; then
    echo "❌ Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

# Verificar que PostgreSQL esté disponible
echo "📋 Verificando conexión a PostgreSQL..."
python -c "
import os
from sqlalchemy import create_engine
url = os.getenv('DATABASE_URL')
if not url: raise SystemExit('Definí DATABASE_URL (ver .env.example).')
engine = create_engine(url)
engine.execute('SELECT 1')
print('✅ PostgreSQL disponible')
" || {
    echo "❌ PostgreSQL no está disponible. Verifica la configuración."
    exit 1
}

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python -m venv venv
fi

# Activar entorno virtual
echo "🔧 Activando entorno virtual..."
source venv/bin/activate

# Instalar dependencias
echo "📦 Instalando dependencias..."
pip install -r requirements.txt

# Configurar base de datos
echo "🗄️  Configurando base de datos PostgreSQL..."
python scripts/setup_database.py

# Migrar datos si existe SQLite
if [ -f "instance/silva360.db" ]; then
    echo "📊 Migrando datos desde SQLite..."
    python scripts/migrate_to_postgres.py
else
    echo "ℹ️  No se encontraron datos existentes en SQLite"
fi

# Verificar migración
echo "🔍 Verificando migración..."
python scripts/verify_migration.py

echo ""
echo "🎉 ¡Migración completada exitosamente!"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Actualiza tu archivo .env con DATABASE_URL de PostgreSQL"
echo "   2. Ejecuta 'python app.py' para probar la aplicación"
echo "   3. Considera eliminar el archivo SQLite si ya no lo necesitas"
echo ""
echo "🔒 Recuerda configurar backups para PostgreSQL en producción"