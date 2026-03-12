#!/usr/bin/env bash
set -euo pipefail

# Sincroniza Goal.current_value con ventas PRE usando endpoint protegido por token.
# Uso:
#   SABIOGO_CRON_TOKEN=xxx bash scripts/sync_objetivos_pre_cron.sh
#   SABIOGO_CRON_TOKEN=xxx BASE_URL="https://app360.tu-dominio.com" PERIODO=2026-03 bash scripts/sync_objetivos_pre_cron.sh

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
TOKEN="${SABIOGO_CRON_TOKEN:-}"
PERIODO="${PERIODO:-$(date +%Y-%m)}"
ENDPOINT="${BASE_URL%/}/sabiogo/api/sync-objetivos-pre-cron"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: falta SABIOGO_CRON_TOKEN en entorno" >&2
  exit 2
fi

payload=$(printf '{"periodo":"%s"}' "$PERIODO")

response_file=$(mktemp)
http_code=$(curl -sS -o "$response_file" -w "%{http_code}" \
  -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "X-App360-Cron-Token: $TOKEN" \
  --data "$payload")

if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
  echo "ERROR: sync objetivos PRE fallo con HTTP $http_code" >&2
  cat "$response_file" >&2
  rm -f "$response_file"
  exit 1
fi

echo "OK: sync objetivos PRE ejecutado ($PERIODO)"
cat "$response_file"
rm -f "$response_file"
