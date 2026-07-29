#!/usr/bin/env bash

set -euo pipefail

echo "ERROR: flujo deshabilitado por seguridad." >&2
echo "Un pg_dump --clean no es una migracion diferencial y puede reemplazar datos productivos." >&2
echo "Versione las migraciones Alembic y use scripts/migrate_db_safely.sh." >&2
exit 2
