#!/usr/bin/env bash

set -euo pipefail

echo "ERROR: aplicacion de dumps SQL completos deshabilitada por seguridad." >&2
echo "Use scripts/apply_db_migrations_to_vps.sh con revisiones Alembic explicitas." >&2
exit 2
