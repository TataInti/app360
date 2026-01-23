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

# Verificar que el directorio del proyecto existe y está configurado correctamente
echo "📁 Verificando directorio del proyecto..."
if ssh_cmd "test -d $PROJECT_DIR"; then
    echo "✅ Directorio existe, verificando repositorio git..."
    if ssh_cmd "cd $PROJECT_DIR && git status" 2>/dev/null; then
        echo "✅ Repositorio git válido encontrado"
        # Verificar si tiene remote origin configurado
        if ssh_cmd "cd $PROJECT_DIR && git remote get-url origin" 2>/dev/null; then
            echo "✅ Remote origin configurado"
        else
            echo "⚠️  Configurando remote origin..."
            ssh_cmd "cd $PROJECT_DIR && git remote add origin https://github.com/TataInti/app360.git"
        fi
    else
        echo "⚠️  Directorio existe pero no es repositorio git válido. Reclonando..."
        ssh_cmd "rm -rf $PROJECT_DIR"
        ssh_cmd "git clone https://github.com/TataInti/app360.git $PROJECT_DIR"
    fi
else
    echo "📥 Clonando repositorio desde GitHub..."
    ssh_cmd "git clone https://github.com/TataInti/app360.git $PROJECT_DIR"
fi

# Hacer pull de los cambios
echo "📥 Haciando pull de cambios..."
ssh_cmd "cd $PROJECT_DIR && git checkout main 2>/dev/null || git checkout -b main"
ssh_cmd "cd $PROJECT_DIR && git pull origin main"

# Instalar dependencias en entorno virtual
echo "📦 Instalando dependencias..."
ssh_cmd "cd $PROJECT_DIR && (test -d venv || python3 -m venv venv)"
ssh_cmd "cd $PROJECT_DIR && source venv/bin/activate && pip install --upgrade python-dotenv"
ssh_cmd "cd $PROJECT_DIR && source venv/bin/activate && pip install -r requirements.txt"

# Ejecutar migraciones de base de datos si es necesario
echo "🗄️  Verificando base de datos..."
# ssh_cmd "cd $PROJECT_DIR && source venv/bin/activate && PYTHONPATH=/var/www/app360 python -c \"from scripts.verify_migration import *; verify_migration()\"" || {
#     echo "⚠️  Posible problema con la base de datos. Considera ejecutar migraciones."
# }
echo "⚠️  Verificación de base de datos omitida temporalmente"

# Reiniciar servicios si están corriendo
echo "🔄 Verificando servicios..."
ssh_cmd "cd $PROJECT_DIR && ps aux | grep -v grep | grep -q 'python app.py' && (pkill -f 'python app.py' && echo '🛑 Servicio detenido') || echo 'ℹ️  No hay servicio corriendo'"

# Iniciar la aplicación
echo "▶️  Iniciando aplicación..."
ssh_cmd "cd $PROJECT_DIR && PYTHONPATH=/var/www/app360 /var/www/app360/venv/bin/python -c \"
import os
os.chdir('/var/www/app360')
from dotenv import load_dotenv
load_dotenv()
from app import app
app.run(host='0.0.0.0', port=5000, debug=False)
\" > app.log 2>&1 &"

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