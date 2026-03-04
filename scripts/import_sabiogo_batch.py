#!/usr/bin/env python3
"""Importa un batch SabioGo desde filesystem (6 archivos + manifest).

Uso:
  /path/venv/bin/python scripts/import_sabiogo_batch.py /ruta/al/batch_dir

El batch_dir debe contener:
  - manifest.json
  - los archivos declarados en el manifest

Este script es intencionalmente simple para integrarlo con PowerShell/cron.
"""

import os
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from services.sabiogo_batch_importer import process_batch


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/import_sabiogo_batch.py <batch_dir>")
        return 2

    batch_dir = sys.argv[1]
    if not os.path.isdir(batch_dir):
        print(f"batch_dir no existe o no es directorio: {batch_dir}")
        return 2

    app = create_app()
    with app.app_context():
        result = process_batch(batch_dir)
        print(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
