# Integracion automatica SabioGo (Firebird) -> App360

**Ultima revision:** 2026-07-13

**Version del documento:** 2.2

**Estado:** receptor desplegado en el VPS; autenticacion y preflight validados; pendiente prueba E2E manual desde Windows

## 1. Objetivo

Una tarea diaria en el servidor Windows de SabioGo consulta ventas y compras en Firebird y envia dos requests HTTPS a App360:

1. `POST /sabiogo/api/db-sync/daily` con ventas y compras, confirmadas en una sola transaccion.
2. `POST /sabiogo/api/db-sync/finalize` para refrescar facts y objetivos PRE, solo si la carga diaria termino bien.

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
| Autenticacion tecnica | Restringida a `db-sync`, `db-sync/daily` y `db-sync/finalize`. |
| Dedupe | Incluye `origen` en la firma. |
| Facts y objetivos | Orquestados por `db-sync/finalize`. |
| VPS productivo | Desplegado; health `200`, sync sin clave `401`, sync autenticado con payload invalido `400`. |
| Task Scheduler | No configurado. |

La prueba manual de `run_sync.bat --fecha 2026-05-04` queda habilitada despues de actualizar los cuatro archivos Windows y configurar el secreto entregado fuera del repositorio.

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

## 6. Seguridad

- `X-Sync-Key` solo habilita `sabiogo_db_sync`, `sabiogo_db_sync_daily` y `sabiogo_db_sync_finalize`.
- Otras rutas siguen exigiendo sesion y permisos.
- Las comparaciones de secretos usan `hmac.compare_digest`.
- Las rutas tecnicas estan exentas de CSRF, pero mantienen autenticacion por header.
- El cron PRE independiente usa `X-App360-Cron-Token`; no acepta `X-Sync-Key`.
- Los secretos no deben guardarse en el repositorio, documentacion, logs ni Task Scheduler arguments.

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

No se probo todavia el nuevo `setup.bat` en Windows despues de corregir su generacion de `config.ini`.

## 9. Pruebas automatizadas

Comando focalizado:

```bash
.venv/bin/python -m pytest tests/test_sabiogo_cobertura.py tests/test_sabiogo_sync_client.py -q
```

Resultado 2026-07-13:

```text
43 passed
```

Preflight equivalente al despliegue, con SQLite temporal y cada archivo en un proceso separado:

```text
63 passed (3 + 6 + 35 + 11 + 8)
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
- validacion de respuestas VPS;
- retries POST para errores transitorios.

La suite monolitica tiene un problema preexistente de aislamiento: algunos fixtures mutan `Config` entre archivos. El preflight de `scripts/deploy.sh` evita esa contaminacion ejecutando cada archivo en un proceso separado.

## 10. Salida a produccion

### Completado en VPS

1. Codigo integrado en `main` y descargado por fast-forward.
2. `SABIOGO_SYNC_API_KEY` generada y configurada sin guardarla en Git.
3. Deploy completo con conexion PostgreSQL y 63 pruebas aprobadas.
4. Servicio Gunicorn reiniciado y activo.
5. Verificados health `200`, sync sin clave `401` y sync autenticado con payload invalido `400`.

### Pendiente inmediato en Windows

1. Reemplazar `sync.py`, `setup.bat`, `run_sync.bat` y `requirements.txt` en `C:\SabioGoSync`.
2. Conservar credenciales Firebird existentes en `config.ini` y actualizar solo la clave VPS.
3. Ejecutar `setup.bat` desde CMD para actualizar dependencias.
4. Confirmar que el endpoint sin credenciales responde `401`.
5. Ejecutar `run_sync.bat --fecha 2026-05-04` manualmente.
6. Reconciliar 279 ventas, 53 compras, staging, auditorias, facts y objetivos.
7. Reejecutar la misma fecha para validar idempotencia.

### Despues de E2E

- Medir tamano maximo diario contra `client_max_body_size` de Nginx.
- Alinear timeouts Nginx, Gunicorn y cliente.
- Configurar Task Scheduler con cuenta de servicio.
- Definir alerta y responsable operativo.
- Monitorear siete noches antes de retirar la carga manual habitual.

### Riesgos residuales

- Convivencia con carga manual: una importacion global puede borrar datos cargados por API.
- La finalizacion ocurre despues del commit diario; si falla debe reintentarse para publicar los derivados.
- No hay particionado ni compresion para requests mayores a 10 MB.
- No se configuro rotacion de secreto ni allowlist de IP.
- No existe alerta automatica ante fallo nocturno.

## 11. Historial

| Version | Fecha | Descripcion |
|---|---|---|
| `2.2` | 2026-07-13 | Deploy VPS completado, secreto configurado y smoke tests `200/401/400` aprobados. |
| `2.1` | 2026-07-13 | Request diario atomico para ventas y compras, advisory lock por fecha y rollback conjunto. |
| `2.0` | 2026-07-13 | Contrato dual y atomico, origenes explicitos, vacios auditados, finalizacion, retries y evidencia Windows. |
| `1.1` | 2026-07-13 | Brecha ventas/compras y datos faltantes para Firebird. |
| `1.0` | 2026-07-13 | Estado inicial, riesgos y plan de salida. |
