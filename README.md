# App360 - Sistema de Gestion Empresarial

App360 es una plataforma integral de gestion desarrollada con Flask y Jinja2. Unifica operacion comercial, RRHH, compras, ventas y finanzas en un solo panel con roles y permisos. Esta pensada para operar en produccion con PostgreSQL y para pruebas con SQLite.

Documento oficial de desarrollo:

- `docs/MANUAL_DEVELOPER.md`

## Prioridad Operativa (Local First)

Desde 2026-02-12, la prioridad del proyecto es:

- Trabajar y validar primero en local.
- Versionar en GitHub todos los cambios de DB como migraciones Alembic.
- Replicar en VPS solo desde cambios versionados.

Documento oficial de trabajo:

- `docs/PRIORIDAD_LOCAL_FIRST_DB.md`

Scripts operativos:

- `scripts/migrate_db_safely.sh`: backup, restore de ensayo y migración forward-only.
- `scripts/apply_db_migrations_to_vps.sh`: invocación remota con revisiones y commit explícitos.

## Deploy a VPS (GitHub -> VPS)

Guía completa y checklist pre-push/post-pull:

- `docs/DEPLOY_VPS.md`

Nota: `scripts/deploy.sh` no modifica el esquema. `RUN_MIGRATIONS=true` está bloqueado; las migraciones productivas pasan exclusivamente por el ejecutor seguro.

### Archivos locales (no versionar)

El repo está configurado para ignorar:

- `.env` (secrets)
- `instance/*.db` / `*.sqlite*` (DBs locales)
- `logs/*.log` (logs locales)
- dumps temporales fuera del repo (default actual: `$HOME/.app360/backups/db-sync/`)
- `docs/_local/*` (notas locales, accesos, etc.)

Nota: `backups/db-releases/` conserva únicamente releases históricas. Los backups nuevos viven fuera del repositorio.

Tip: si necesitás guardar accesos/credenciales del VPS, guardalos en `docs/_local/` (no se pushea).

## Caracteristicas Principales

- Dashboard ejecutivo y BI con resultado de gestión compartido.
- Inventario y productos con ubicaciones.
- CRM con leads, clientes y campañas.
- RRHH: empleados, asistencia, adelantos y liquidaciones.
- Compras y proveedores.
- Tesoreria: movimientos con conceptos estructurales, arqueos y cuenta corriente.
- Gastos/egresos y reportes exportables a Excel.
- Autenticacion por roles y control de acceso.

## Modulos Destacados

- RRHH
    - Empleados: altas/edicion desde administracion.
    - Asistencia, ausentismo y llegadas tarde por empleado.
    - Adelantos y prestamos, con flujo de aprobacion.
    - Liquidacion mensual de sueldos.
- Tesoreria
    - Arqueos de caja y movimientos clasificados por concepto.
    - Exportacion de movimientos y arqueos a Excel.
    - Cuenta corriente con proveedor Friar y pagos.
- Gastos
    - Registro de egresos por concepto y proveedor.
    - KPIs de gastos y exportacion a Excel.

## Tecnologias

- Backend
    - Python 3.12
    - Flask 3.1.2
    - SQLAlchemy 2.0
    - PostgreSQL (prod) / SQLite (dev)
- Frontend
    - Jinja2 (templates server-rendered)
    - Bootstrap / CSS
    - JavaScript (fetch API para dashboards)

## Integracion con SabioGo

- SabioGo sigue siendo el facturador legal; App360 funciona como soporte para decision de direccion y necesita nutrirse de sus datos de ventas y costos.
- La integracion principal es una tarea Windows que consulta Firebird y envia ventas/compras por HTTPS a App360. La carga manual/batch queda como contingencia.
- En PostgreSQL se cargan primero a staging (`stg_sabiogo_ventas` y `stg_sabiogo_compras`) con metadatos de import antes de finalizar facts, objetivos PRE y dashboards.
- El resultado comercial compartido se calcula como: facturacion sin PRE - compras + ingresos incluidos - egresos incluidos.
- Contrato tecnico completo: `docs/SABIOGO_SYNC_API.md`.

## Requisitos

- Python 3.12+
- PostgreSQL 15+ (recomendado)

## Instalacion Rapida (Local)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Variables minimas en `.env` (copiá `.env.example` como base y reemplazá cada `<...>`):

```env
SECRET_KEY=<generá-con-openssl-rand-hex-32>
ADMIN_PASSWORD=<clave-inicial-del-admin>
DATABASE_URL=postgresql://app360:<clave-de-la-base>@localhost:5432/app360
```

`scripts/dev_backend.sh` no lee el `.env`: antes de ejecutarlo cargalo en la shell con `set -a; . ./.env; set +a`. La clave del rol local `app360` (solo si el script lo crea) sale de `APP360_DB_PASSWORD`, que debe coincidir con la de `DATABASE_URL`.

Ejecutar backend (1 comando, incluye: arrancar PostgreSQL local + crear DB/usuario si faltan + crear tablas):

```bash
bash scripts/dev_backend.sh
```

## Docker (Opcional)

```bash
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
├── api.py                 # Endpoints API dashboards
├── api_rest.py            # API REST/JWT
├── app.py                 # Aplicacion Flask principal
├── blueprints/            # Blueprints Flask
├── config.py              # Configuracion
├── models/                # Modelos de datos
├── services/              # Logica de negocio
├── static/                # Archivos estaticos
├── templates/             # Plantillas Jinja2
├── tests/                 # Tests backend
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

## Migraciones de base de datos (GitHub -> VPS)

Los dumps completos están deshabilitados. Para una migración productiva:

```bash
EXPECTED_GIT_SHA=<sha_completo> \
PROD_SSH_HOST=<host> \
MAINTENANCE_CONFIRMED=true \
bash scripts/apply_db_migrations_to_vps.sh \
  <revision_actual> \
  <revision_objetivo> \
  <sql_de_validacion>
```

El flujo comprueba el commit, exige una única cabecera Alembic, crea un backup,
ensaya su restauración, aplica únicamente las revisiones forward y conserva un
manifiesto operativo. No reinicia la aplicación.

### Test seguro en VPS (post-deploy)

Para validar en servidor sin tocar la base de datos productiva:

```bash
cd /var/www/app360
source venv/bin/activate
rm -f /tmp/app360_test.sqlite
PYTHONPATH=/var/www/app360 DATABASE_URL=sqlite:////tmp/app360_test.sqlite pytest tests/ -v --tb=short
```

Este comando corre tests contra SQLite temporal (`/tmp/app360_test.sqlite`) y evita impacto en PostgreSQL de producción.

## Migracion a PostgreSQL

```bash
./scripts/migrate_to_postgres.sh
```

## Soporte

- Email: soporte@app360.com
