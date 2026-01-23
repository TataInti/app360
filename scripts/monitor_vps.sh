#!/bin/bash

# Script de monitoreo continuo para el VPS
# Uso: ./scripts/monitor_vps.sh

# Configuración del VPS
VPS_HOST="72.61.47.19"
VPS_USER="root"
VPS_PASSWORD="AccesoServerVirtual+7423"
PROJECT_DIR="/var/www/app360"

# Función para ejecutar comandos en el VPS
run_ssh() {
    sshpass -p "$VPS_PASSWORD" ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" "$1" 2>/dev/null
}

# Función para verificar servicio
check_service() {
    local service=$1
    local status=$(run_ssh "systemctl is-active $service")
    if [ "$status" = "active" ]; then
        echo "✅ $service: Activo"
        return 0
    else
        echo "❌ $service: Inactivo"
        return 1
    fi
}

# Función para verificar proceso Python
check_python_app() {
    local process_count=$(run_ssh "ps aux | grep 'python app.py' | grep -v grep | wc -l")
    if [ "$process_count" -gt 0 ]; then
        echo "✅ Aplicación Python: Corriendo ($process_count proceso(s))"
        return 0
    else
        echo "❌ Aplicación Python: Detenida"
        return 1
    fi
}

# Función para verificar API
check_api() {
    local response=$(run_ssh "curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/api/health")
    if [ "$response" = "200" ]; then
        echo "✅ API: Respondiendo correctamente"
        return 0
    else
        echo "❌ API: Error HTTP $response"
        return 1
    fi
}

# Función para verificar base de datos
check_database() {
    local db_check=$(run_ssh "sudo -u postgres psql -d app360 -c 'SELECT 1;' 2>/dev/null | grep -c '1'")
    if [ "$db_check" -gt 0 ]; then
        echo "✅ Base de datos: Conectada"
        return 0
    else
        echo "❌ Base de datos: Error de conexión"
        return 1
    fi
}

# Función para verificar uso de recursos
check_resources() {
    echo "📊 Uso de recursos:"
    run_ssh "echo 'CPU: '; top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\1/' | awk '{print 100 - \$1\"%\"}'"
    run_ssh "echo 'Memoria: '; free | grep Mem | awk '{printf \"%.2f%%\", \$3/\$2 * 100.0}'"
    run_ssh "echo 'Disco: '; df -h / | awk 'NR==2 {print \$5}'"
}

# Función principal de monitoreo
monitor() {
    echo "🔍 Monitoreo del VPS - $(date)"
    echo "================================"

    local errors=0

    check_service "postgresql" || ((errors++))
    check_python_app || ((errors++))
    check_service "nginx" || true  # Nginx es opcional
    check_api || ((errors++))
    check_database || ((errors++))

    echo ""
    check_resources

    echo ""
    if [ $errors -eq 0 ]; then
        echo "✅ Todos los servicios están funcionando correctamente"
    else
        echo "❌ Se encontraron $errors problema(s)"
    fi

    echo "--------------------------------"
}

# Modo continuo
if [ "$1" = "--continuous" ] || [ "$1" = "-c" ]; then
    echo "Iniciando monitoreo continuo (Ctrl+C para detener)..."
    echo "Intervalo: 60 segundos"
    echo ""

    while true; do
        monitor
        sleep 60
    done
else
    # Monitoreo único
    monitor
fi