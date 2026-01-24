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

### Despliegue Local

#### Configuración Inicial

1. **Instalar dependencias:**
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

5. **Configurar variables de entorno para producción:**
   ```bash
   # Copiar configuración de producción
   cp .env.production.example .env
   
   # Editar .env con configuración específica del servidor
   nano .env
   
   # Variables críticas para producción:
   # - SERVER_NAME=vyp.app360.com.ar
   # - PREFERRED_URL_SCHEME=https
   # - SESSION_COOKIE_SECURE=True
   # - REMEMBER_COOKIE_SECURE=True
   # - DATABASE_URL=postgresql://app360user:app360_secure@localhost:5432/app360
   ```

### Configuración de Nginx con SSL

#### Despliegue Manual

```bash
# Navegar al proyecto
cd /path/to/app360

# Configurar entorno local
cp .env.example .env
# Editar .env con credenciales locales
nano .env

# Instalar dependencias
source venv/bin/activate
pip install -r requirements.txt

# Configurar base de datos (primera vez)
python scripts/setup_comercial.py

# Reiniciar aplicación
pkill -f 'gunicorn'
cd /var/www/app360 && source venv/bin/activate && gunicorn --config gunicorn.conf.py app:create_app --daemon
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

### Configuración de Nginx con SSL

Para servir la aplicación con Nginx como proxy reverso con HTTPS:

```bash
# Instalar certbot para Let's Encrypt
apt install snapd -y
snap install core; snap refresh core
snap install --classic certbot
ln -s /snap/bin/certbot /usr/bin/certbot

# Crear configuración de sitio
cat > /etc/nginx/sites-available/app360 << 'EOF'
# HTTP redirect a HTTPS
server {
    listen 80;
    server_name vyp.app360.com.ar;
    
    # Directorio para Let's Encrypt challenges
    location /.well-known/acme-challenge/ {
        root /var/www/app360;
        try_files $uri =404;
    }
    
    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name vyp.app360.com.ar;
    
    # Certificado SSL (se configurará después de obtenerlo)
    ssl_certificate /etc/letsencrypt/live/vyp.app360.com.ar/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vyp.app360.com.ar/privkey.pem;
    
    # Configuración SSL
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Headers de seguridad
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Proxy a Gunicorn (puerto 8000)
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Static files
    location /static/ {
        alias /var/www/app360/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Habilitar sitio
ln -sf /etc/nginx/sites-available/app360 /etc/nginx/sites-enabled/

# Probar configuración
nginx -t

# Reiniciar Nginx
systemctl reload nginx

# Obtener certificado SSL
certbot certonly --webroot -w /var/www/app360 -d vyp.app360.com.ar --agree-tos --email admin@vyp.app360.com.ar --non-interactive

# Configurar renovación automática
crontab -l | { cat; echo "0 12 * * * /usr/bin/certbot renew --quiet"; } | crontab -
```
### Monitoreo y Mantenimiento

#### Verificación del Estado del Despliegue

Para verificar el estado local, puedes usar comandos como:

```bash
# Verificar si la aplicación está corriendo
ps aux | grep gunicorn

# Verificar la base de datos
# (depende de tu configuración local)
```

#### Monitoreo Continuo

Para monitoreo local, usa herramientas del sistema como `top`, `htop`, etc.

#### Comandos Útiles para Mantenimiento

```bash
# Ver logs en tiempo real
tail -f logs/gunicorn.log

# Reiniciar servicios
# Reinicia PostgreSQL si es necesario (depende de tu configuración local)
# pkill -f 'gunicorn' && source venv/bin/activate && gunicorn --config gunicorn.conf.py app:create_app --daemon

# Backup de base de datos
# Usa pg_dump localmente
pg_dump -U app360 app360 > backup_$(date +%Y%m%d_%H%M%S).sql

# Verificar uso de disco
df -h
```
#### Backup de Base de Datos

```bash
# Crear backup local
pg_dump -U app360 app360 > backup_$(date +%Y%m%d_%H%M%S).sql
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