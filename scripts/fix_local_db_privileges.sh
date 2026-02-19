#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$ROOT_DIR/.env}"
LOCAL_ADMIN_DATABASE_URL="${LOCAL_ADMIN_DATABASE_URL:-}"
TARGET_ROLE="${TARGET_ROLE:-app360user}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ Falta comando requerido: $1"
    exit 1
  fi
}

require_cmd psql

if [[ -z "$LOCAL_ADMIN_DATABASE_URL" && -f "$LOCAL_ENV_FILE" ]]; then
  # Si no se especifica, intentamos usar conexión por socket al mismo nombre de DB,
  # asumiendo que el usuario del SO tiene permisos.
  db_name="$(grep -E '^DATABASE_URL=' "$LOCAL_ENV_FILE" | tail -n1 | cut -d= -f2- | sed -E 's#^.*/##; s#\?.*$##' || true)"
  if [[ -n "$db_name" ]]; then
    LOCAL_ADMIN_DATABASE_URL="postgresql:///$db_name?user=$(whoami)"
  fi
fi

if [[ -z "$LOCAL_ADMIN_DATABASE_URL" ]]; then
  echo "❌ No se pudo resolver LOCAL_ADMIN_DATABASE_URL."
  echo "   Uso: LOCAL_ADMIN_DATABASE_URL='postgresql:///app360?user=postgres' bash scripts/fix_local_db_privileges.sh"
  exit 1
fi

echo "🔐 Aplicando permisos en schema public para rol '$TARGET_ROLE'..."
psql -w "$LOCAL_ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -c "GRANT USAGE ON SCHEMA public TO ${TARGET_ROLE};" \
  -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${TARGET_ROLE};" \
  -c "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO ${TARGET_ROLE};" \
  -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${TARGET_ROLE};" \
  -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO ${TARGET_ROLE};"

echo "👑 Asegurando ownership de vistas materializadas (necesario para REFRESH)..."
psql -w "$LOCAL_ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 <<SQL
DO $$
DECLARE
  mv record;
BEGIN
  FOR mv IN
    SELECT schemaname, matviewname
    FROM pg_matviews
    WHERE schemaname = 'public'
      AND matviewname IN ('fact_ventas_sabiogo', 'fact_costos_sabiogo')
  LOOP
    EXECUTE format('ALTER MATERIALIZED VIEW %I.%I OWNER TO %I', mv.schemaname, mv.matviewname, '${TARGET_ROLE}');
  END LOOP;
END $$;
SQL

echo "✅ Permisos aplicados"
