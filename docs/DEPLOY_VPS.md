# Deploy a VPS (GitHub -> VPS)

Este documento describe el flujo **recomendado** para actualizar App360 en el VPS desde el repositorio, manteniendo la política **Local First DB**.

Importante: en nuestro caso **la aplicación ya existe y ya corre en producción**. Por lo tanto, el flujo habitual es de **update** (pull + instalar deps + aplicar cambios versionados + restart), no un “bootstrap desde cero”.

## Checklist antes de pushear

1. Verificar que NO haya secretos ni archivos locales en git:

```bash
git status
```

- No debe aparecer `.env`, DBs locales (`instance/*.db`) ni dumps (`backups/db-sync/*.dump`).
- Notas de acceso al VPS deben vivir en `docs/_local/` (ignoradas) o en un archivo local ignorado.

2. Backend tests:

```bash
pytest
```

3. Frontend build (si se usa la SPA):

```bash
cd frontend
npm ci
npm run build
```

4. Push:

```bash
git push
```

## Preparación en VPS (una vez)

Si el VPS ya está instalado y corriendo, esta sección sirve como referencia para auditar configuración. No hace falta re-crear todo.

### 0) Acceso al VPS
- Acceso SSH con usuario root:
```
ssh root@72.61.47.19
```

### 1) Código

- Path esperado: `/var/www/app360`

```bash
sudo mkdir -p /var/www/app360
sudo chown -R www-data:www-data /var/www/app360
```

### 2) Archivo de entorno

Crear `/var/www/app360/.env` (NO se versiona). Usar `.env.example` como base.

- Recomendación: `LOCAL_DEV_BYPASS_AUTH=False` en VPS.

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

Lo único que puede tocar estructura de DB es si se habilita explícitamente:

- `RUN_MIGRATIONS=true` → corre Alembic (`flask db upgrade`).

Si seguimos Local First DB, normalmente dejamos `RUN_MIGRATIONS=false` y aplicamos releases SQL versionadas.

### Riesgos/consideraciones al correr `scripts/deploy.sh` en un VPS ya corriendo

- No genera duplicados en datos por sí solo, pero **sí puede cambiar el entorno** (dependencias Python). Para que el código nuevo se vea, igual hay que **reiniciar** Gunicorn.
- Si el proceso Gunicorn está usando el mismo `venv/`, instalar deps mientras corre normalmente no rompe el proceso activo, pero el cambio no se aplica hasta el restart. Aun así, conviene ejecutar deploy en una ventana controlada.
- Si se activa `RUN_MIGRATIONS=true` sin querer, ahí sí puede haber cambios de schema.

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

3) Base de datos (Local First DB)

- Generar release en local:

```bash
bash scripts/create_local_db_release.sh
```

- Aplicar release versionada en VPS:

```bash
bash scripts/apply_db_release_to_vps.sh <release_tag>
```

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

- `scripts/deploy.sh` corre un set de **tests seguros** contra SQLite temporal (`/tmp/app360_test.sqlite`) para no tocar PostgreSQL de producción.
- Si el frontend se sirve estático, asegurarse de copiar el build a la ruta configurada en Nginx (`/var/www/app360/frontend/dist`).

## Cron nocturno: sincronización PRE -> objetivos comerciales

Se agregó un endpoint dedicado para cron con token:

- `POST /sabiogo/api/sync-objetivos-pre-cron`
- Header requerido: `X-App360-Cron-Token: <token>`
- Env requerida en app: `SABIOGO_CRON_TOKEN=<mismo token>`

Script listo para producción:

```bash
bash scripts/sync_objetivos_pre_cron.sh
```

Variables soportadas por el script:

- `BASE_URL` (default: `http://127.0.0.1:5000`)
- `SABIOGO_CRON_TOKEN` (obligatoria)
- `PERIODO` (default: mes actual `YYYY-MM`)

Ejemplo de crontab (todos los días 02:10):

```bash
10 2 * * * cd /var/www/app360 && SABIOGO_CRON_TOKEN='TU_TOKEN' BASE_URL='http://127.0.0.1:5000' /usr/bin/bash scripts/sync_objetivos_pre_cron.sh >> /var/www/app360/logs/sync_objetivos_pre_cron.log 2>&1
```

## Caso real: VPS ya instalado y corriendo

Para actualizar una instalación existente, normalmente alcanza con:

```bash
cd /var/www/app360
sudo -u www-data git pull
sudo -u www-data bash scripts/deploy.sh

# si hay release DB versionada:
bash scripts/apply_db_release_to_vps.sh <release_tag>

sudo systemctl restart app360
curl -fsS http://127.0.0.1:5000/api/health
```

No debería haber “duplicados” por correr `scripts/deploy.sh`, porque el script no hace seed ni create_all.
