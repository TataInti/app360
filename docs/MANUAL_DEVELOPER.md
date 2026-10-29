# Manual de Developer — App360

Última actualización: 2026-07-29
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
- `docs/SABIOGO_SYNC_API.md`

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
- `services/`: lógica de negocio y orquestación. El cálculo compartido de resultado comercial vive en `services/resultado_comercial_service.py`.
- `repositories/`: consultas y agregaciones de acceso a datos.
- `dtos/`: objetos de transferencia para respuestas estructuradas.

### 3.3 Persistencia y migraciones

- `migrations/`: Alembic (`env.py` + `versions/`).
- `alembic.ini`: configuración de migraciones.
- `scripts/migrate_db_safely.sh`: backup, restore de ensayo y Alembic forward-only.
- `scripts/apply_db_migrations_to_vps.sh`: invocación remota con commit y revisiones explícitas.
- `scripts/sabiogo_sync/rebaseline_2026.bat`: recarga controlada 2026 desde Windows/SabioGo.
- `scripts/sabiogo_sync/validate_rebaseline_2026.sql`: auditoría SQL posterior a rebaseline productivo.

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
- Los conceptos de Tesorería se administran en `/admin/movimientos`; `/admin/gastos` redirige por compatibilidad.
- Las APIs legacy `/api/admin/gastos/categorias` se normalizan internamente a `/api/admin/movimientos/conceptos`.
- La creación de conceptos desde `/api/gastos/categorias` queda restringida a `admin`, `manager` y `gerente`.

### 4.3 Seguridad operativa

- Eventos de seguridad se registran en `logs/security.log`.
- Headers de hardening se agregan en `after_request` (CSP, HSTS según esquema, X-Frame-Options, etc.).

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
- `SABIOGO_SYNC_API_KEY` para la integración automática SabioGo

No se versionan plantillas de entorno en el repositorio.

### 5.2 Política de secretos

- Nunca commitear `.env`, llaves o credenciales.
- Información local sensible debe ir en `docs/_local/` o archivos ignorados.

---

## 6) Flujo de trabajo de desarrollo

### 6.1 Setup local recomendado

Prerrequisitos genéricos:

- Python 3.12
- PostgreSQL accesible localmente
- Dependencias del sistema necesarias para `requirements.txt`

Las notas específicas de máquina, package manager, PATH y servicios locales no se versionan; mantenelas en `docs/_local/` o en documentación privada.

Backend:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
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
2. Todo cambio DB pasa por GitHub como migración Alembic forward-only.
3. No aplicar cambios ad-hoc en VPS por fuera del flujo.

### 7.1 Migración segura

Aplicar desde la máquina operadora:

```bash
EXPECTED_GIT_SHA=<sha_completo> \
PROD_SSH_HOST=<host> \
MAINTENANCE_CONFIRMED=true \
bash scripts/apply_db_migrations_to_vps.sh \
  <revision_actual> <revision_objetivo> <sql_de_validacion>
```

El ejecutor exige escrituras pausadas, valida commit y revisiones, crea backup
con SHA256, ensaya su restauración y aplica solamente Alembic forward-only. Los
backups viven en `/var/backups/app360`, fuera del repositorio.

Los scripts históricos de dump completo están bloqueados.

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

### 7.4 Migraciones recientes relevantes

- `20260729_conceptos_movimientos_resultado.py`: descendiente directo de `20260713_sabiogo_sync_runs`; agrega naturaleza, participación y auditoría sin introducir geofencing.
- `20260729_ensure_efectivo_iva.py`: conciliación idempotente de `EFECTIVO IVA`.

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
# aplicar scripts/apply_db_migrations_to_vps.sh desde la máquina operadora
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

No hay app React/Vite separada en este checkout. La validación UI se hace sobre las plantillas Flask/Jinja servidas por el backend.

Tests focalizados para cambios recientes:

```bash
PYTHONPATH=$PWD pytest tests/test_resultado_comercial.py
PYTHONPATH=$PWD pytest tests/test_dashboards_v2.py tests/test_rrhh_fichadas.py tests/test_sabiogo_service.py
```

Notas de aislamiento:
- Los fixtures nuevos deben usar `monkeypatch.setattr(Config, ...)` en vez de mutar `Config` globalmente.
- `tests/test_resultado_comercial.py` cubre la coincidencia Ejecutivo/BI, validación de conceptos y granularidad semanal del dashboard financiero.

---

## 11) Integración SabioGo (resumen técnico)

### 11.1 Flujo

1. Ingesta API automática desde Firebird Windows o carga manual/batch como contingencia.
2. Carga a staging (`stg_sabiogo_ventas`, `stg_sabiogo_compras`).
3. Mapeos producto/cliente/ubicación.
4. Finalización a facts/materialized views y objetivos PRE.
5. Consumo por dashboards de resultado comercial.

### 11.2 Consideraciones actuales

- Manejo de `origen` (`LEGACY`, `CARNES`, `LACTEOS`) para joins correctos.
- Normalización de `codigo` / preservación de `codigo_raw` en importaciones.
- La integración diaria usa `replace=true` por fecha y origen para mantener idempotencia.
- `docs/SABIOGO_SYNC_API.md` contiene el contrato completo de endpoints, seguridad y operación Windows.
- Scripts y servicios relevantes:
  - `services/sabiogo_service.py`
  - `services/sabiogo_batch_importer.py`
  - `services/sabiogo_sync_monitor.py`
  - `scripts/import_sabiogo_batch.py`
  - `scripts/sabiogo_sync/sync.py`

### 11.3 Rebaseline SabioGo 2026

Scripts nuevos:
- `scripts/sabiogo_sync/rebaseline_2026.bat`: ejecuta enero a julio 2026 por rangos mensuales, fecha por fecha, con `replace=true`.
- `scripts/sabiogo_sync/validate_rebaseline_2026.sql`: audita ejecuciones, staging, facts y logs posteriores.

Reglas:
- Pausar temporalmente la tarea diaria `App360 SabioGo Sync` antes de correr el rebaseline.
- Ejecutar desde `C:\SabioGoSync` con `config.ini`, `run_sync.bat` y `venv` válidos.
- No usar `--no-replace` en recargas productivas.
- Si un mes falla, el script se detiene; es seguro reintentar ese mes con `replace=true`.
- El rango actual documentado llega hasta `2026-07-28`, último día cerrado al momento de la recarga.

---

## 12) Resultado comercial y conceptos de Tesorería

### 12.1 Métrica compartida

El cálculo oficial vive en `services/resultado_comercial_service.py` y alimenta:
- `GET /api/panel-ejecutivo-v2`
- `GET /api/bi/dashboard`

Fórmula:

```text
resultado_gestion = facturación sin PRE - compras + ingresos incluidos - egresos incluidos
```

Esta métrica es un indicador de gestión, no utilidad contable. Las compras representan entradas de mercadería; no sustituyen costo de mercadería vendida ni inventario valorizado.

### 12.2 Fuentes, filtros y advertencias

Fuentes:
- Facturación: `stg_sabiogo_ventas`, `estado='procesado'`, excluyendo comprobante `PRE`.
- Compras: `stg_sabiogo_compras`, `estado='procesado'`.
- Tesorería: `movimientos_caja` no anulados y conceptos incluidos en resultado.

Filtros:
- `fecha_desde` y `fecha_hasta` aplican a todas las fuentes.
- `empresa` (`TODAS`, `CARNES`, `LACTEOS`) aplica a ventas/compras por `origen`.
- Tesorería es global; no se distribuye por empresa. Si se filtra una empresa, la API devuelve advertencia `tesoreria_global`.
- Los filtros asimétricos `vendedor` y `producto` en BI se conservan por compatibilidad de URL, pero no modifican el resultado porque compras no tiene atribución equivalente.

Advertencias generadas:
- Fuentes sin datos o con corte anterior al período consultado.
- Conceptos activos sin `naturaleza`.
- Movimientos cuyo `tipo` contradice la naturaleza del concepto.

### 12.3 Conceptos de Tesorería

La tabla histórica `categoria_gasto` se conserva por compatibilidad, pero en la interfaz/API nueva representa conceptos estructurales de Tesorería.

Campos clave:
- `naturaleza`: `ingreso`, `egreso`, `ambos` o `NULL` si está pendiente de clasificar.
- `incluye_resultado`: indica si el concepto participa del resultado comercial.
- `efecto_resultado`: propiedad derivada (`suma`, `resta`, `segun_movimiento`, `pendiente`, `no_participa`).

Administración:
- UI: `/admin/movimientos`
- API canónica: `/api/admin/movimientos/conceptos`
- Alias legacy: `/admin/gastos` redirige y `/api/admin/gastos/categorias` normaliza a conceptos.
- Los cambios de concepto se auditan en `categoria_movimiento_audit` porque pueden recalcular períodos históricos.
- Si un concepto tiene movimientos asociados, eliminarlo desde administración lo desactiva en vez de borrarlo físicamente.

### 12.4 Validación al cargar movimientos

`POST /api/tesoreria/movimientos` ahora requiere `categoria_gasto_id`.

Reglas:
- Concepto inactivo o inexistente: `404`.
- Concepto sin `naturaleza`: `409`, debe corregirse en Administración → Movimientos.
- Concepto `ingreso` o `egreso`: el backend deriva/fija `tipo`.
- Si el request contradice la naturaleza del concepto: `422`.
- Concepto `ambos`: el request debe indicar `tipo` (`ingreso` o `egreso`).
- `monto` debe ser numérico positivo.

El módulo de gastos usa solo egresos categorizados y no anulados. El selector de gastos pide conceptos con `naturaleza=egreso,ambos`.

### 12.5 Dashboards relacionados

- Ejecutivo (`/panel-ejecutivo` → `/api/panel-ejecutivo-v2`): resultado de gestión, caja neta, concentración de clientes y cuenta corriente Friar.
- BI (`/bi` → `/api/bi/dashboard`): mismo contrato de resultado que Ejecutivo, con desglose de conceptos y frescura de datos.
- Financiero (`/api/dashboard-financiero`): adapta la granularidad de flujo a `dia`, `semana` o `mes` según período/rango.

---

## 13) Recuperación y continuidad operativa

### 13.1 Recuperación de código

Fuente de recuperación: `GitHub/main`.

```bash
git clone <repo_url>
cd app360
git checkout main
```

### 13.2 Recuperación de esquema/datos

- Usar backups operativos de `/var/backups/app360`.
- Validar SHA256 y catálogo antes de restaurar.
- Restaurar primero en una base aislada.
- Ejecutar smoke test de salud posterior.

### 13.3 Checklist post-recuperación

- [ ] `git rev-parse HEAD` coincide con versión objetivo
- [ ] `DATABASE_URL` correcto en `.env`
- [ ] servicio `app360` activo
- [ ] `/api/health` responde 200
- [ ] módulos críticos cargan sin error

---

## 14) Convenciones de mantenimiento

- Mantener cambios pequeños y trazables.
- Evitar mezcla de refactors masivos con fixes urgentes.
- Toda operación manual excepcional debe quedar documentada en PR/issue.
- No borrar scripts/docs legacy sin evidencia de no uso y plan de rollback.

---

## 15) Runbooks rápidos

### 15.1 Ver estado Git local limpio

```bash
git fetch --all --prune
git status --short
git rev-list --left-right --count origin/main...main
```

### 15.2 Ver estado Git en VPS

```bash
ssh <user>@<host> "cd /var/www/app360 && git status --short && git rev-parse HEAD && git branch --show-current"
```

### 15.3 Validación de servicio en VPS

```bash
ssh <user>@<host> "sudo systemctl status app360 --no-pager && curl -fsS http://127.0.0.1:5000/api/health"
```

---

## 16) Historial de actualizaciones del manual

- 2026-07-29: documentación de conceptos de Tesorería, resultado comercial compartido, migraciones geofence/sync/conceptos, rebaseline SabioGo 2026 y tests focalizados.
- 2026-03-04: creación inicial del manual exhaustivo.

---

## 17) Módulo de Control de Asistencia (Fichadas)

### 17.1 Descripción

Sistema de control de asistencia basado en fichadas de reloj biométrico. Permite importar registros desde Excel, asociarlos con empleados, procesar contra turnos asignados y generar un resumen diario con KPIs.

### 17.2 Modelos

- **`FichadaReloj`** (`fichadas_reloj`): registro crudo importado del reloj. Campos clave: `clock_id_original` (ID del reloj, String), `empleado_id` (nullable FK a Employee), `nombre_reloj`, `fecha`, `hora`, `fecha_hora`. UniqueConstraint en `(clock_id_original, fecha_hora)`.
- **`ResumenAsistenciaDiaria`** (`resumen_asistencia_diaria`): resultado del procesamiento. Un registro por empleado/fecha con conteo de fichadas, horas de entrada/salida, minutos tarde, flags (es_falta, es_tarde, fichada_faltante, justificado).

### 17.3 Flujo de datos

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

### 17.4 Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/rrhh/fichadas/cargar` | Importa Excel, auto-asocia y auto-procesa. Retorna: importados, duplicados, errores_parse, asociados, pendientes, diagnostico, procesamiento |
| POST | `/api/rrhh/fichadas/asociar` | Re-asocia fichadas pendientes con Employee.clock_id, devuelve diagnostico útil y reprocesa empleados recién impactados |
| POST | `/api/rrhh/fichadas/procesar` | Genera ResumenAsistenciaDiaria desde fichadas asociadas. Requiere `lote` o `fecha_desde`+`fecha_hasta` |
| GET | `/api/rrhh/fichadas/resumen` | KPIs y tabla del tablero. Filtros: periodo, empleado_id, estado |
| GET | `/api/rrhh/fichadas/resumen-empleado` | Detalle mensual de un empleado |
| PUT | `/api/rrhh/fichadas/resumen/<id>/justificar` | Justifica una falta/tardanza |

### 17.5 Configuración de empleados

- Cada Employee necesita `clock_id` (entero, configurado en `/admin/rrhh`) que corresponde al ID del reloj biométrico.
- Cada Employee necesita `turno_id` asignado para que el procesamiento funcione.
- Sin turno asignado, las fichadas se importan y asocian pero no se procesan.
- El Admin normaliza `clock_id` al guardar y rechaza duplicados con error legible.

### 17.5.1 Diagnóstico de asociación

- `diagnostico.empleados_con_clock_id`: cantidad de empleados con ID Reloj configurado.
- `diagnostico.matchables`: clock IDs pendientes que sí encuentran empleado.
- `diagnostico.sin_match`: clock IDs pendientes sin coincidencia en Employee.clock_id.
- `diagnostico.sin_turno`: coincidencias válidas que todavía no tienen turno asignado.
- `diagnostico.ambiguos`: casos con empleados duplicados tras normalizar clock IDs; no se auto-asocian.
- `procesamiento.sin_turno`: cantidad de empleados asociados que no pudieron procesarse por falta de turno.

### 17.6 Formato Excel esperado

- Archivo: `Transacciones_*.xlsx`
- Se saltan las primeras 7 filas (`skiprows=7`)
- Columnas requeridas: `ID` (clock_id), `fecha`, `Hora de registro de entrada` (formato HH:MM o HH:MM:SS)
- Columnas opcionales: `Nombre`, `Apellido` (se guardan como `nombre_reloj`)

### 17.7 Migraciones

- `20260401_fichadas_reloj.py`: creación de tablas `fichadas_reloj` y `resumen_asistencia_diaria`
- `20260401_fichadas_nullable.py`: empleado_id nullable, +nombre_reloj, UniqueConstraint actualizado

### 17.8 Template

- `templates/rrhh_ausentismo.html`: panel completo con KPIs, charts (Chart.js), tabla de detalle, modal de importación, banner de fichadas sin asociar
- El banner `fichadas_sin_procesar` se calcula sobre el período visible del tablero, no sobre todo el historial.
