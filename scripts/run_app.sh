#!/bin/bash
# Script wrapper para ejecutar la aplicación con entorno virtual activado

cd /var/www/app360
source venv/bin/activate
export PYTHONPATH=/var/www/app360
python app.py