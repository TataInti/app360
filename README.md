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

## 📁 Estructura del Proyecto

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