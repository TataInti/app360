#!/usr/bin/env bash
"""
Script para hacer pull de cambios al VPS
Uso: ./scripts/deploy_to_vps.sh
"""

set -e

# Configuración del VPS
VPS_HOST="72.61.47.19"
VPS_USER="root"
VPS_PASSWORD="AccesoServerVirtual+7423"
PROJECT_DIR="/var/www/app360"

echo "🚀 Iniciando despliegue al VPS..."

# Función para ejecutar comandos en el VPS
ssh_cmd() {
    sshpass -p "$VPS_PASSWORD" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "$1"
}

# Verificar conexión al VPS
echo "📡 Verificando conexión al VPS..."
ssh_cmd "echo '✅ Conexión exitosa al VPS'"

# Verificar que el directorio del proyecto existe
echo "📁 Verificando directorio del proyecto..."
ssh_cmd "test -d $PROJECT_DIR || (echo '❌ Directorio $PROJECT_DIR no existe en el VPS' && exit 1)"

# Verificar que es un repositorio git
echo "🔧 Verificando repositorio git..."
ssh_cmd "cd $PROJECT_DIR && git status" || {
    echo "❌ No es un repositorio git válido en $PROJECT_DIR"
    exit 1
}

# Hacer pull de los cambios
echo "📥 Haciando pull de cambios..."
ssh_cmd "cd $PROJECT_DIR && git pull origin main"

# Instalar dependencias si requirements.txt cambió
echo "📦 Verificando dependencias..."
ssh_cmd "cd $PROJECT_DIR && pip install -r requirements.txt"

# Ejecutar migraciones de base de datos si es necesario
echo "🗄️  Verificando base de datos..."
ssh_cmd "cd $PROJECT_DIR && python scripts/verify_migration.py" || {
    echo "⚠️  Posible problema con la base de datos. Considera ejecutar migraciones."
}

# Reiniciar servicios si están corriendo
echo "🔄 Verificando servicios..."
ssh_cmd "cd $PROJECT_DIR && ps aux | grep -v grep | grep -q 'python app.py' && (pkill -f 'python app.py' && echo '🛑 Servicio detenido') || echo 'ℹ️  No hay servicio corriendo'"

# Iniciar la aplicación
echo "▶️  Iniciando aplicación..."
ssh_cmd "cd $PROJECT_DIR && nohup python app.py > app.log 2>&1 &"

# Verificar que la aplicación está corriendo
echo "🔍 Verificando que la aplicación está corriendo..."
sleep 3
ssh_cmd "curl -f http://localhost:5000/api/health && echo '✅ Aplicación corriendo correctamente' || echo '❌ Error al verificar aplicación'"

echo ""
echo "🎉 ¡Despliegue completado exitosamente!"
echo ""
echo "📊 Información del despliegue:"
echo "   🌐 URL: http://vyp.app360.com.ar"
echo "   📁 Directorio: $PROJECT_DIR"
echo "   📝 Logs: $PROJECT_DIR/app.log"
echo ""
echo "🔧 Comandos útiles en el VPS:"
echo "   Conectar: ssh $VPS_USER@$VPS_HOST"
echo "   Ver logs: tail -f $PROJECT_DIR/app.log"
echo "   Reiniciar: cd $PROJECT_DIR && pkill -f 'python app.py' && nohup python app.py &"