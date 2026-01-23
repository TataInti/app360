# App360 - Sistema de Gestión Empresarial

Un sistema completo de gestión empresarial desarrollado con Flask (backend) y React (frontend), diseñado para optimizar operaciones comerciales, de recursos humanos, inventario y más.

## 🚀 Características

- **Dashboard Ejecutivo**: Visión general del negocio con KPIs clave
- **Gestión de Productos**: Control de inventario y catálogo de productos
- **CRM**: Gestión de leads y clientes
- **Recursos Humanos**: Control de empleados, asistencia y objetivos
- **Compras**: Gestión de órdenes de compra y proveedores
- **Ventas**: Seguimiento de ventas y análisis
- **Autenticación**: Sistema de roles y permisos

## 🛠️ Tecnologías

### Backend
- **Python 3.12**
- **Flask 3.1.2** - Framework web
- **SQLAlchemy 2.0.45** - ORM para base de datos
- **PostgreSQL** - Base de datos principal
- **SQLite** - Para desarrollo local (opcional)
- **Werkzeug** - Utilidades de seguridad

### Frontend
- **React 19.2.0** - Framework UI
- **Vite 7.2.4** - Build tool
- **React Query** - Gestión de estado y caché
- **React Router** - Navegación

### Testing
- **pytest** - Tests backend
- **Vitest** - Tests frontend
- **Playwright** - Tests E2E
- **Bandit** - Análisis de seguridad

## 📋 Prerrequisitos

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+ (recomendado) o SQLite (para desarrollo rápido)

## 🚀 Instalación y Configuración

### Opción 1: Usando Docker (Recomendado)

```bash
# Clonar el repositorio
git clone <repository-url>
cd app360

# Crear archivo .env
cp .env.example .env
# Editar .env con tus configuraciones

# Ejecutar con Docker Compose
docker-compose up -d
```

### Opción 2: Instalación Local

#### 1. Instalar PostgreSQL

**macOS (con Homebrew):**
```bash
brew install postgresql
brew services start postgresql
createdb app360
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb app360
```

**Windows:**
Descargar e instalar desde: https://www.postgresql.org/download/windows/

#### 2. Configurar Backend

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Variables de entorno (crear .env)
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD=admin-password
DATABASE_URL=postgresql://app360:password@localhost:5432/app360

# Crear base de datos y ejecutar migraciones
python scripts/setup_database.py
```

### 3. Configurar Frontend

```bash
cd frontend
npm install

# Variables de entorno (crear .env)
VITE_API_BASE_URL=http://localhost:5000/api
```

### 4. Ejecutar la aplicación

```bash
# Backend (desde raíz del proyecto)
python app.py

# Frontend (desde directorio frontend)
npm run dev
```

La aplicación estará disponible en:
- Frontend: http://localhost:5173
- Backend API: http://localhost:5000

## 🧪 Testing

### Backend
```bash
# Tests unitarios
pytest

# Con cobertura
pytest --cov-report=term
```

### Frontend
```bash
cd frontend

# Tests unitarios
npm test

# Tests E2E
npx playwright test
```

### Seguridad
```bash
# Escaneo de seguridad
bandit -r .
```

## � Despliegue

### Despliegue Local

```bash
# Con Docker (recomendado)
docker-compose up -d

# O instalación manual
python scripts/setup_database.py
python app.py
```

### Despliegue en VPS

#### Configuración Inicial del VPS

1. **Conectar al VPS:**
   ```bash
   ssh root@72.61.47.19
   # Password: AccesoServerVirtual+7423
   ```

2. **Instalar dependencias:**
   ```bash
   # Actualizar sistema
   apt update && apt upgrade -y

   # Instalar Python y pip
   apt install python3 python3-pip python3-venv -y

   # Instalar PostgreSQL
   apt install postgresql postgresql-contrib -y

   # Instalar git
   apt install git -y

   # Instalar nginx (opcional para proxy reverso)
   apt install nginx -y
   ```

3. **Configurar PostgreSQL:**
   ```bash
   # Crear usuario y base de datos
   sudo -u postgres psql
   CREATE USER app360 WITH PASSWORD 'secure-password';
   CREATE DATABASE app360 OWNER app360;
   ALTER USER app360 CREATEDB;
   \q
   ```

4. **Clonar el repositorio:**
   ```bash
   mkdir -p /var/www
   cd /var/www
   git clone https://github.com/TataInti/app360.git
   cd app360
   ```

5. **Configurar la aplicación:**
   ```bash
   # Crear entorno virtual
   python3 -m venv venv
   source venv/bin/activate

   # Instalar dependencias
   pip install -r requirements.txt

   # Configurar variables de entorno
   cp .env.example .env
   # Editar .env con la configuración correcta
   nano .env
   ```

#### Despliegue Automático

```bash
# Desde tu máquina local
./scripts/deploy_to_vps.sh
```

#### Despliegue Manual

```bash
# Conectar al VPS
ssh root@72.61.47.19

# Navegar al proyecto
cd /var/www/app360

# Hacer pull de cambios
git pull origin main

# Instalar dependencias
source venv/bin/activate
pip install -r requirements.txt

# Configurar base de datos
python scripts/setup_database.py

# Iniciar aplicación
nohup python app.py > app.log 2>&1 &
```

#### Verificación del Despliegue

```bash
# Verificar que la aplicación está corriendo
curl http://localhost:5000/api/health

# Ver logs
tail -f /var/www/app360/app.log

# Ver procesos
ps aux | grep python
```

### Configuración de Nginx (Opcional)

Para servir la aplicación con Nginx como proxy reverso:

```bash
# Crear configuración de sitio
cat > /etc/nginx/sites-available/app360 << EOF
server {
    listen 80;
    server_name vyp.app360.com.ar;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Habilitar sitio
ln -s /etc/nginx/sites-available/app360 /etc/nginx/sites-enabled/

# Reiniciar Nginx
systemctl restart nginx
```
### Monitoreo y Mantenimiento

#### Verificación del Estado del Despliegue

```bash
# Verificación completa del despliegue
./scripts/check_deployment.sh
```

#### Monitoreo Continuo

```bash
# Monitoreo único
./scripts/monitor_vps.sh

# Monitoreo continuo (cada 60 segundos)
./scripts/monitor_vps.sh --continuous
```

#### Comandos Útiles para Mantenimiento

```bash
# Ver logs en tiempo real
ssh root@72.61.47.19 "tail -f /var/www/app360/app.log"

# Reiniciar servicios
ssh root@72.61.47.19 "systemctl restart postgresql"
ssh root@72.61.47.19 "pkill -f 'python app.py' && cd /var/www/app360 && source venv/bin/activate && nohup python app.py > app.log 2>&1 &"

# Backup de base de datos
ssh root@72.61.47.19 "pg_dump -U app360 app360 > backup_$(date +%Y%m%d_%H%M%S).sql"

# Verificar uso de disco
ssh root@72.61.47.19 "df -h"
```
#### Backup de Base de Datos

```bash
# Crear backup automático
./scripts/backup_database.sh

# Crear backup y descargarlo localmente
./scripts/backup_database.sh --download
```

Los backups se almacenan en el VPS en `/var/www/app360/backups/` y se mantienen los últimos 10 backups automáticamente.
## �📁 Estructura del Proyecto

```
app360/
├── api/                    # Endpoints REST API
├── api_rest.py            # API REST adicional
├── app.py                 # Aplicación Flask principal
├── blueprints/            # Blueprints Flask
│   ├── auth.py
│   ├── products.py
│   └── ...
├── config.py              # Configuración
├── models/                # Modelos de datos
│   ├── core/
│   ├── crm/
│   └── ...
├── services/              # Lógica de negocio
├── static/                # Archivos estáticos
├── templates/             # Plantillas HTML
├── tests/                 # Tests backend
├── frontend/              # Aplicación React
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   └── services/
│   ├── e2e/               # Tests E2E
│   └── ...
├── requirements.txt       # Dependencias Python
├── pyproject.toml         # Configuración Python
└── README.md
```

## 🔒 Seguridad

- Autenticación basada en sesiones
- Control de acceso por roles
- Validación de entrada
- Protección CSRF
- Headers de seguridad configurados

## 📊 API Documentation

### Autenticación
```http
POST /api/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password"
}
```

### Productos
```http
GET /api/products
GET /api/products/{id}
POST /api/products
PUT /api/products/{id}
DELETE /api/products/{id}
```

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 📞 Soporte

Para soporte técnico o preguntas:
- Email: support@app360.com
- Documentación: [Wiki del proyecto]

## 🔄 Migración a PostgreSQL

Si tienes datos existentes en SQLite y quieres migrar a PostgreSQL:

### Opción 1: Migración automática (Recomendado)
```bash
# Ejecutar script completo de migración
./scripts/migrate_to_postgres.sh
```

### Opción 2: Migración manual

#### 1. Configurar PostgreSQL
```bash
# Instalar PostgreSQL (ver sección de prerrequisitos)
createdb app360
```

#### 2. Actualizar configuración
Edita tu archivo `.env`:
```env
DATABASE_URL=postgresql://app360:password@localhost:5432/app360
```

#### 3. Crear tablas en PostgreSQL
```bash
python scripts/setup_database.py
```

#### 4. Migrar datos existentes
```bash
python scripts/migrate_to_postgres.py
```

#### 5. Verificar migración
```bash
python scripts/verify_migration.py
```