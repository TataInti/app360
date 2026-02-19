#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$ROOT_DIR/.env}"
DATABASE_URL="${DATABASE_URL:-}"
RELEASE_TAG="${1:-}"
RELEASE_BASE_DIR="${RELEASE_BASE_DIR:-$ROOT_DIR/backups/db-releases}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ Falta comando requerido: $1"
    exit 1
  fi
}

require_cmd pg_dump
require_cmd shasum
require_cmd git

if [[ -z "$DATABASE_URL" && -f "$LOCAL_ENV_FILE" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$LOCAL_ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
fi

if [[ -z "$DATABASE_URL" ]]; then
  echo "❌ No se pudo resolver DATABASE_URL local."
  echo "   Define DATABASE_URL o crea $LOCAL_ENV_FILE con DATABASE_URL=..."
  exit 1
fi

if [[ -z "$RELEASE_TAG" ]]; then
  RELEASE_TAG="$(date +%Y%m%d_%H%M%S)_$(git rev-parse --short HEAD 2>/dev/null || echo no_git)"
fi

RELEASE_DIR="$RELEASE_BASE_DIR/$RELEASE_TAG"
SQL_FILE="$RELEASE_DIR/db.sql"
SHA_FILE="$RELEASE_DIR/db.sql.sha256"
META_FILE="$RELEASE_DIR/release_meta.txt"

mkdir -p "$RELEASE_DIR"

echo "💾 Generando dump SQL local en $SQL_FILE"
pg_dump \
  --format=plain \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname="$DATABASE_URL" \
  --file="$SQL_FILE"

SQL_SHA="$(shasum -a 256 "$SQL_FILE" | awk '{print $1}')"
echo "$SQL_SHA  db.sql" > "$SHA_FILE"

{
  echo "release_tag=$RELEASE_TAG"
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo n/a)"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo n/a)"
  echo "database_url_source=$(if [[ -n "${DATABASE_URL:-}" ]]; then echo env_or_local_env; else echo unknown; fi)"
  echo "db_sql_sha256=$SQL_SHA"
} > "$META_FILE"

echo "✅ Release DB generado"
echo "   Carpeta: $RELEASE_DIR"
echo "   SQL: $SQL_FILE"
echo "   SHA256: $SHA_FILE"
echo "   Meta: $META_FILE"
echo ""
echo "Siguiente paso sugerido:"
echo "  git add $RELEASE_DIR"
echo "  git commit -m 'db: release $RELEASE_TAG'"
