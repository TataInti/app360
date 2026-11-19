#!/usr/bin/env bash
# Entorno E2E local de App360 para la pantalla de objetivos comerciales.
#
# Solo local: PostgreSQL 16 efímero en el contenedor app360-e2e-pg
# (127.0.0.1:55432, base app360_e2e) y la app en 127.0.0.1:5055 con CSRF activo.
# Datos sintéticos. No usa ni toca otros contenedores ni bases.
#
# Uso:
#   scripts/dev_preview/run_local.sh up       levanta todo (idempotente)
#   scripts/dev_preview/run_local.sh seed     siembra si la base está vacía
#   scripts/dev_preview/run_local.sh reset    vacía las tablas sintéticas y vuelve a sembrar
#   scripts/dev_preview/run_local.sh app      arranca solo la app
#   scripts/dev_preview/run_local.sh restart  reinicia la app (recalcula la versión de estáticos)
#   scripts/dev_preview/run_local.sh status   estado del contenedor y de la app
#   scripts/dev_preview/run_local.sh down     detiene la app y elimina el contenedor
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREVIEW_DIR="$ROOT_DIR/scripts/dev_preview"
VENV="${E2E_VENV:-/root/.cache/app360-e2e-venv}"
UV_BIN="${UV_BIN:-/root/.local/bin/uv}"
SCRATCH="${E2E_SCRATCH_DIR:-/root/.hermes/cache/scratch}"
LOCK_FILE="${E2E_HEAVY_LOCK:-$SCRATCH/heavy.lock}"
STATE_DIR="$SCRATCH/e2e-state"
LOG_DIR="$SCRATCH/e2e-logs"
SHOTS_DIR="$SCRATCH/e2e-shots"
PIDFILE="$STATE_DIR/gunicorn.pid"

PG_CONTAINER="app360-e2e-pg"
PG_IMAGE="postgres:16"
PG_HOST="127.0.0.1"
PG_PORT="55432"
PG_DB="app360_e2e"
PG_USER="app360_e2e"
# Valores de prueba SOLO-DEV del entorno E2E local (127.0.0.1, datos sintéticos).
# No son credenciales de producción. Para cambiarlos, exportá E2E_PG_PASSWORD,
# E2E_SECRET_KEY o E2E_ADMIN_PASSWORD antes de correr el script.
PG_PASSWORD="${E2E_PG_PASSWORD:-app360_e2e_local_ficticia}"
DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@${PG_HOST}:${PG_PORT}/${PG_DB}"

APP_HOST="127.0.0.1"
APP_PORT="5055"
SECRET_KEY="${E2E_SECRET_KEY:-e2e-local-secret-ficticio}"
ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-admin-ficticio}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

env_app() {
  export DATABASE_URL SECRET_KEY ADMIN_PASSWORD
  export FLASK_ENV=development DEBUG=False WTF_CSRF_ENABLED=True
  export LOG_FILE="$LOG_DIR/app.log" SECURITY_LOG_FILE="$LOG_DIR/security.log" LOG_FORMAT=json
  export E2E_SCRATCH_DIR="$SCRATCH" PYTHONDONTWRITEBYTECODE=1
  mkdir -p "$STATE_DIR" "$LOG_DIR" "$SHOTS_DIR"
}

_venv_install() {
  # Invocado solo bajo flock desde setup_venv.
  "$UV_BIN" venv --python 3.12 "$VENV"
  "$UV_BIN" pip install --python "$VENV/bin/python" -r "$ROOT_DIR/requirements.txt" playwright
}

setup_venv() {
  if [[ -x "$VENV/bin/python" ]]; then
    return 0
  fi
  [[ -x "$UV_BIN" ]] || fail "Falta uv en $UV_BIN (definí UV_BIN)."
  mkdir -p "$(dirname "$LOCK_FILE")"
  flock "$LOCK_FILE" "$0" _venv_install
}

db_up() {
  command -v docker >/dev/null 2>&1 || fail "Falta docker."
  if ! docker image inspect "$PG_IMAGE" >/dev/null 2>&1; then
    mkdir -p "$(dirname "$LOCK_FILE")"
    flock "$LOCK_FILE" docker pull "$PG_IMAGE"
  fi
  if docker container inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    docker start "$PG_CONTAINER" >/dev/null
  else
    docker run -d --name "$PG_CONTAINER" \
      -p "${PG_HOST}:${PG_PORT}:5432" \
      -e POSTGRES_USER="$PG_USER" \
      -e POSTGRES_PASSWORD="$PG_PASSWORD" \
      -e POSTGRES_DB="$PG_DB" \
      "$PG_IMAGE" >/dev/null
  fi
  # La imagen oficial arranca primero un servidor temporal que escucha solo por socket Unix.
  # Por eso se comprueba por TCP y se confirma dos veces: el servidor definitivo recién queda
  # listo en TCP después del reinicio.
  for _ in $(seq 1 60); do
    if docker exec "$PG_CONTAINER" pg_isready -h 127.0.0.1 -p 5432 -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
      sleep 2
      if docker exec "$PG_CONTAINER" pg_isready -h 127.0.0.1 -p 5432 -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
        echo "PG_OK ${PG_HOST}:${PG_PORT}/${PG_DB}"
        return 0
      fi
    fi
    sleep 1
  done
  fail "PostgreSQL no respondió en ${PG_HOST}:${PG_PORT}."
}

schema() {
  env_app
  (cd "$ROOT_DIR" && "$VENV/bin/python" "$PREVIEW_DIR/baseline_previa.py")
  (cd "$ROOT_DIR" && "$VENV/bin/flask" db upgrade)
  (cd "$ROOT_DIR" && "$VENV/bin/flask" db current | tail -1)
}

seed_run() {
  env_app
  local args=()
  if [[ "${1:-}" == "--reset" ]]; then
    args=(--reset)
  fi
  (cd "$ROOT_DIR" && "$VENV/bin/python" "$PREVIEW_DIR/seed_demo.py" "${args[@]}")
}

app_running() {
  [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

app_start() {
  env_app
  if app_running; then
    echo "APP_YA_ACTIVA pid=$(cat "$PIDFILE")"
  else
    if ss -ltn 2>/dev/null | grep -q ":${APP_PORT} "; then
      fail "El puerto ${APP_PORT} ya está en uso por otro proceso."
    fi
    "$VENV/bin/gunicorn" \
      --chdir "$ROOT_DIR" \
      --bind "${APP_HOST}:${APP_PORT}" \
      --workers 2 \
      --timeout 180 \
      --pid "$PIDFILE" \
      --daemon \
      --access-logfile "$LOG_DIR/gunicorn-access.log" \
      --error-logfile "$LOG_DIR/gunicorn-error.log" \
      "app:create_app()"
  fi
  for _ in $(seq 1 60); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://${APP_HOST}:${APP_PORT}/" || true)"
    if [[ "$code" == "200" ]]; then
      echo "APP_OK http://${APP_HOST}:${APP_PORT}/ (200)"
      return 0
    fi
    sleep 1
  done
  fail "La app no respondió 200 en ${APP_PORT}. Revisá $LOG_DIR/gunicorn-error.log"
}

app_stop() {
  if app_running; then
    local pid
    pid="$(cat "$PIDFILE")"
    kill -TERM "$pid"
    for _ in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    echo "APP_DETENIDA pid=$pid"
  else
    echo "APP_NO_ESTABA_ACTIVA"
  fi
  rm -f "$PIDFILE"
}

restart_app() {
  app_stop
  app_start
}

status() {
  if docker container inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    echo "PG: $(docker inspect -f '{{.State.Status}}' "$PG_CONTAINER") ${PG_HOST}:${PG_PORT}"
  else
    echo "PG: no existe el contenedor $PG_CONTAINER"
  fi
  if app_running; then
    echo "APP: pid $(cat "$PIDFILE") en ${APP_HOST}:${APP_PORT} (HTTP $(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://${APP_HOST}:${APP_PORT}/" || echo sin-respuesta))"
  else
    echo "APP: detenida"
  fi
}

down() {
  app_stop
  if docker container inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    docker rm -f "$PG_CONTAINER" >/dev/null
    echo "PG_ELIMINADO $PG_CONTAINER"
  fi
  # setup_logging crea logs/ dentro del repo; los archivos reales van a LOG_DIR.
  if [[ -d "$ROOT_DIR/logs" ]]; then
    rmdir "$ROOT_DIR/logs" 2>/dev/null || true
  fi
}

up() {
  setup_venv
  db_up
  schema
  seed_run
  app_start
  status
}

case "${1:-}" in
  up) up ;;
  seed) seed_run ;;
  reset) seed_run --reset ;;
  app) app_start ;;
  restart) restart_app ;;
  status) status ;;
  down) down ;;
  _venv_install) _venv_install ;;
  *)
    echo "Uso: $0 {up|seed|reset|app|status|down}" >&2
    exit 2
    ;;
esac
