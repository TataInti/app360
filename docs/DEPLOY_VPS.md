# Deploy a VPS (GitHub -> VPS)

Este documento describe el flujo **recomendado** para actualizar App360 en el VPS desde el repositorio, manteniendo la política **Local First DB**.

Importante: en nuestro caso **la aplicación ya existe y ya corre en producción**. Por lo tanto, el flujo habitual es de **update** (pull + instalar deps + aplicar cambios versionados + restart), no un “bootstrap desde cero”.

## Checklist antes de pushear

1. Verificar que NO haya secretos ni archivos locales en git:

```bash
git status
```

- No debe aparecer `.env`, DBs locales (`instance/*.db`) ni dumps (`backups/db-sync/*.dump`).
- Los dumps operativos deben vivir fuera del repo. Default actual para sync local: `$HOME/.app360/backups/db-sync/`.
- `backups/db-releases/` es histórico. No agregar dumps productivos nuevos al repositorio.
- Notas de acceso al VPS deben vivir en `docs/_local/` (ignoradas) o en un archivo local ignorado.

2. Backend tests:

```bash
pytest
```

3. Push:

```bash
git push
```

## Preparación en VPS (una vez)

Si el VPS ya está instalado y corriendo, esta sección sirve como referencia para auditar configuración. No hace falta re-crear todo.

### 0) Acceso al VPS
- Acceso SSH con usuario root:
```
ssh root@<VPS_IP>
```

Los accesos concretos del entorno deben mantenerse fuera del repositorio versionado.

### 1) Código

- Path esperado: `/var/www/app360`
- Backups operativos en VPS: `/var/backups/app360`

```bash
sudo mkdir -p /var/www/app360
sudo chown -R www-data:www-data /var/www/app360
```

### 2) Archivo de entorno

Crear `/var/www/app360/.env` manualmente (NO se versiona).

- No habilitar bypasses de desarrollo en VPS.

### 3) systemd (Gunicorn)

- Unit de referencia: `scripts/app360.service`

```bash
sudo cp scripts/app360.service /etc/systemd/system/app360.service
sudo systemctl daemon-reload
sudo systemctl enable app360
```

### 4) Nginx

- Config de referencia: `scripts/nginx-app360.conf`

```bash
sudo cp scripts/nginx-app360.conf /etc/nginx/sites-available/app360
sudo ln -sf /etc/nginx/sites-available/app360 /etc/nginx/sites-enabled/app360
sudo nginx -t
sudo systemctl reload nginx
```

## Deploy (cada actualización)

### Qué hace `scripts/deploy.sh` (y qué NO hace)

`scripts/deploy.sh` está pensado para ser **idempotente** en un VPS existente:

- Crea el `venv/` **solo si no existe**.
- Instala/actualiza dependencias con `pip install -r requirements.txt`.
- Verifica que exista `.env` y que tenga variables críticas.
- Crea directorios `logs/` e `instance/` si faltan.
- Verifica conexión a la DB configurada en `.env` (abre conexión y cierra).
- **No** ejecuta `db.create_all()`.
- **No** inserta datos ni “seed” (no debería generar duplicados de registros).
- **No** reinicia systemd por sí mismo.

`RUN_MIGRATIONS=true` está bloqueado. La estructura de DB solo se modifica con
`scripts/migrate_db_safely.sh`, que exige backup, restore de ensayo y revisiones
Alembic explícitas.

### Riesgos/consideraciones al correr `scripts/deploy.sh` en un VPS ya corriendo

- No genera duplicados en datos por sí solo, pero **sí puede cambiar el entorno** (dependencias Python). Para que el código nuevo se vea, igual hay que **reiniciar** Gunicorn.
- Si el proceso Gunicorn está usando el mismo `venv/`, instalar deps mientras corre normalmente no rompe el proceso activo, pero el cambio no se aplica hasta el restart. Aun así, conviene ejecutar deploy en una ventana controlada.
- Si se activa `RUN_MIGRATIONS=true`, el deploy aborta sin cambiar el esquema.

### Update standard (recomendado)

1) Pull:

```bash
cd /var/www/app360
sudo -u www-data git pull
```

2) Ejecutar deploy script (instala deps + checks; no toca datos):

```bash
cd /var/www/app360
sudo -u www-data bash scripts/deploy.sh
```

3) Base de datos (forward-only)

Desde el checkout local que contiene el mismo commit ya descargado en el VPS:

```bash
EXPECTED_GIT_SHA=<sha_completo> \
PROD_SSH_HOST=<host> \
MAINTENANCE_CONFIRMED=true \
bash scripts/apply_db_migrations_to_vps.sh \
  20260729_ensure_efectivo_iva \
  20261021_comercial_cliente_criterio \
  scripts/sql/validate_20261021_comercial_cliente_criterio.sql
```

Para esta release, Alembic aplicará cuatro revisiones comerciales consecutivas:
`20261020_comercial_vendedores`, `20261020_comercial_objetivos`,
`20261020_objetivo_vinculos` y `20261021_comercial_cliente_criterio`. La
validación SQL anterior comprueba las tablas e índice esperados y reporta sus
recuentos junto con los de las tablas legadas `goals` y `movimientos_caja`.

Antes de ejecutarlo se deben pausar las escrituras y declarar
`MAINTENANCE_CONFIRMED=true`. El comando crea el backup en
`/var/backups/app360`, ensaya una restauración, aplica Alembic y valida Resultado
comercial. No reinicia el servicio.

4) Restart servicio (aplica el código nuevo):

```bash
sudo systemctl restart app360
sudo systemctl status app360 --no-pager
```

5) Smoke check:

```bash
curl -fsS http://127.0.0.1:5000/api/health
```

## Notas

- `scripts/deploy.sh` corre un set de **tests seguros** contra SQLite temporal (`/tmp/app360_test.sqlite`) para no tocar PostgreSQL de producción. Antes de correr pytest, el script inicializa el esquema completo con `db.create_all()` sobre ese mismo archivo SQLite, para que los tests que asumen una DB ya migrada (equivalente a Postgres) no fallen con `no such table: ...` (falso positivo detectado en despliegues reales).
- `scripts/deploy.sh` ejecuta cada archivo `tests/test_*.py` en un **proceso pytest separado** (no un único `pytest tests/`). Motivo: algunos fixtures `app` mutan atributos de clase en `Config` (p.ej. `Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"`) sin revertirlos al terminar el test. Como `Config` es un singleton importado una sola vez por proceso, esa mutación queda "pegada" para el resto de los archivos que corran después en el mismo proceso de pytest, provocando fallos `no such table` en archivos que en realidad están bien (otro falso positivo detectado en despliegues reales, distinto del anterior). Correr un proceso por archivo evita el acoplamiento sin tener que tocar cada test.
- Convención para nuevos archivos de test que usan la base de datos: preferir un fixture `app` autocontenido que fuerce `SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"` y llame a `db.create_all()`/`db.session.remove()`/`db.drop_all()` (ver `tests/test_rrhh_fichadas.py`, `tests/test_dashboards_v2.py`, `tests/test_sabiogo_service.py`). Si un test necesita depender del `DATABASE_URL` del entorno (por ejemplo para correr contra Postgres real en desarrollo local), el bootstrap de `scripts/deploy.sh` ya cubre el caso del SQLite temporal, pero no reemplaza migraciones reales si el modelo cambia de forma incompatible con SQLite.
- Este repositorio no incluye actualmente un frontend estatico separado. Si se vuelve a desplegar uno, documentar en el mismo cambio la ruta de build y copia asociada en Nginx.
- Los backups operativos del VPS no deben quedar dentro de `/var/www/app360`; usar `/var/backups/app360/...`.
- `create_local_db_release.sh` y `apply_db_release_to_vps.sh` están bloqueados
  para impedir restauraciones completas accidentales.
- `scripts/sync_prod_db_to_local.sh` guarda por default sus dumps temporales en `$HOME/.app360/backups/db-sync/` salvo override con `BACKUP_DIR`.

## Objetivos comerciales

El realizado de cada línea se calcula desde PRE al consultar. La carga y finalización de staging refrescan los datos de ventas y facts; el avance comercial no se copia a `Goal.current_value` ni requiere una sincronización de objetivos.

## Caso real: VPS ya instalado y corriendo

Para actualizar una instalación existente, normalmente alcanza con:

```bash
cd /var/www/app360
sudo -u www-data git pull

sudo -u www-data bash scripts/deploy.sh

# desde la maquina operadora, antes del restart:
EXPECTED_GIT_SHA=<sha_completo> \
PROD_SSH_HOST=<host> \
MAINTENANCE_CONFIRMED=true \
bash scripts/apply_db_migrations_to_vps.sh \
  20260729_ensure_efectivo_iva \
  20261029_objetivos_comerciales_lineas \
  scripts/sql/validate_20261029_objetivos_comerciales_lineas.sql

sudo systemctl restart app360
curl -fsS http://127.0.0.1:5000/api/health
```

La migración debe aplicarse antes de reiniciar el servicio con el código nuevo.
Si falla, detener el despliegue y mantener la versión anterior activa.

No debería haber “duplicados” por correr `scripts/deploy.sh`, porque el script no hace seed ni create_all.
