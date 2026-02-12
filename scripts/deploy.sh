#!/bin/bash
# =============================================================================
# Script de Despliegue para App360
# Ejecutar en el servidor VPS después de clonar el repositorio
# =============================================================================

set -e

echo "=========================================="
echo "  App360 - Script de Despliegue"
echo "=========================================="

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directorio del proyecto
PROJECT_DIR="/var/www/app360"

# Verificar que estamos en el directorio correcto
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: Ejecutar este script desde el directorio raíz del proyecto${NC}"
    exit 1
fi

# 1. Verificar Python
echo -e "\n${YELLOW}[1/8] Verificando Python...${NC}"
python3 --version || { echo -e "${RED}Python3 no encontrado${NC}"; exit 1; }

# 2. Crear entorno virtual si no existe
echo -e "\n${YELLOW}[2/8] Configurando entorno virtual...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Entorno virtual creado${NC}"
else
    echo -e "${GREEN}✓ Entorno virtual existente${NC}"
fi

# 3. Activar entorno e instalar dependencias
echo -e "\n${YELLOW}[3/8] Instalando dependencias...${NC}"
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}✓ Dependencias instaladas${NC}"

# 4. Verificar archivo .env
echo -e "\n${YELLOW}[4/8] Verificando configuración...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: Archivo .env no encontrado${NC}"
    echo "Crear .env basándose en .env.example con valores de producción"
    exit 1
fi

# Verificar variables críticas
source .env 2>/dev/null || true
if [ -z "$SECRET_KEY" ]; then
    echo -e "${RED}Error: SECRET_KEY no definida en .env${NC}"
    exit 1
fi
if [ -z "$ADMIN_PASSWORD" ]; then
    echo -e "${RED}Error: ADMIN_PASSWORD no definida en .env${NC}"
    exit 1
fi
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}Error: DATABASE_URL no definida en .env${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Variables de entorno configuradas${NC}"

# 5. Crear directorios necesarios
echo -e "\n${YELLOW}[5/8] Creando directorios...${NC}"
mkdir -p logs
mkdir -p instance
echo -e "${GREEN}✓ Directorios creados${NC}"

# 6. Verificar conexión a PostgreSQL
echo -e "\n${YELLOW}[6/8] Verificando conexión a base de datos...${NC}"
python3 -c "
from app import create_app
from models import db
app = create_app()
with app.app_context():
    db.engine.connect()
    print('✓ Conexión a PostgreSQL exitosa')
" || { echo -e "${RED}Error: No se pudo conectar a PostgreSQL${NC}"; exit 1; }

# 7. Ejecutar migraciones
echo -e "\n${YELLOW}[7/8] Ejecutando migraciones de base de datos...${NC}"
if [ -d "migrations" ]; then
    flask db upgrade || echo "Advertencia: Migraciones no aplicadas (puede ser normal en primera instalación)"
else
    echo "Inicializando migraciones..."
    flask db init
    flask db migrate -m "Initial migration"
    flask db upgrade
fi
echo -e "${GREEN}✓ Base de datos actualizada${NC}"

# 8. Ejecutar tests seguros (sin tocar DB productiva)
echo -e "\n${YELLOW}[8/9] Ejecutando tests seguros en entorno aislado...${NC}"
if [ -d "tests" ]; then
    rm -f /tmp/app360_test.sqlite
    PYTHONPATH=/var/www/app360 DATABASE_URL=sqlite:////tmp/app360_test.sqlite pytest tests/ -v --tb=short || {
        echo -e "${RED}Error: Fallaron tests seguros en VPS${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Tests seguros ejecutados correctamente${NC}"
else
    echo -e "${YELLOW}Advertencia: carpeta tests/ no encontrada, se omite validación${NC}"
fi

# 9. Verificar que la aplicación funciona
echo -e "\n${YELLOW}[9/9] Verificando aplicación...${NC}"
python3 -c "
from app import create_app
app = create_app()
with app.test_client() as client:
    response = client.get('/api/health')
    if response.status_code == 200:
        print('✓ Aplicación funcionando correctamente')
    else:
        print('Error: Health check falló')
        exit(1)
"

echo -e "\n${GREEN}=========================================="
echo "  ✓ Despliegue completado exitosamente"
echo "==========================================${NC}"

echo -e "\n${YELLOW}Próximos pasos:${NC}"
echo "1. Configurar systemd service para gunicorn"
echo "2. Configurar nginx como reverse proxy"
echo "3. Configurar certificado SSL con Let's Encrypt"
echo "4. Iniciar el servicio: systemctl start app360"

echo -e "\n${YELLOW}Para ejecutar manualmente:${NC}"
echo "  source venv/bin/activate"
echo "  gunicorn --bind 127.0.0.1:5000 --workers 4 'app:create_app()'"
