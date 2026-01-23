#!/bin/bash

# Script para verificar el estado del despliegue en VPS
# Uso: ./scripts/check_deployment.sh

set -e

# Configuración del VPS
VPS_HOST="72.61.47.19"
VPS_USER="root"
VPS_PASSWORD="AccesoServerVirtual+7423"
PROJECT_DIR="/var/www/app360"

echo "🔍 Verificando despliegue en VPS..."
echo "================================="

# Función para ejecutar comandos en el VPS
run_ssh() {
    sshpass -p "$VPS_PASSWORD" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "$1"
}

echo "📊 Estado de servicios:"
echo "----------------------"

# Verificar si PostgreSQL está corriendo
echo "PostgreSQL:"
run_ssh "systemctl is-active postgresql" || echo "❌ PostgreSQL no está activo"

# Verificar si la aplicación Python está corriendo
echo "Aplicación Python:"
run_ssh "ps aux | grep 'python app.py' | grep -v grep" || echo "❌ Aplicación Python no está corriendo"

# Verificar Nginx (si está configurado)
echo "Nginx:"
run_ssh "systemctl is-active nginx" 2>/dev/null || echo "⚠️  Nginx no está activo (opcional)"

echo ""
echo "📁 Estado del proyecto:"
echo "----------------------"

# Verificar directorio del proyecto
echo "Directorio del proyecto:"
run_ssh "ls -la $PROJECT_DIR" || echo "❌ Directorio del proyecto no existe"

# Verificar archivos importantes
echo "Archivos de configuración:"
run_ssh "ls -la $PROJECT_DIR/.env" || echo "❌ Archivo .env no existe"
run_ssh "ls -la $PROJECT_DIR/venv" || echo "❌ Entorno virtual no existe"

echo ""
echo "🌐 Estado de la aplicación:"
echo "--------------------------"

# Verificar conectividad de la API
echo "API Health Check:"
run_ssh "curl -s http://localhost:5000/api/health" || echo "❌ API no responde"

# Verificar puerto 5000
echo "Puerto 5000:"
run_ssh "netstat -tlnp | grep :5000" || echo "❌ Puerto 5000 no está abierto"

echo ""
echo "📊 Estado de la base de datos:"
echo "-----------------------------"

# Verificar conexión a PostgreSQL
echo "Conexión a PostgreSQL:"
run_ssh "sudo -u postgres psql -d app360 -c 'SELECT version();'" > /dev/null 2>&1 && echo "✅ PostgreSQL conectado" || echo "❌ Error de conexión a PostgreSQL"

# Verificar tablas en la base de datos
echo "Tablas en la base de datos:"
run_ssh "sudo -u postgres psql -d app360 -c '\dt'" || echo "❌ Error al listar tablas"

echo ""
echo "📝 Logs recientes:"
echo "------------------"

# Mostrar últimas líneas del log de la aplicación
echo "Últimas 10 líneas del log de la aplicación:"
run_ssh "tail -10 $PROJECT_DIR/app.log" 2>/dev/null || echo "❌ No se pudo acceder al log"

echo ""
echo "✅ Verificación completada"