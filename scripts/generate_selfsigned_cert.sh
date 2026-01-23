#!/usr/bin/env bash
set -euo pipefail

# Generates a self-signed certificate + key for app360.actioconsultores.com or
# for the hostname provided via DOMAIN. This is only meant for internal use
# (staging, demos) because it will not be trusted by browsers without installing
# the cert.

DOMAIN="${DOMAIN:-app360.actioconsultores.com}"
OUT_DIR="${OUT_DIR:-instance/certs}"
CRT_PATH="${OUT_DIR}/${DOMAIN}.crt"
KEY_PATH="${OUT_DIR}/${DOMAIN}.key"

mkdir -p "$OUT_DIR"

cat <<EOF
Generating self-signed certificate for "$DOMAIN"
  - certificate: $CRT_PATH
  - key:         $KEY_PATH
EOF

# openssl req reads from stdin for the subject; we keep it minimal since we're
# automating. You can customize or prompt if you want more fields.
openssl req -new -x509 -nodes -sha256 \
    -days 365 \
    -subj "/CN=${DOMAIN}" \
    -keyout "$KEY_PATH" \
    -out "$CRT_PATH"

echo "Done. Please point your Nginx SSL configuration to the generated files."
