# Integracion automatica SabioGo (Firebird) -> App360

**Ultima revision:** 2026-07-13

**Version del documento:** 2.4

**Estado:** E2E e idempotencia validadas; automatizacion y alertas implementadas; pendiente instalar tarea en Windows

## 1. Objetivo

Una tarea diaria en el servidor Windows de SabioGo consulta ventas y compras en Firebird y realiza cuatro solicitudes HTTPS a App360:

1. `POST /sabiogo/api/db-sync/status` con estado `iniciada`.
2. `POST /sabiogo/api/db-sync/daily` con ventas y compras, confirmadas en una sola transaccion.
3. `POST /sabiogo/api/db-sync/finalize` para refrescar facts y objetivos PRE, solo si la carga diaria termino bien.
4. `POST /sabiogo/api/db-sync/status` con estado `exitosa` o `error`.

El cliente es de solo lectura sobre Firebird. No expone la base a Internet y no reemplaza todavia la carga manual como contingencia.

```text
Windows SabioGo                              VPS App360
-------------------------------              --------------------------------
Task Scheduler                               Nginx + Gunicorn + Flask
  run_sync.bat                                 /sabiogo/api/db-sync/daily
    sync.py                                    /sabiogo/api/db-sync/finalize
      P_VENTAS_GLOBALES        HTTPS JSON        staging ventas/compras
      P_COMPRAS_GLOBALES  ----------------->     logs de carga
      Firebird localhost                         facts + objetivos PRE
```

## 2. Estado actual

| Componente | Estado |
|---|---|
| Firebird 4.0.6 en Windows | Validado en `localhost:3050`, alias `VYP`. |
| `P_VENTAS_GLOBALES` | Validado: 279 filas y 29 columnas para 2026-05-04. |
| `P_COMPRAS_GLOBALES` | Validado: 53 filas y 29 columnas para 2026-05-04. |
| Cliente Windows | Implementa ventas, compras, vacios, retries y finalizacion. |
| Receptor Flask | Desplegado; ventas y compras atomicas por fecha. |
| Concurrencia | Advisory lock PostgreSQL serializa cargas de la misma fecha. |
| Autenticacion tecnica | Restringida a `db-sync`, `db-sync/daily`, `db-sync/finalize` y `db-sync/status`. |
| Dedupe | Incluye `origen` en la firma. |
| Facts y objetivos | Orquestados por `db-sync/finalize`. |
| VPS productivo | Desplegado; health `200`, sync sin clave `401`, sync autenticado con payload invalido `400`. |
| E2E Windows | Dos ejecuciones identicas para 2026-05-04, reconciliadas en staging, facts y auditorias. |
| Alertas web | Fallo, demora o ausencia visibles solamente para rol `gerente`. |
| Task Scheduler | Instalador preparado para 02:00 bajo cuenta local `Administrador`; pendiente ejecutar en Windows. |

La prueba manual de `run_sync.bat --fecha 2026-05-04` y su repeticion idempotente finalizaron correctamente.

## 3. Configuracion Windows

Archivo local `C:\SabioGoSync\config.ini`:

```ini
[firebird]
host = localhost
port = 3050
database = VYP
user = USUARIO_SOLO_LECTURA
password = SECRETO_FIREBIRD
client_library = C:\Program Files\Firebird\Firebird_4_0\fbclient.dll

[vps]
url = https://vyp.app360.com.ar
api_key = SECRETO_COMPARTIDO
timeout_seconds = 120
max_retries = 3
backoff_factor = 1
origenes = CARNES,LACTEOS
```

Reglas:

- `database` es el alias o ruta de base. No usar `localhost/VYP` con `firebird-driver 2.0.3`.
- `host` y `port` se aplican mediante `driver_config.server_defaults`.
- `client_library` debe apuntar a una DLL compatible con la arquitectura de Python.
- La URL debe usar HTTPS.
- Los placeholders generados por `setup.bat` son rechazados por el cliente.
- `origenes` declara las unidades que deben reemplazarse incluso cuando un procedimiento devuelve cero filas.

Dependencias fijadas y validadas en Windows:

```text
firebird-driver==2.0.3
requests==2.34.2
```

## 4. Contrato de carga

### Request

```http
POST /sabiogo/api/db-sync/daily
X-Sync-Key: <SABIOGO_SYNC_API_KEY>
Content-Type: application/json; charset=utf-8
```

```json
{
  "fecha": "2026-05-04",
  "replace": true,
  "origenes": ["CARNES", "LACTEOS"],
  "ventas": [
    {
      "EMPRESA": "VYP",
      "FECHA": "2026-05-04",
      "CODIGO": "1001",
      "PRODUCTO": "ASADO KG",
      "NRO_COMPROB": "0001-00009999",
      "TIPO": "FAC",
      "SUBTOT": 49725.0
    }
  ],
  "compras": [
    {
      "EMPRESA": "VYP",
      "FECHA": "2026-05-04",
      "CODIGO": "1001",
      "PRODUCTO": "ASADO KG",
      "NRO_COMPROB": "0001-00001234",
      "TIPO": "OC",
      "SUBTOT": 30200.0
    }
  ]
}
```

| Campo | Regla |
|---|---|
| `fecha` | Obligatoria, formato `YYYY-MM-DD`. |
| `replace` | Por defecto `true`. |
| `origenes` | Lista no vacia. Obligatoria si `ventas` o `compras` esta vacio. |
| `ventas` | Lista obligatoria; puede estar vacia si se declaran origenes. |
| `compras` | Lista obligatoria; puede estar vacia si se declaran origenes. |
| `EMPRESA` | Obligatoria por fila y debe estar mapeada. |
| `FECHA` | Si viene informada, debe coincidir con la fecha del lote. |
| `empresa_map` | Opcional; agrega empresas, pero el origen debe ser `CARNES` o `LACTEOS`. |

Mapeo predeterminado:

| Empresa Firebird | Origen App360 |
|---|---|
| `VYP`, `CARNES` | `CARNES` |
| `LACTEOS_VP`, `VYP_LACTEOS`, `LACTEOS` | `LACTEOS` |

### Semantica transaccional

- Se agrupan filas por origen.
- Con `replace=true`, se borran fecha y origen antes de insertar.
- Ventas, compras y todos los origenes declarados se procesan en una sola transaccion.
- Un advisory lock transaccional de PostgreSQL serializa requests para la misma fecha.
- Si falla cualquier tipo u origen, se ejecuta rollback del request completo y se responde HTTP 500.
- Un lote vacio reemplaza los origenes declarados, elimina datos obsoletos y registra auditorias de cero filas.
- Una respuesta HTTP 200 siempre representa exito completo; `errores` es `null`.
- El cliente tambien valida `success`, `errores`, `fecha`, totales y resultados para ambos tipos.

Respuesta exitosa:

```json
{
  "success": true,
  "fecha": "2026-05-04",
  "total_filas": {
    "ventas": 279,
    "compras": 53,
    "total": 332
  },
  "resultados": {
    "ventas": {
      "CARNES": {
        "filas_insertadas": 200,
        "filas_procesadas": 200,
        "filas_duplicadas": 0,
        "filas_error": 0
      },
      "LACTEOS": {
        "filas_insertadas": 79,
        "filas_procesadas": 79,
        "filas_duplicadas": 0,
        "filas_error": 0
      }
    },
    "compras": {
      "CARNES": {},
      "LACTEOS": {}
    }
  },
  "errores": null,
  "replace": true
}
```

Codigos HTTP:

| HTTP | Significado |
|---|---|
| `200` | Request completo confirmado. |
| `400` | JSON, fecha, origenes o filas invalidos. |
| `401` | Clave ausente o incorrecta. |
| `500` | Fallo atomico; ninguna venta, compra u origen queda confirmado. |
| `503` | `SABIOGO_SYNC_API_KEY` no configurada. |

`POST /sabiogo/api/db-sync` se conserva para compatibilidad y diagnostico de un solo tipo. El cliente diario no lo utiliza.

## 5. Finalizacion

```http
POST /sabiogo/api/db-sync/finalize
X-Sync-Key: <SABIOGO_SYNC_API_KEY>
Content-Type: application/json
```

```json
{"fecha": "2026-05-04"}
```

La finalizacion:

1. Promueve staging pendiente/cargado a procesado.
2. Refresca `fact_ventas_sabiogo` y `fact_costos_sabiogo`.
3. Intenta `REFRESH MATERIALIZED VIEW CONCURRENTLY`; usa refresh estandar como fallback.
4. Sincroniza objetivos PRE del mes de la fecha recibida.
5. Es invocada por el cliente solo cuando la transaccion diaria termino bien.

Si falla, el cliente termina con codigo distinto de cero. Repetir la fecha es seguro.

### Estado operativo

Cada invocacion de `sync_fecha` genera un UUID y reporta `iniciada`, `exitosa` o `error` en `/sabiogo/api/db-sync/status`. Los reportes del mismo UUID se serializan en PostgreSQL y los reintentos de un estado terminal no modifican su hora de finalizacion.

Si el reporte terminal no llega al VPS despues de los retries, el cliente termina con codigo distinto de cero aunque la carga de datos haya finalizado. Desde las 03:00, App360 tambien alerta cuando falta o sigue abierta la ejecucion programada para las 02:00.

## 6. Seguridad

- `X-Sync-Key` solo habilita `sabiogo_db_sync`, `sabiogo_db_sync_daily`, `sabiogo_db_sync_finalize` y `sabiogo_db_sync_status`.
- Otras rutas siguen exigiendo sesion y permisos.
- Las comparaciones de secretos usan `hmac.compare_digest`.
- Las rutas tecnicas estan exentas de CSRF, pero mantienen autenticacion por header.
- El cron PRE independiente usa `X-App360-Cron-Token`; no acepta `X-Sync-Key`.
- Los secretos no deben guardarse en el repositorio, documentacion, logs ni Task Scheduler arguments.
- `install_task.bat` elimina permisos heredados de `C:\SabioGoSync` y conserva acceso completo solo para `Administrador` y `SYSTEM`.

Variables requeridas en el VPS:

```env
SABIOGO_SYNC_API_KEY=<secreto-aleatorio-de-al-menos-32-bytes>
SABIOGO_CRON_TOKEN=<solo-si-se-mantiene-el-cron-independiente>
```

## 7. Integridad e idempotencia

La firma anti-duplicados incluye:

```text
origen + nro_comprob + tipo + fecha + codigo + subtot
```

Esto evita cruces falsos entre CARNES y LACTEOS.

Cada lote genera un hash SHA-256 canonico que incluye tipo, fecha, origen, filas y `replace`. La auditoria se registra en `logs_sabiogo_carga`, incluyendo lotes vacios.

Con `replace=true`, reejecutar una fecha reconstruye el mismo estado logico. Las cargas concurrentes de una fecha se serializan hasta commit o rollback. `--no-replace` queda reservado para diagnostico controlado.

## 8. Evidencia Windows

Validacion realizada el 2026-07-13:

- Windows Server 2019, Python 3.12.3 x64.
- Firebird Server y Guardian 4.0.6.3221 activos.
- Cliente nativo x64 en `C:\Program Files\Firebird\Firebird_4_0\fbclient.dll`.
- Alias `VYP`; base real `F:\SabioGo\DataBase\VYP.FDB`.
- Usuario tecnico conecta y ejecuta ambos procedimientos.
- 2026-05-01: ventas 0 filas, consulta exitosa.
- 2026-05-04: ventas 279, compras 53, total 332.
- Ambos procedimientos devuelven 29 columnas.
- Empresas observadas: `VYP` y `LACTEOS_VP`.
- HTTPS Windows -> VPS y TLS/Nginx funcionan.
- Receptor productivo desplegado; HTTPS y autenticacion validados sin insertar datos.
- `setup.bat` ejecutado correctamente sobre Python 3.12.3 y el entorno existente.
- Primera E2E: 279 ventas, 53 compras, total recibido 332, codigo de salida 0.
- Una venta LACTEOS duplicada fue descartada; ambas filas eran identicas en las 29 columnas.
- Estado publicado: ventas CARNES 217, ventas LACTEOS 61, compras CARNES 47 y compras LACTEOS 6.
- Staging y facts contienen exactamente los mismos conteos, todos con estado procesado.
- Segunda E2E produjo los mismos conteos, hashes y resultado; idempotencia confirmada.
- Cada uno de los cuatro lotes tiene dos auditorias, un unico hash y cero errores.

La salida UTF-8 de `sync.log` puede verse corrupta con `type` bajo la pagina de codigos predeterminada de CMD; `chcp 65001` corrige solo la visualizacion.

## 9. Pruebas automatizadas

Comando focalizado sobre una DB ya inicializada (el preflight de `scripts/deploy.sh` crea el SQLite temporal antes de pytest):

```bash
.venv/bin/python -m pytest tests/test_sabiogo_cobertura.py tests/test_sabiogo_sync_client.py tests/test_sabiogo_sync_alerts.py -q
```

Resultado 2026-07-13:

```text
52 passed
```

Preflight completo por archivo, con SQLite temporal y procesos aislados:

```text
72 passed (3 + 6 + 35 + 11 + 7 + 10)
```

Cobertura incluida:

- alcance de API key y token cron;
- separacion y dedupe por origen;
- dedupe cross-carga con campos nulos en la firma;
- compras en staging correcto;
- fecha inconsistente;
- reemplazo y lote vacio auditado;
- rollback atomico ante fallo de un origen;
- finalizacion de facts y objetivos;
- configuracion host/puerto de Firebird;
- extraccion de ambos procedimientos antes del unico envio diario;
- rollback conjunto de ventas y compras;
- autenticacion del endpoint diario;
- autenticacion, idempotencia y serializacion del endpoint de estado;
- validacion de respuestas VPS;
- retries POST para errores transitorios.
- alerta inmediata por error y control de ausencia a las 03:00;
- fallos historicos visibles hasta recuperar la misma fecha;
- banner visible solo para rol `gerente`;
- codigo distinto de cero si no puede confirmarse el estado final.

La suite monolitica tiene un problema preexistente de aislamiento: algunos fixtures mutan `Config` entre archivos. El preflight de `scripts/deploy.sh` evita esa contaminacion ejecutando cada archivo en un proceso separado.

## 10. Salida a produccion

### Completado en VPS

1. Codigo integrado en `main` y descargado por fast-forward.
2. `SABIOGO_SYNC_API_KEY` generada y configurada sin guardarla en Git.
3. Deploy completo con conexion PostgreSQL y 63 pruebas aprobadas.
4. Servicio Gunicorn reiniciado y activo.
5. Verificados health `200`, sync sin clave `401` y sync autenticado con payload invalido `400`.

### Preparado para el siguiente deploy

1. Migracion Alembic `20260713_sabiogo_sync_runs` con una unica cabeza.
2. Release incremental `20260713_sabiogo_sync_alerts` con checksum SHA-256.
3. Release aplicado dos veces sobre un esquema PostgreSQL local temporal: revision correcta, tabla presente y seis indices.
4. `setup.bat` aplica la DACL antes de crear secretos; `install_task.bat` vuelve a verificarla antes de programar la tarea.
5. `scripts/deploy.sh` aborta si una migracion falla o Alembic no queda en `head`.

### Completado en Windows

1. Cuatro archivos iniciales actualizados y dependencias verificadas.
2. Configuracion Firebird preservada y clave VPS instalada sin exponerla.
3. Endpoint sin credenciales confirmado en `401`.
4. Primera E2E confirmada con codigo 0 y finalizacion correcta.
5. Duplicado real verificado como dos filas identicas en las 29 columnas.
6. Staging, facts y auditorias reconciliados en PostgreSQL.
7. Segunda ejecucion confirmada idempotente.

### Pendiente operativo

1. Copiar los seis archivos de `scripts/sabiogo_sync` a `C:\SabioGoSync`.
2. Aplicar release DB `20260713_sabiogo_sync_alerts` antes de reiniciar App360.
3. Confirmar zona `Argentina Standard Time` y ejecutar `install_task.bat` desde CMD elevado.
4. Confirmar primera ejecucion automatica y alerta visible para rol `gerente`.
5. Monitorear siete noches antes de retirar la carga manual habitual.
6. Medir tamano maximo diario y revisar timeouts con volumen real.

### Riesgos residuales

- Convivencia con carga manual: una importacion global puede borrar datos cargados por API.
- La finalizacion ocurre despues del commit diario; si falla debe reintentarse para publicar los derivados.
- No hay particionado ni compresion para requests mayores a 10 MB.
- No se configuro rotacion de secreto ni allowlist de IP.
- Si Windows pierde red antes de reportar, la alerta depende del control de ausencia a las 03:00.
- La contrasena de `Administrador` debe actualizarse en la tarea si cambia o expira.
- Cambiar la zona horaria del servidor afecta todos sus procesos; el instalador solo valida y nunca la modifica.

## 11. Historial

| Version | Fecha | Descripcion |
|---|---|---|
| `2.4` | 2026-07-13 | Tarea diaria 02:00, cuenta Administrador y alertas web para rol gerente. |
| `2.3` | 2026-07-13 | E2E Windows, duplicado exacto, reconciliacion e idempotencia aprobadas. |
| `2.2` | 2026-07-13 | Deploy VPS completado, secreto configurado y smoke tests `200/401/400` aprobados. |
| `2.1` | 2026-07-13 | Request diario atomico para ventas y compras, advisory lock por fecha y rollback conjunto. |
| `2.0` | 2026-07-13 | Contrato dual y atomico, origenes explicitos, vacios auditados, finalizacion, retries y evidencia Windows. |
| `1.1` | 2026-07-13 | Brecha ventas/compras y datos faltantes para Firebird. |
| `1.0` | 2026-07-13 | Estado inicial, riesgos y plan de salida. |
