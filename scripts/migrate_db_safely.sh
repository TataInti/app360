#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-$ROOT_DIR}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/venv/bin/python}"
FLASK_BIN="${FLASK_BIN:-$APP_DIR/venv/bin/flask}"
PSQL_BIN="${PSQL_BIN:-psql}"
PG_DUMP_BIN="${PG_DUMP_BIN:-pg_dump}"
PG_RESTORE_BIN="${PG_RESTORE_BIN:-pg_restore}"
POSTGRES_DOCKER_CONTAINER="${POSTGRES_DOCKER_CONTAINER:-}"
POSTGRES_DOCKER_PASSWORD="${POSTGRES_DOCKER_PASSWORD:-}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/app360}"
EXPECTED_CURRENT_REVISION="${EXPECTED_CURRENT_REVISION:-}"
EXPECTED_TARGET_REVISION="${EXPECTED_TARGET_REVISION:-}"
EXPECTED_GIT_SHA="${EXPECTED_GIT_SHA:-}"
REQUIRE_CLEAN_GIT="${REQUIRE_CLEAN_GIT:-true}"
REQUIRE_GIT_SHA="${REQUIRE_GIT_SHA:-true}"
VERIFY_RESTORE="${VERIFY_RESTORE:-true}"
MAINTENANCE_CONFIRMED="${MAINTENANCE_CONFIRMED:-false}"
VALIDATION_SQL_FILE="${VALIDATION_SQL_FILE:-}"
PRESERVE_TABLE="${PRESERVE_TABLE:-}"
MIGRATION_DATABASE_URL="${DATABASE_URL:-}"
DATABASE_TOOL_URL="${DATABASE_TOOL_URL:-}"
ADMIN_DATABASE_URL="${ADMIN_DATABASE_URL:-}"
RELEASE_TAG="${RELEASE_TAG:-}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Falta comando requerido: $1"
}

is_true() {
  case "$1" in
    true|TRUE|True) return 0 ;;
    *) return 1 ;;
  esac
}

checksum_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1"
  else
    fail "Falta sha256sum o shasum"
  fi
}

run_psql() {
  if [[ -n "$POSTGRES_DOCKER_CONTAINER" ]]; then
    docker exec -i \
      -e PGPASSWORD="$POSTGRES_DOCKER_PASSWORD" \
      "$POSTGRES_DOCKER_CONTAINER" \
      psql "$@"
  else
    "$PSQL_BIN" "$@"
  fi
}

run_pg_dump() {
  if [[ -n "$POSTGRES_DOCKER_CONTAINER" ]]; then
    docker exec -i \
      -e PGPASSWORD="$POSTGRES_DOCKER_PASSWORD" \
      "$POSTGRES_DOCKER_CONTAINER" \
      pg_dump "$@"
  else
    "$PG_DUMP_BIN" "$@"
  fi
}

run_pg_restore() {
  if [[ -n "$POSTGRES_DOCKER_CONTAINER" ]]; then
    docker exec -i \
      -e PGPASSWORD="$POSTGRES_DOCKER_PASSWORD" \
      "$POSTGRES_DOCKER_CONTAINER" \
      pg_restore "$@"
  else
    "$PG_RESTORE_BIN" "$@"
  fi
}

[[ -n "$EXPECTED_CURRENT_REVISION" ]] || fail "Falta EXPECTED_CURRENT_REVISION"
[[ -n "$EXPECTED_TARGET_REVISION" ]] || fail "Falta EXPECTED_TARGET_REVISION"
is_true "$MAINTENANCE_CONFIRMED" || fail \
  "Falta MAINTENANCE_CONFIRMED=true: las escrituras deben estar pausadas"
[[ "$EXPECTED_CURRENT_REVISION" =~ ^[A-Za-z0-9_]+$ ]] || fail "Revision inicial invalida"
[[ "$EXPECTED_TARGET_REVISION" =~ ^[A-Za-z0-9_]+$ ]] || fail "Revision objetivo invalida"
[[ -d "$APP_DIR/.git" ]] || fail "APP_DIR no es un checkout Git: $APP_DIR"
[[ -x "$PYTHON_BIN" ]] || fail "No existe Python del venv: $PYTHON_BIN"
[[ -x "$FLASK_BIN" ]] || fail "No existe Flask del venv: $FLASK_BIN"

require_cmd git
if [[ -n "$POSTGRES_DOCKER_CONTAINER" ]]; then
  require_cmd docker
  [[ -n "$POSTGRES_DOCKER_PASSWORD" ]] || fail "Falta POSTGRES_DOCKER_PASSWORD"
  docker inspect "$POSTGRES_DOCKER_CONTAINER" >/dev/null 2>&1 || fail \
    "No existe el contenedor PostgreSQL: $POSTGRES_DOCKER_CONTAINER"
else
  require_cmd "$PSQL_BIN"
  require_cmd "$PG_DUMP_BIN"
  require_cmd "$PG_RESTORE_BIN"
fi

if [[ -z "$MIGRATION_DATABASE_URL" ]]; then
  [[ -f "$ENV_FILE" ]] || fail "No existe ENV_FILE: $ENV_FILE"
  MIGRATION_DATABASE_URL="$(
    "$PYTHON_BIN" - "$ENV_FILE" <<'PY'
from dotenv import dotenv_values
import sys

print(dotenv_values(sys.argv[1]).get("DATABASE_URL", ""))
PY
  )"
fi
[[ -n "$MIGRATION_DATABASE_URL" ]] || fail "DATABASE_URL esta vacia"
[[ "$MIGRATION_DATABASE_URL" == postgresql* ]] || fail "La migracion segura requiere PostgreSQL"
if [[ -z "$DATABASE_TOOL_URL" ]]; then
  DATABASE_TOOL_URL="$MIGRATION_DATABASE_URL"
fi
[[ "$DATABASE_TOOL_URL" == postgresql* ]] || fail "DATABASE_TOOL_URL debe apuntar a PostgreSQL"

cd "$APP_DIR"

if is_true "$REQUIRE_CLEAN_GIT"; then
  [[ -z "$(git status --porcelain)" ]] || fail "El checkout tiene cambios sin versionar"
fi

ACTUAL_GIT_SHA="$(git rev-parse HEAD)"
if is_true "$REQUIRE_GIT_SHA"; then
  [[ -n "$EXPECTED_GIT_SHA" ]] || fail "Falta EXPECTED_GIT_SHA"
  [[ "$EXPECTED_GIT_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail "EXPECTED_GIT_SHA debe ser un SHA completo"
  [[ "$ACTUAL_GIT_SHA" == "$EXPECTED_GIT_SHA" ]] || fail "El checkout no coincide con EXPECTED_GIT_SHA"
fi

CURRENT_ROWS="$(run_psql -X -At --dbname="$DATABASE_TOOL_URL" -c "SELECT count(*) FROM alembic_version;")"
[[ "$CURRENT_ROWS" == "1" ]] || fail "alembic_version debe tener exactamente una fila; tiene $CURRENT_ROWS"
CURRENT_REVISION="$(run_psql -X -At --dbname="$DATABASE_TOOL_URL" -c "SELECT version_num FROM alembic_version;")"
[[ "$CURRENT_REVISION" == "$EXPECTED_CURRENT_REVISION" ]] || fail \
  "Revision actual inesperada: $CURRENT_REVISION (esperada: $EXPECTED_CURRENT_REVISION)"

ALEMBIC_HEADS_OUTPUT="$("$FLASK_BIN" db heads 2>&1 | awk '/\(head\)$/{print $1}')"
ALEMBIC_HEAD_COUNT="$(printf '%s\n' "$ALEMBIC_HEADS_OUTPUT" | awk 'NF{count++} END{print count+0}')"
[[ "$ALEMBIC_HEAD_COUNT" == "1" ]] || fail "Alembic debe tener una unica cabecera"
ALEMBIC_HEAD="$(printf '%s\n' "$ALEMBIC_HEADS_OUTPUT" | awk 'NF{print; exit}')"
[[ "$ALEMBIC_HEAD" == "$EXPECTED_TARGET_REVISION" ]] || fail \
  "Cabecera Alembic inesperada: $ALEMBIC_HEAD (esperada: $EXPECTED_TARGET_REVISION)"

if [[ -n "$PRESERVE_TABLE" ]]; then
  [[ "$PRESERVE_TABLE" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || fail "PRESERVE_TABLE invalida"
  PRESERVED_COUNT_BEFORE="$(run_psql -X -At --dbname="$DATABASE_TOOL_URL" -c "SELECT count(*) FROM \"$PRESERVE_TABLE\";")"
else
  PRESERVED_COUNT_BEFORE=""
fi

if [[ -z "$RELEASE_TAG" ]]; then
  RELEASE_TAG="$(date -u +%Y%m%d_%H%M%S)_${EXPECTED_TARGET_REVISION}"
fi
[[ "$RELEASE_TAG" =~ ^[A-Za-z0-9._-]+$ ]] || fail "RELEASE_TAG invalido"

RELEASE_DIR="$BACKUP_ROOT/$RELEASE_TAG"
BACKUP_FILE="$RELEASE_DIR/pre_migration.dump"
CHECKSUM_FILE="$BACKUP_FILE.sha256"
MANIFEST_FILE="$RELEASE_DIR/migration_manifest.txt"
[[ ! -e "$RELEASE_DIR" ]] || fail "Ya existe el directorio de release: $RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
chmod 700 "$RELEASE_DIR"

echo "Creando backup pre-migracion en $BACKUP_FILE"
run_pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --dbname="$DATABASE_TOOL_URL" > "$BACKUP_FILE"
checksum_file "$BACKUP_FILE" > "$CHECKSUM_FILE"
run_pg_restore -l < "$BACKUP_FILE" >/dev/null

{
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_sha=$ACTUAL_GIT_SHA"
  echo "revision_before=$CURRENT_REVISION"
  echo "revision_target=$EXPECTED_TARGET_REVISION"
  echo "backup_file=$BACKUP_FILE"
  echo "backup_sha256=$(awk '{print $1}' "$CHECKSUM_FILE")"
  if [[ -n "$PRESERVE_TABLE" ]]; then
    echo "preserve_table=$PRESERVE_TABLE"
    echo "preserve_count_before=$PRESERVED_COUNT_BEFORE"
  fi
} > "$MANIFEST_FILE"

VERIFY_DB_CREATED=false
VERIFY_DATABASE_NAME=""
VERIFY_MODE=""

cleanup_verify_database() {
  if [[ "$VERIFY_DB_CREATED" != "true" || -z "$VERIFY_DATABASE_NAME" ]]; then
    return
  fi
  if [[ "$VERIFY_MODE" == "url" ]]; then
    run_psql -X --dbname="$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 \
      -c "DROP DATABASE IF EXISTS \"$VERIFY_DATABASE_NAME\";" >/dev/null || true
  elif [[ "$VERIFY_MODE" == "os-postgres" ]]; then
    sudo -u postgres dropdb --if-exists "$VERIFY_DATABASE_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup_verify_database EXIT INT TERM

if is_true "$VERIFY_RESTORE"; then
  VERIFY_DATABASE_NAME="app360_verify_$(date -u +%Y%m%d_%H%M%S)_$$"
  [[ "$VERIFY_DATABASE_NAME" =~ ^[a-z0-9_]+$ ]] || fail "Nombre temporal invalido"

  if [[ -n "$ADMIN_DATABASE_URL" ]]; then
    VERIFY_MODE="url"
    run_psql -X --dbname="$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 \
      -c "CREATE DATABASE \"$VERIFY_DATABASE_NAME\";" >/dev/null
    VERIFY_DB_CREATED=true
    VERIFY_DATABASE_URL="$(
      "$PYTHON_BIN" - "$ADMIN_DATABASE_URL" "$VERIFY_DATABASE_NAME" <<'PY'
from sqlalchemy.engine import make_url
import sys

print(
    make_url(sys.argv[1])
    .set(database=sys.argv[2])
    .render_as_string(hide_password=False)
)
PY
    )"
    run_pg_restore --exit-on-error --no-owner --no-privileges \
      --dbname="$VERIFY_DATABASE_URL" < "$BACKUP_FILE"
    RESTORED_REVISION="$(run_psql -X -At --dbname="$VERIFY_DATABASE_URL" -c "SELECT version_num FROM alembic_version;")"
  elif [[ "$(id -u)" == "0" ]] && command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    VERIFY_MODE="os-postgres"
    sudo -u postgres createdb "$VERIFY_DATABASE_NAME"
    VERIFY_DB_CREATED=true
    sudo -u postgres "$PG_RESTORE_BIN" --exit-on-error --no-owner --no-privileges \
      --dbname="$VERIFY_DATABASE_NAME" < "$BACKUP_FILE"
    RESTORED_REVISION="$(sudo -u postgres "$PSQL_BIN" -X -At --dbname="$VERIFY_DATABASE_NAME" -c "SELECT version_num FROM alembic_version;")"
  else
    fail "VERIFY_RESTORE=true requiere ADMIN_DATABASE_URL o ejecucion root con usuario postgres"
  fi

  [[ "$RESTORED_REVISION" == "$EXPECTED_CURRENT_REVISION" ]] || fail \
    "El restore de ensayo no conserva la revision esperada"
  cleanup_verify_database
  VERIFY_DB_CREATED=false
  echo "Restore de ensayo verificado"
fi

echo "Aplicando Alembic hasta $EXPECTED_TARGET_REVISION"
DATABASE_URL="$MIGRATION_DATABASE_URL" "$FLASK_BIN" db upgrade "$EXPECTED_TARGET_REVISION"

FINAL_ROWS="$(run_psql -X -At --dbname="$DATABASE_TOOL_URL" -c "SELECT count(*) FROM alembic_version;")"
[[ "$FINAL_ROWS" == "1" ]] || fail "alembic_version quedo con $FINAL_ROWS filas"
FINAL_REVISION="$(run_psql -X -At --dbname="$DATABASE_TOOL_URL" -c "SELECT version_num FROM alembic_version;")"
[[ "$FINAL_REVISION" == "$EXPECTED_TARGET_REVISION" ]] || fail \
  "Revision final inesperada: $FINAL_REVISION"

if [[ -n "$PRESERVE_TABLE" ]]; then
  PRESERVED_COUNT_AFTER="$(run_psql -X -At --dbname="$DATABASE_TOOL_URL" -c "SELECT count(*) FROM \"$PRESERVE_TABLE\";")"
  [[ "$PRESERVED_COUNT_AFTER" == "$PRESERVED_COUNT_BEFORE" ]] || fail \
    "$PRESERVE_TABLE cambio de $PRESERVED_COUNT_BEFORE a $PRESERVED_COUNT_AFTER filas"
  echo "preserve_count_after=$PRESERVED_COUNT_AFTER" >> "$MANIFEST_FILE"
fi

if [[ -n "$VALIDATION_SQL_FILE" ]]; then
  if [[ "$VALIDATION_SQL_FILE" != /* ]]; then
    VALIDATION_SQL_FILE="$APP_DIR/$VALIDATION_SQL_FILE"
  fi
  [[ -f "$VALIDATION_SQL_FILE" ]] || fail "No existe VALIDATION_SQL_FILE: $VALIDATION_SQL_FILE"
  run_psql -X --dbname="$DATABASE_TOOL_URL" -v ON_ERROR_STOP=1 \
    < "$VALIDATION_SQL_FILE"
fi

{
  echo "completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "revision_after=$FINAL_REVISION"
  echo "restore_verified=$VERIFY_RESTORE"
} >> "$MANIFEST_FILE"

trap - EXIT INT TERM
echo "Migracion segura completada. Backup conservado en $BACKUP_FILE"
echo "El servicio de aplicacion no fue reiniciado."
