#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_TAG="${1:-}"
RELEASE_BASE_DIR="${RELEASE_BASE_DIR:-$ROOT_DIR/backups/db-releases}"
PROD_SSH_USER="${PROD_SSH_USER:-root}"
PROD_SSH_HOST="${PROD_SSH_HOST:-}"
PROD_APP_DIR="${PROD_APP_DIR:-/var/www/app360}"
PROD_ENV_FILE="${PROD_ENV_FILE:-$PROD_APP_DIR/.env}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ Falta comando requerido: $1"
    exit 1
  fi
}

require_cmd ssh
require_cmd shasum

if [[ -z "$RELEASE_TAG" ]]; then
  echo "❌ Falta RELEASE_TAG. Uso:"
  echo "   bash scripts/apply_db_release_to_vps.sh <release_tag>"
  exit 1
fi

if [[ -z "$PROD_SSH_HOST" ]]; then
  echo "❌ Falta PROD_SSH_HOST (host/IP del VPS)."
  echo "   Ej: PROD_SSH_HOST=vyp.app360.com.ar bash scripts/apply_db_release_to_vps.sh <release_tag>"
  exit 1
fi

RELEASE_DIR="$RELEASE_BASE_DIR/$RELEASE_TAG"
SQL_FILE="$RELEASE_DIR/db.sql"
SHA_FILE="$RELEASE_DIR/db.sql.sha256"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "❌ No existe $SQL_FILE"
  exit 1
fi

if [[ ! -f "$SHA_FILE" ]]; then
  echo "❌ No existe $SHA_FILE"
  exit 1
fi

EXPECTED_SHA="$(awk '{print $1}' "$SHA_FILE")"
CURRENT_SHA="$(shasum -a 256 "$SQL_FILE" | awk '{print $1}')"

if [[ "$EXPECTED_SHA" != "$CURRENT_SHA" ]]; then
  echo "❌ SHA256 no coincide para $SQL_FILE"
  echo "   expected=$EXPECTED_SHA"
  echo "   current=$CURRENT_SHA"
  exit 1
fi

echo "🚀 Aplicando release $RELEASE_TAG en $PROD_SSH_USER@$PROD_SSH_HOST"
ssh "$PROD_SSH_USER@$PROD_SSH_HOST" "bash -lc '
  set -e
  test -f "$PROD_ENV_FILE" || { echo "No existe $PROD_ENV_FILE"; exit 2; }
  set -a
  source "$PROD_ENV_FILE" >/dev/null 2>&1
  set +a
  test -n "\$DATABASE_URL" || { echo "DATABASE_URL vacío en VPS"; exit 3; }
  psql --set ON_ERROR_STOP=1 --dbname="\$DATABASE_URL" --file=-
'" < "$SQL_FILE"

echo "✅ Release aplicada en VPS"
