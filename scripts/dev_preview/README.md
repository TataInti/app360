# Entorno E2E local de objetivos comerciales

Vista previa local de App360 para recorrer la pantalla `/comercial/objetivos`
con un navegador real. Todo corre en `127.0.0.1` y usa datos sintéticos.

## Qué levanta

- PostgreSQL 16 efímero en el contenedor `app360-e2e-pg`, en `127.0.0.1:55432`,
  base `app360_e2e`, con credenciales ficticias.
- Esquema previo a las migraciones (`baseline_previa.py`) y después
  `flask db upgrade` con la cadena de migraciones del repo. Las tablas base que
  esa cadena nunca crea salen del modelo del commit `47407ab^`, que es el
  último estado previo a la primera migración.
- Datos sintéticos (`seed_demo.py`): staging procesado con origen CARNES y
  LACTEOS, PRE y FAC, productos con y sin cajas o kilos, cliente consumidor final,
  vendedores con alias, un vendedor «Salón», objetivos históricos de RRHH y
  usuarios por rol.
- La app en `127.0.0.1:5055` con CSRF activo y gunicorn.

## Uso

```
scripts/dev_preview/run_local.sh up        # levanta todo (idempotente)
/root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_objetivos.py
scripts/dev_preview/run_local.sh down      # detiene la app y elimina el contenedor
```

Otros comandos: `seed`, `reset` (vacía y vuelve a sembrar), `app`, `restart`
y `status`.

El entorno de Python y Playwright vive en `/root/.cache/app360-e2e-venv`, fuera
del repo. `run_local.sh up` lo crea la primera vez. Las capturas, los informes
y los logs van a `/root/.hermes/cache/scratch/`, también fuera del repo.

## Seguridad del entorno

- `seed_demo.py` y `baseline_previa.py` se niegan a escribir si la URL no es
  `127.0.0.1:55432/app360_e2e`.
- Las contraseñas de este entorno son ficticias y válidas solo en la base local.
- `down` elimina únicamente el contenedor `app360-e2e-pg`.

## Informe del recorrido

`e2e_objetivos.py` escribe `informe.json` y capturas en `E2E_SHOTS_DIR`. Por
defecto reinicia los datos sintéticos antes de correr; `--sin-reset` conserva el
estado actual. Devuelve código 0 solo si todas las verificaciones pasan.
