#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROD_SSH_USER="${PROD_SSH_USER:-root}"
PROD_SSH_HOST="${PROD_SSH_HOST:-}"
PROD_APP_DIR="${PROD_APP_DIR:-/var/www/app360}"
PROD_ENV_FILE="${PROD_ENV_FILE:-$PROD_APP_DIR/.env}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$ROOT_DIR/.env}"
LOCAL_DATABASE_URL="${LOCAL_DATABASE_URL:-}"
APP360_BACKUP_ROOT="${APP360_BACKUP_ROOT:-$HOME/.app360/backups}"
BACKUP_DIR="${BACKUP_DIR:-$APP360_BACKUP_ROOT/db-sync}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PROD_DUMP_FILE="$BACKUP_DIR/prod_${TIMESTAMP}.sql"
LOCAL_BACKUP_FILE="$BACKUP_DIR/local_before_sync_${TIMESTAMP}.dump"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ Falta comando requerido: $1"
    exit 1
  fi
}

require_cmd ssh
require_cmd pg_dump
require_cmd pg_restore
require_cmd psql

mkdir -p "$BACKUP_DIR"

if [[ -z "$PROD_SSH_HOST" ]]; then
  echo "❌ Falta PROD_SSH_HOST (host/IP del VPS)."
  echo "   Ej: PROD_SSH_HOST=vyp.app360.com.ar bash scripts/sync_prod_db_to_local.sh"
  exit 1
fi

if [[ -z "$LOCAL_DATABASE_URL" && -f "$LOCAL_ENV_FILE" ]]; then
  LOCAL_DATABASE_URL="$(grep -E '^DATABASE_URL=' "$LOCAL_ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
fi

if [[ -z "$LOCAL_DATABASE_URL" ]]; then
  echo "❌ No se pudo resolver LOCAL_DATABASE_URL."
  echo "   Defínelo en variable de entorno o en $LOCAL_ENV_FILE (DATABASE_URL=...)"
  exit 1
fi

if [[ "$LOCAL_DATABASE_URL" != postgresql* ]]; then
  echo "❌ LOCAL_DATABASE_URL no apunta a PostgreSQL: $LOCAL_DATABASE_URL"
  exit 1
fi

echo "🔎 Verificando conexión SSH a producción ($PROD_SSH_USER@$PROD_SSH_HOST)..."
ssh -o ConnectTimeout=10 "$PROD_SSH_USER@$PROD_SSH_HOST" "echo SSH_OK" >/dev/null

echo "🔐 Validando DATABASE_URL en entorno productivo ($PROD_ENV_FILE)..."
ssh "$PROD_SSH_USER@$PROD_SSH_HOST" "bash -lc 'test -f \"$PROD_ENV_FILE\" || { echo \"No existe $PROD_ENV_FILE\"; exit 2; }; set -a; source \"$PROD_ENV_FILE\" >/dev/null 2>&1; set +a; test -n \"\$DATABASE_URL\" || { echo \"DATABASE_URL vacío en producción\"; exit 3; }'"

echo "💾 Generando backup local previo en $LOCAL_BACKUP_FILE ..."
pg_dump --format=custom --no-owner --no-privileges --dbname="$LOCAL_DATABASE_URL" --file="$LOCAL_BACKUP_FILE"

echo "⬇️  Descargando dump SQL de producción a $PROD_DUMP_FILE ..."
ssh "$PROD_SSH_USER@$PROD_SSH_HOST" "bash -lc 'set -a; source \"$PROD_ENV_FILE\" >/dev/null 2>&1; set +a; pg_dump --format=plain --no-owner --no-privileges --dbname=\"\$DATABASE_URL\"'" > "$PROD_DUMP_FILE"

echo "♻️  Restaurando SQL de producción sobre base local..."
psql --set ON_ERROR_STOP=1 --dbname="$LOCAL_DATABASE_URL" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
psql --set ON_ERROR_STOP=1 --dbname="$LOCAL_DATABASE_URL" --file="$PROD_DUMP_FILE"

echo "✅ Sincronización completada"
echo "   Backup local previo: $LOCAL_BACKUP_FILE"
echo "   Dump de producción: $PROD_DUMP_FILE"
