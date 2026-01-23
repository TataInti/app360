#!/bin/bash
# Script wrapper para ejecutar la aplicación con entorno virtual activado

# Ejecutar en una subshell que mantenga el entorno
bash -c "
cd /var/www/app360
source venv/bin/activate
export PYTHONPATH=/var/www/app360
exec python app.py
"