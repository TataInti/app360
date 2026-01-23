#!/bin/bash
# Script wrapper para ejecutar la aplicación con entorno virtual activado

# Cambiar al directorio del proyecto
cd /var/www/app360

# Activar entorno virtual
source venv/bin/activate

# Establecer PYTHONPATH
export PYTHONPATH=/var/www/app360

# Ejecutar la aplicación
python app.py