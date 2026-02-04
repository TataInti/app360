#!/bin/bash
# Script para aplicar la migración de tesorería (destinos y logs de arqueo)
# Ejecutar en el VPS con: bash scripts/migrate_tesoreria.sh

set -e  # Salir si hay error

echo "=========================================="
echo "Migración de Tesorería - App360"
echo "=========================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "app.py" ]; then
    echo "Error: Debes ejecutar este script desde el directorio raíz del proyecto"
    exit 1
fi

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    echo "Activando entorno virtual..."
    source venv/bin/activate
fi

# Verificar que las variables de entorno estén cargadas
if [ -f ".env" ]; then
    echo "Cargando variables de entorno desde .env..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Verificar SECRET_KEY
if [ -z "$SECRET_KEY" ]; then
    echo "Error: SECRET_KEY no está configurada"
    echo "Asegúrate de tener un archivo .env con las variables necesarias"
    exit 1
fi

echo ""
echo "1. Verificando estado actual de migraciones..."
python -m flask db current

echo ""
echo "2. Aplicando migración de tesorería..."
python -m flask db upgrade

echo ""
echo "3. Verificando migración aplicada..."
python -m flask db current

echo ""
echo "=========================================="
echo "Migración completada exitosamente!"
echo "=========================================="
echo ""
echo "Cambios aplicados:"
echo "  ✓ Nueva tabla: destinos_arqueo"
echo "  ✓ Nueva tabla: logs_arqueo"
echo "  ✓ Nuevas columnas en arqueos_caja:"
echo "    - destino_id"
echo "    - editado_por_id"
echo "    - fecha_edicion"
echo "    - created_at"
echo "    - updated_at"
echo "  ✓ Seeds:"
echo "    - 8 destinos predefinidos"
echo "    - 16 nuevos instrumentos de pago"
echo ""
echo "Recuerda reiniciar el servicio:"
echo "  sudo systemctl restart app360"
echo ""
