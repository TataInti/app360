#!/bin/bash

# Script para backup automático de la base de datos PostgreSQL en VPS
# Uso: ./scripts/backup_database.sh

set -e

# Configuración del VPS
VPS_HOST="72.61.47.19"
VPS_USER="root"
VPS_PASSWORD="AccesoServerVirtual+7423"
PROJECT_DIR="/var/www/app360"
BACKUP_DIR="$PROJECT_DIR/backups"

# Configuración de la base de datos
DB_NAME="app360"
DB_USER="app360"

# Función para ejecutar comandos en el VPS
run_ssh() {
    sshpass -p "$VPS_PASSWORD" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "$1"
}

echo "💾 Iniciando backup de base de datos..."
echo "====================================="

# Crear directorio de backups si no existe
run_ssh "mkdir -p $BACKUP_DIR"

# Generar nombre del archivo de backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="backup_$TIMESTAMP.sql"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_FILE"

echo "📁 Creando backup: $BACKUP_FILE"

# Crear backup de la base de datos
run_ssh "sudo -u postgres pg_dump -U $DB_USER -h localhost $DB_NAME > $BACKUP_PATH"

# Verificar que el backup se creó correctamente
BACKUP_SIZE=$(run_ssh "ls -lh $BACKUP_PATH | awk '{print \$5}'")
echo "✅ Backup creado exitosamente: $BACKUP_SIZE"

# Comprimir el backup
COMPRESSED_FILE="${BACKUP_FILE}.gz"
COMPRESSED_PATH="$BACKUP_DIR/$COMPRESSED_FILE"

run_ssh "gzip $BACKUP_PATH"
echo "📦 Backup comprimido: $COMPRESSED_FILE"

# Limpiar backups antiguos (mantener solo los últimos 10)
echo "🧹 Limpiando backups antiguos..."
run_ssh "cd $BACKUP_DIR && ls -t *.sql.gz | tail -n +11 | xargs -r rm -f"

# Mostrar información del backup
echo ""
echo "📊 Información del backup:"
echo "-------------------------"
echo "Archivo: $COMPRESSED_FILE"
echo "Ubicación: $COMPRESSED_PATH"
echo "Tamaño: $(run_ssh "ls -lh $COMPRESSED_PATH | awk '{print \$5}'")"

# Listar backups disponibles
echo ""
echo "📁 Backups disponibles:"
run_ssh "ls -lh $BACKUP_DIR/*.sql.gz" | head -10

echo ""
echo "✅ Backup completado exitosamente"

# Opcional: Descargar el backup localmente
if [ "$1" = "--download" ]; then
    echo ""
    echo "⬇️  Descargando backup localmente..."
    mkdir -p ./backups
    sshpass -p "$VPS_PASSWORD" scp -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST:$COMPRESSED_PATH" "./backups/"
    echo "✅ Backup descargado: ./backups/$COMPRESSED_FILE"
fi