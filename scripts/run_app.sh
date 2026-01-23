#!/bin/bash
# Script wrapper para ejecutar la aplicación con entorno virtual activado

# Cambiar al directorio del proyecto
cd /var/www/app360

# Activar entorno virtual y ejecutar en el mismo shell
exec /var/www/app360/venv/bin/python -c "
import os
import sys
sys.path.insert(0, '/var/www/app360')

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Ejecutar la aplicación
from app import app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
"