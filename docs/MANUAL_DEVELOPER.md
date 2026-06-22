# Manual de Developer — App360

Última actualización: 2026-04-02
Estado: Activo

---

## 1) Propósito del documento

Este manual concentra la operación técnica de App360 para desarrollo, mantenimiento, despliegue y recuperación.

Objetivos:
- Reducir dependencia de conocimiento tácito.
- Estandarizar cómo trabajar localmente y cómo promover cambios a VPS.
- Mantener trazabilidad de cambios de código y base de datos.
- Asegurar recuperabilidad desde GitHub + releases de DB.

Documentos relacionados:
- `README.md`
- `docs/PRIORIDAD_LOCAL_FIRST_DB.md`
- `docs/DEPLOY_VPS.md`

---

## 2) Resumen de arquitectura

### 2.1 Componentes principales

- **Backend**: Flask monolítico modular (Blueprints), SQLAlchemy, Alembic.
- **Frontend**: Jinja2 templates server-rendered con JavaScript (fetch API para dashboards).
- **DB**:
  - Local: PostgreSQL recomendado (SQLite para tests/escenarios puntuales).
  - VPS: PostgreSQL.
- **Servidor app (VPS)**: Gunicorn + systemd.
- **Reverse proxy**: Nginx.

### 2.2 Entry points

- Backend app factory: `app.py` → `create_app()`
- API principal: `api.py`
- API REST/JWT complementaria: `api_rest.py`

### 2.3 Inicialización en backend (alto nivel)

`create_app()` realiza:
1. Carga de configuración (`Config`) y logging JSON.
2. Validación de variables críticas (`SECRET_KEY`, `ADMIN_PASSWORD`).
3. Inicialización de extensiones (limiter, csrf, db, migrate).
4. Registro de blueprints funcionales.
5. Configuración de headers de seguridad.
6. Handlers globales de errores.

---

## 3) Estructura del repositorio y responsabilidades

### 3.1 Núcleo de aplicación

- `app.py`: app factory, middlewares, registro de blueprints, error handlers.
- `config.py`: settings por entorno y seguridad de sesión/cookies.
- `extensions.py`: inicialización de extensiones Flask.
- `security.py`: control de acceso por rol/módulo, JWT decorators y auditoría de eventos.
- `exceptions.py`: excepciones de dominio/API.

### 3.2 Backend funcional

- `blueprints/`: rutas web y APIs por módulo de negocio.
- `models/`: entidades SQLAlchemy (core, crm, hr, purchases, sales, sabiogo, etc.).
- `services/`: lógica de negocio y orquestación.
- `repositories/`: consultas y agregaciones de acceso a datos.
- `dtos/`: objetos de transferencia para respuestas estructuradas.

### 3.3 Persistencia y migraciones

- `migrations/`: Alembic (`env.py` + `versions/`).
- `alembic.ini`: configuración de migraciones.
- `scripts/create_local_db_release.sh`: genera release SQL versionada.
- `scripts/apply_db_release_to_vps.sh`: aplica release en VPS validando SHA256.

### 3.4 Operación / Infra

- `scripts/deploy.sh`: update idempotente de runtime en VPS.
- `scripts/app360.service`: servicio systemd de Gunicorn.
- `scripts/nginx-app360.conf`: reverse proxy.
- `docker-compose.yml`, `Dockerfile`: ejecución containerizada opcional.

### 3.5 Documentación

- `README.md`: guía de uso e instalación.
- `docs/DEPLOY_VPS.md`: proceso de deploy update.
- `docs/PRIORIDAD_LOCAL_FIRST_DB.md`: política DB vigente.
- `docs/_local/`: notas no versionadas (accesos/operación local sensible).

---

## 4) Accesos, autenticación y autorización

### 4.1 Mecanismos de autenticación

- **Sesión Flask** para vistas server-rendered.
- **JWT** para endpoints API (`jwt_required`, `jwt_optional` en `security.py`).

### 4.2 Autorización por módulos

El control de permisos usa:
- `ACCESS_MAP` (rol → módulos permitidos)
- `module_allowed(...)`
- `protect_blueprint(...)`
- `require_module(...)`

Roles con acceso total: `admin`, `manager`, `gerente`.

Notas de permisos:
- El rol `caja` incluye `gastos` para visualizar conceptos/categorías en tesorería.
- El módulo de gastos usa `protect_blueprint(..., "gastos")` para respetar permisos de `gastos`.

### 4.3 Seguridad operativa

- Eventos de seguridad se registran en `logs/security.log`.
- Headers de hardening se agregan en `after_request` (CSP, HSTS según esquema, X-Frame-Options, etc.).
- En VPS se recomienda `LOCAL_DEV_BYPASS_AUTH=False`.

---

## 5) Entornos y configuración

### 5.1 Variables mínimas obligatorias

En `.env`:
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `DATABASE_URL`

Variables relevantes adicionales:
- `FLASK_ENV`, `DEBUG`
- `CORS_ORIGINS`
- `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRES`, `JWT_REFRESH_TOKEN_EXPIRES`
- `WTF_CSRF_ENABLED`
- `RATELIMIT_ENABLED`, `RATELIMIT_DEFAULT`
- `LOG_LEVEL`, `LOG_FILE`, `SECURITY_LOG_FILE`
- `LOCAL_DEV_BYPASS_AUTH`

Plantillas:
- `.env.example`
- `.env.production.example`

### 5.2 Política de secretos

- Nunca commitear `.env`, llaves o credenciales.
- Información local sensible debe ir en `docs/_local/` o archivos ignorados.

---

## 6) Flujo de trabajo de desarrollo

### 6.1 Setup local recomendado

**Requisitos de sistema (macOS vía Homebrew):**

```bash
# Node.js 22 (keg-only: requiere agregar al PATH)
brew install node@22
echo 'export PATH="/opt/homebrew/opt/node@22/bin:$PATH"' >> ~/.zshrc

# PostgreSQL 14 (keg-only: requiere agregar al PATH)
brew install postgresql@14
echo 'export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"' >> ~/.zshrc
brew services start postgresql@14
```

Backend:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
# Editar .env: generar SECRET_KEY con `openssl rand -base64 32`
bash scripts/dev_backend.sh
```

Interfaz local:

```bash
open http://127.0.0.1:5001
```

Este checkout no incluye una app React/Vite separada. La validacion visual local se hace sobre las plantillas Flask/Jinja servidas por el backend.

### 6.2 Validación previa a push

```bash
PYTHONPATH=$PWD pytest
git status
```

No deben aparecer archivos locales/sensibles en staging.

---

## 7) Política de base de datos (Local First)

Fuente oficial: `docs/PRIORIDAD_LOCAL_FIRST_DB.md`

Reglas operativas:
1. Cambio DB primero en local.
2. Todo cambio DB pasa por GitHub (migración + release SQL versionada).
3. No aplicar cambios ad-hoc en VPS por fuera del flujo.

### 7.1 Release de DB

Generar release local:

```bash
bash scripts/create_local_db_release.sh
```

Salida esperada:
- `backups/db-releases/<release_tag>/db.sql`
- `backups/db-releases/<release_tag>/db.sql.sha256`
- `backups/db-releases/<release_tag>/release_meta.txt`

Notas:
- `backups/db-releases/` sigue dentro del repo porque es una release versionada y auditable en Git.
- Los backups operativos/temporales deben vivir fuera del repo.

Aplicar en VPS:

```bash
bash scripts/apply_db_release_to_vps.sh <release_tag>
```

El script valida hash SHA256 antes de aplicar.

### 7.2 Sync de productiva a local (uso controlado)

```bash
bash scripts/sync_prod_db_to_local.sh
```

Advertencia:
- Este flujo **resetea schema local** (`DROP SCHEMA ... CASCADE`), usar solo con backup previo y conciencia de impacto.
- Default actual de dumps temporales: `$HOME/.app360/backups/db-sync/`.

### 7.3 Corrección de permisos locales tras restore

```bash
bash scripts/fix_local_db_privileges.sh
```

---

## 8) Deploy y operación en VPS

Fuente operativa: `docs/DEPLOY_VPS.md`

### 8.1 Runtime objetivo

- Código: `/var/www/app360`
- Servicio: `app360.service`
- Entorno: `/var/www/app360/.env`
- Gunicorn bind local: `127.0.0.1:5000`
- Backups operativos en VPS: `/var/backups/app360`

### 8.2 Update estándar

```bash
cd /var/www/app360
sudo -u www-data git pull
sudo -u www-data bash scripts/deploy.sh
bash scripts/apply_db_release_to_vps.sh <release_tag>   # si corresponde
sudo systemctl restart app360
curl -fsS http://127.0.0.1:5000/api/health
```

### 8.3 Qué hace y qué no hace `deploy.sh`

Hace:
- prepara `venv` si falta
- instala dependencias
- valida `.env`
- chequea conexión DB
- corre tests seguros en SQLite temporal

No hace:
- seed de datos
- `db.create_all()`
- restart de systemd automático

---

## 9) Observabilidad y logs

- Log app: `logs/app.log`
- Log seguridad: `logs/security.log`
- En VPS, systemd/journalctl para servicio `app360`.

Comandos útiles:

```bash
sudo systemctl status app360 --no-pager
sudo journalctl -u app360 -n 200 --no-pager
```

---

## 10) Testing y calidad

Backend:

```bash
PYTHONPATH=$PWD pytest
```

Frontend:

```bash
cd frontend
npm test
```

E2E (si aplica):

```bash
cd frontend
npx playwright test
```

---

## 11) Integración SabioGo (resumen técnico)

### 11.1 Flujo

1. Ingesta XLS (manual o batch).
2. Carga a staging (`stg_sabiogo_ventas`, `stg_sabiogo_compras`).
3. Mapeos producto/cliente/ubicación.
4. Procesamiento a facts/consultas de rentabilidad.

### 11.2 Consideraciones actuales

- Manejo de `origen` (`LEGACY`, `CARNES`, `LACTEOS`) para joins correctos.
- Normalización de `codigo` / preservación de `codigo_raw` en importaciones.
- Scripts y servicios relevantes:
  - `services/sabiogo_service.py`
  - `services/sabiogo_batch_importer.py`
  - `scripts/import_sabiogo_batch.py`

---

## 12) Recuperación y continuidad operativa

### 12.1 Recuperación de código

Fuente de recuperación: `GitHub/main`.

```bash
git clone <repo_url>
cd app360
git checkout main
```

### 12.2 Recuperación de esquema/datos

- Preferir releases versionadas (`backups/db-releases/<tag>`).
- Validar checksum antes de aplicar.
- Ejecutar smoke test de salud posterior.

### 12.3 Checklist post-recuperación

- [ ] `git rev-parse HEAD` coincide con versión objetivo
- [ ] `DATABASE_URL` correcto en `.env`
- [ ] servicio `app360` activo
- [ ] `/api/health` responde 200
- [ ] módulos críticos cargan sin error

---

## 13) Convenciones de mantenimiento

- Mantener cambios pequeños y trazables.
- Evitar mezcla de refactors masivos con fixes urgentes.
- Toda operación manual excepcional debe quedar documentada en PR/issue.
- No borrar scripts/docs legacy sin evidencia de no uso y plan de rollback.

---

## 14) Runbooks rápidos

### 14.1 Ver estado Git local limpio

```bash
git fetch --all --prune
git status --short
git rev-list --left-right --count origin/main...main
```

### 14.2 Ver estado Git en VPS

```bash
ssh <user>@<host> "cd /var/www/app360 && git status --short && git rev-parse HEAD && git branch --show-current"
```

### 14.3 Validación de servicio en VPS

```bash
ssh <user>@<host> "sudo systemctl status app360 --no-pager && curl -fsS http://127.0.0.1:5000/api/health"
```

---

## 15) Historial de actualizaciones del manual

- 2026-03-04: creación inicial del manual exhaustivo.

---

## 16) Módulo de Control de Asistencia (Fichadas)

### 16.1 Descripción

Sistema de control de asistencia basado en fichadas de reloj biométrico. Permite importar registros desde Excel, asociarlos con empleados, procesar contra turnos asignados y generar un resumen diario con KPIs.

### 16.2 Modelos

- **`FichadaReloj`** (`fichadas_reloj`): registro crudo importado del reloj. Campos clave: `clock_id_original` (ID del reloj, String), `empleado_id` (nullable FK a Employee), `nombre_reloj`, `fecha`, `hora`, `fecha_hora`. UniqueConstraint en `(clock_id_original, fecha_hora)`.
- **`ResumenAsistenciaDiaria`** (`resumen_asistencia_diaria`): resultado del procesamiento. Un registro por empleado/fecha con conteo de fichadas, horas de entrada/salida, minutos tarde, flags (es_falta, es_tarde, fichada_faltante, justificado).

### 16.3 Flujo de datos

```
Excel (Transacciones_*.xlsx, skiprows=7)
  │
  ▼
POST /api/rrhh/fichadas/cargar
  → Importa TODAS las fichadas con empleado_id=NULL
  → Normaliza clock_id (float→int, strip)
  → Dedup batch contra DB existente
  → Auto-asocia con Employee.clock_id (_asociar_fichadas)
  │
  ▼
POST /api/rrhh/fichadas/asociar  (re-asociar manualmente)
  → Busca fichadas sin empleado_id
  → Matchea contra Employee.clock_id (normalizado)
  │
  ▼
POST /api/rrhh/fichadas/procesar
  → Toma fichadas asociadas (empleado_id IS NOT NULL)
  → Agrupa por (empleado_id, fecha)
  → Compara contra TurnoDia del empleado
  → Genera/actualiza ResumenAsistenciaDiaria
  │
  ▼
GET /api/rrhh/fichadas/resumen
  → Consulta ResumenAsistenciaDiaria
  → KPIs, ranking, tendencia 6 meses, fichadas pendientes
  → Alimenta el tablero (rrhh_ausentismo.html)
```

### 16.4 Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/rrhh/fichadas/cargar` | Importa Excel, auto-asocia y auto-procesa. Retorna: importados, duplicados, errores_parse, asociados, pendientes, diagnostico, procesamiento |
| POST | `/api/rrhh/fichadas/asociar` | Re-asocia fichadas pendientes con Employee.clock_id, devuelve diagnostico útil y reprocesa empleados recién impactados |
| POST | `/api/rrhh/fichadas/procesar` | Genera ResumenAsistenciaDiaria desde fichadas asociadas. Requiere `lote` o `fecha_desde`+`fecha_hasta` |
| GET | `/api/rrhh/fichadas/resumen` | KPIs y tabla del tablero. Filtros: periodo, empleado_id, estado |
| GET | `/api/rrhh/fichadas/resumen-empleado` | Detalle mensual de un empleado |
| PUT | `/api/rrhh/fichadas/resumen/<id>/justificar` | Justifica una falta/tardanza |

### 16.5 Configuración de empleados

- Cada Employee necesita `clock_id` (entero, configurado en `/admin/rrhh`) que corresponde al ID del reloj biométrico.
- Cada Employee necesita `turno_id` asignado para que el procesamiento funcione.
- Sin turno asignado, las fichadas se importan y asocian pero no se procesan.
- El Admin normaliza `clock_id` al guardar y rechaza duplicados con error legible.

### 16.5.1 Diagnóstico de asociación

- `diagnostico.empleados_con_clock_id`: cantidad de empleados con ID Reloj configurado.
- `diagnostico.matchables`: clock IDs pendientes que sí encuentran empleado.
- `diagnostico.sin_match`: clock IDs pendientes sin coincidencia en Employee.clock_id.
- `diagnostico.sin_turno`: coincidencias válidas que todavía no tienen turno asignado.
- `diagnostico.ambiguos`: casos con empleados duplicados tras normalizar clock IDs; no se auto-asocian.
- `procesamiento.sin_turno`: cantidad de empleados asociados que no pudieron procesarse por falta de turno.

### 16.6 Formato Excel esperado

- Archivo: `Transacciones_*.xlsx`
- Se saltan las primeras 7 filas (`skiprows=7`)
- Columnas requeridas: `ID` (clock_id), `fecha`, `Hora de registro de entrada` (formato HH:MM o HH:MM:SS)
- Columnas opcionales: `Nombre`, `Apellido` (se guardan como `nombre_reloj`)

### 16.7 Migraciones

- `20260401_fichadas_reloj.py`: creación de tablas `fichadas_reloj` y `resumen_asistencia_diaria`
- `20260401_fichadas_nullable.py`: empleado_id nullable, +nombre_reloj, UniqueConstraint actualizado

### 16.8 Template

- `templates/rrhh_ausentismo.html`: panel completo con KPIs, charts (Chart.js), tabla de detalle, modal de importación, banner de fichadas sin asociar
- El banner `fichadas_sin_procesar` se calcula sobre el período visible del tablero, no sobre todo el historial.
