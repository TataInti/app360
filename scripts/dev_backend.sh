#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/venv/bin/python"
  elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "❌ No se encontró Python (python3)."
    exit 1
  fi
fi

export FLASK_ENV="${FLASK_ENV:-development}"
export DEBUG="${DEBUG:-True}"

# Defaults de desarrollo (podés overridearlos exportando env vars antes)
export DATABASE_URL="${DATABASE_URL:-postgresql://app360:password@localhost:5432/app360}"
export SECRET_KEY="${SECRET_KEY:-dev-secret}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

ensure_postgres() {
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    return 0
  fi

  if ! command -v brew >/dev/null 2>&1; then
    echo "❌ PostgreSQL no responde en localhost:5432 y no encuentro Homebrew para arrancarlo."
    echo "   Instala/arranca PostgreSQL y reintenta."
    exit 1
  fi

  # Intentar arrancar Postgres por Homebrew (la app usa psql 14 actualmente)
  brew services start postgresql@14 >/dev/null 2>&1 || true
  sleep 1

  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    return 0
  fi

  echo "❌ No pude arrancar PostgreSQL en localhost:5432 (brew services postgresql@14)."
  echo "   Tip: revisá el log: /usr/local/var/log/postgresql@14.log"
  exit 1
}

ensure_app_db() {
  if ! command -v psql >/dev/null 2>&1; then
    echo "❌ Falta psql (cliente PostgreSQL). Instalalo con Homebrew: brew install postgresql@14"
    exit 1
  fi

  # Crear rol y DB si no existen. Usamos heredoc quoted para evitar expansión de $$.
  psql -d postgres -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app360') THEN
    CREATE ROLE app360 LOGIN PASSWORD 'password';
  END IF;
END$$;
SQL

  if ! psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='app360';" | grep -q 1; then
    createdb -O app360 app360
  fi
}

echo "🟢 Backend dev: verificando PostgreSQL..."
ensure_postgres
ensure_app_db

echo "🟢 Backend dev: creando tablas (si faltan)..."
"$PYTHON_BIN" scripts/setup_database.py

echo "🟢 Backend dev: levantando Flask en http://127.0.0.1:5001 ..."
exec "$PYTHON_BIN" app.py
