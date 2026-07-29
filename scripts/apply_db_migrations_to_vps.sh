#!/usr/bin/env bash

set -euo pipefail

EXPECTED_CURRENT_REVISION="${1:-}"
EXPECTED_TARGET_REVISION="${2:-}"
VALIDATION_SQL_FILE="${3:-}"
PROD_SSH_USER="${PROD_SSH_USER:-root}"
PROD_SSH_HOST="${PROD_SSH_HOST:-}"
PROD_APP_DIR="${PROD_APP_DIR:-/var/www/app360}"
EXPECTED_GIT_SHA="${EXPECTED_GIT_SHA:-}"
RELEASE_TAG="${RELEASE_TAG:-}"
PRESERVE_TABLE="${PRESERVE_TABLE:-movimientos_caja}"
MAINTENANCE_CONFIRMED="${MAINTENANCE_CONFIRMED:-false}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -n "$PROD_SSH_HOST" ]] || fail "Falta PROD_SSH_HOST"
[[ "$MAINTENANCE_CONFIRMED" == "true" ]] || fail \
  "Falta MAINTENANCE_CONFIRMED=true: confirme que las escrituras estan pausadas"
[[ -n "$EXPECTED_GIT_SHA" ]] || fail "Falta EXPECTED_GIT_SHA completo"
[[ "$EXPECTED_GIT_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail "EXPECTED_GIT_SHA debe tener 40 caracteres"
[[ "$EXPECTED_CURRENT_REVISION" =~ ^[A-Za-z0-9_]+$ ]] || fail "Revision inicial invalida"
[[ "$EXPECTED_TARGET_REVISION" =~ ^[A-Za-z0-9_]+$ ]] || fail "Revision objetivo invalida"
[[ -z "$RELEASE_TAG" || "$RELEASE_TAG" =~ ^[A-Za-z0-9._-]+$ ]] || fail "RELEASE_TAG invalido"
[[ -z "$VALIDATION_SQL_FILE" || "$VALIDATION_SQL_FILE" =~ ^[A-Za-z0-9_./-]+$ ]] || fail "VALIDATION_SQL_FILE invalido"
[[ -z "$PRESERVE_TABLE" || "$PRESERVE_TABLE" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || fail "PRESERVE_TABLE invalida"

echo "Ejecutando migracion forward-only en $PROD_SSH_USER@$PROD_SSH_HOST"
echo "El script no reinicia App360."

ssh "$PROD_SSH_USER@$PROD_SSH_HOST" bash -s -- \
  "$PROD_APP_DIR" \
  "$EXPECTED_CURRENT_REVISION" \
  "$EXPECTED_TARGET_REVISION" \
  "$EXPECTED_GIT_SHA" \
  "$VALIDATION_SQL_FILE" \
  "$RELEASE_TAG" \
  "$PRESERVE_TABLE" \
  "$MAINTENANCE_CONFIRMED" <<'REMOTE'
set -euo pipefail

APP_DIR="$1"
EXPECTED_CURRENT_REVISION="$2"
EXPECTED_TARGET_REVISION="$3"
EXPECTED_GIT_SHA="$4"
VALIDATION_SQL_FILE="$5"
RELEASE_TAG="$6"
PRESERVE_TABLE="$7"
MAINTENANCE_CONFIRMED="$8"

cd "$APP_DIR"
EXPECTED_CURRENT_REVISION="$EXPECTED_CURRENT_REVISION" \
EXPECTED_TARGET_REVISION="$EXPECTED_TARGET_REVISION" \
EXPECTED_GIT_SHA="$EXPECTED_GIT_SHA" \
VALIDATION_SQL_FILE="$VALIDATION_SQL_FILE" \
RELEASE_TAG="$RELEASE_TAG" \
PRESERVE_TABLE="$PRESERVE_TABLE" \
MAINTENANCE_CONFIRMED="$MAINTENANCE_CONFIRMED" \
bash scripts/migrate_db_safely.sh
REMOTE
