# App360 - Sistema de Gestion Empresarial

App360 es una plataforma integral de gestion desarrollada con Flask (backend) y React (frontend). Unifica operacion comercial, RRHH, compras, ventas y finanzas en un solo panel con roles y permisos. Esta pensada para operar en produccion con PostgreSQL y para pruebas con SQLite.

## Caracteristicas Principales

- Dashboard ejecutivo con KPIs clave.
- Inventario y productos con ubicaciones.
- CRM con leads, clientes y campañas.
- RRHH: empleados, asistencia, adelantos y liquidaciones.
- Compras y proveedores.
- Tesoreria: movimientos, arqueos y cuenta corriente.
- Gastos y reportes exportables a Excel.
- Autenticacion por roles y control de acceso.

## Modulos Destacados

- RRHH
    - Empleados: altas/edicion desde administracion.
    - Asistencia, ausentismo y llegadas tarde por empleado.
    - Adelantos y prestamos, con flujo de aprobacion.
    - Liquidacion mensual de sueldos.
- Tesoreria
    - Arqueos de caja y movimientos con destino.
    - Exportacion de movimientos y arqueos a Excel.
    - Cuenta corriente con proveedor Friar y pagos.
- Gastos
    - Registro de gastos por categoria y proveedor.
    - KPIs de gastos y exportacion a Excel.

## Tecnologias

- Backend
    - Python 3.12
    - Flask 3.1.2
    - SQLAlchemy 2.0
    - PostgreSQL (prod) / SQLite (dev)
- Frontend
    - React 19
    - Vite 7
    - React Query
    - React Router

## Integracion con SabioGo

- SabioGo sigue siendo el facturador legal; App360 funciona como soporte para decision de direccion y necesita nutrirse de sus datos de ventas y costos.
- Importamos diariamente dos archivos XLS generados desde SabioGo: `ventas_globales.xls` (ventas) y `compras_globales.xls` (costos). Se pueden cargar de forma manual por UI o por proceso programado/cron.
- Ambos archivos traen 28 columnas: RUBRO, FECHA, SUBRUBRO, CODIGO, MODELO, PRODUCTO, MARCA, COMPROBANTE, NRO_COMPROB, CLIENTE, CONDICION_IVA, VENDEDOR, DEPOSITO, UNINEGOCIO, FORMA_PAGO, KILOS, CAJAS, DTOS, NETO, LOCALIDAD, ZONA, SUCURSAL, IVA, MONIVA, TIPO, SUBTOT, NUMLISPRE, LISPREC.
- En PostgreSQL se cargan primero a tablas de staging (`stg_sabiogo_ventas` y `stg_sabiogo_compras`) con metadatos de import (archivo, fecha_import, hash, estado) antes de procesarlas hacia tablas de negocio y KPIs de rentabilidad/margen por linea de producto y canal.
- Tesoreria es el modulo con mas carga manual de usuarios; se complementa con los movimientos financieros y costos/ventas importados desde SabioGo para mantener consistencia diaria.

## Requisitos

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+ (recomendado)

## Instalacion Rapida (Local)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Variables minimas en `.env`:

```env
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD=admin-password
DATABASE_URL=postgresql://app360:password@localhost:5432/app360
```

Inicializar base y migraciones:

```bash
python scripts/setup_database.py
```

Ejecutar backend:

```bash
python app.py
```

## Frontend

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://localhost:5000/api" > .env
npm run dev
```

## Docker (Opcional)

```bash
cp .env.example .env
docker-compose up -d
```

## Exportaciones a Excel

Las exportaciones usan `pandas` y `openpyxl`. Si el boton de exportar abre un error, revisar dependencias del entorno:

```bash
pip install -r requirements.txt
```

## Estructura del Proyecto

```
app360/
├── api/                    # Endpoints REST API
├── api_rest.py            # API REST adicional
├── app.py                 # Aplicacion Flask principal
├── blueprints/            # Blueprints Flask
├── config.py              # Configuracion
├── models/                # Modelos de datos
├── services/              # Logica de negocio
├── static/                # Archivos estaticos
├── templates/             # Plantillas HTML
├── tests/                 # Tests backend
├── frontend/              # App React
└── requirements.txt       # Dependencias Python
```

## Seguridad

- Autenticacion basada en sesiones.
- Control de acceso por roles.
- CSRF habilitado.
- Headers de seguridad via Flask/Werkzeug.

## Testing

```bash
pytest
```

### Test seguro en VPS (post-deploy)

Para validar en servidor sin tocar la base de datos productiva:

```bash
cd /var/www/app360
source venv/bin/activate
rm -f /tmp/app360_test.sqlite
PYTHONPATH=/var/www/app360 DATABASE_URL=sqlite:////tmp/app360_test.sqlite pytest tests/ -v --tb=short
```

Este comando corre tests contra SQLite temporal (`/tmp/app360_test.sqlite`) y evita impacto en PostgreSQL de producción.

```bash
cd frontend
npm test
```

## Migracion a PostgreSQL

```bash
./scripts/migrate_to_postgres.sh
```

## Soporte

- Email: support@app360.com