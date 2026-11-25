"""Esquema previo a la cadena de migraciones, para la base E2E local.

La cadena de Alembic empieza en 0dd692d555b0 (commit 47407ab). Esa migración y
las siguientes asumen tablas que ya existían antes: users, employees, proveedor,
adelantos, etc. Ninguna migración las crea. En producción esas tablas nacieron
con db.create_all() cuando todavía no existía migrations/.

Este script reconstruye ese estado inicial desde los modelos del commit anterior
a la primera migración (47407ab^), extraídos con `git archive` a un directorio
temporal. No usa los modelos actuales. Después, `flask db upgrade` aplica la
cadena vigente del repo sobre esa base.

Solo opera sobre 127.0.0.1:55432/app360_e2e y no usa datos reales.

Uso (desde la raíz del repo):
    python scripts/dev_preview/baseline_previa.py
"""

import os
import subprocess
import sys
import tempfile

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COMMIT_PREVIO_A_MIGRACIONES = "47407ab^"
HOST_PERMITIDO = {"127.0.0.1", "localhost"}
PUERTO_PERMITIDO = 55432
# Una instancia aislada puede usar otra base del mismo contenedor local (E2E_PG_DB).
NOMBRE_BASE_PERMITIDO = os.environ.get("E2E_PG_DB", "app360_e2e")
TABLA_CONTROL = "users"


def verificar_base_local(url: str) -> None:
    if not url:
        raise SystemExit("DATABASE_URL no está definida.")
    parsed = make_url(url)
    if parsed.host not in HOST_PERMITIDO or parsed.port != PUERTO_PERMITIDO:
        raise SystemExit(
            f"Rechazado: solo se admite 127.0.0.1:55432. Recibido: {parsed.host}:{parsed.port}"
        )
    if parsed.database != NOMBRE_BASE_PERMITIDO:
        raise SystemExit(f"Rechazado: la base debe llamarse {NOMBRE_BASE_PERMITIDO}.")


def _extraer_modelos(destino: str) -> None:
    archivo = os.path.join(destino, "_modelos.tar")
    with open(archivo, "wb") as salida:
        subprocess.run(
            ["git", "-C", REPO_ROOT, "archive", COMMIT_PREVIO_A_MIGRACIONES, "models"],
            check=True,
            stdout=salida,
        )
    subprocess.run(["tar", "-x", "-f", archivo, "-C", destino], check=True)
    os.remove(archivo)


def _borrar_arbol(raiz: str) -> None:
    for ruta, carpetas, archivos in os.walk(raiz, topdown=False):
        for nombre in archivos:
            os.remove(os.path.join(ruta, nombre))
        for nombre in carpetas:
            os.rmdir(os.path.join(ruta, nombre))
    os.rmdir(raiz)


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    verificar_base_local(url)

    from sqlalchemy import create_engine

    engine = create_engine(url)
    try:
        tablas = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    if TABLA_CONTROL in tablas:
        print("BASELINE_OMITIDA: la base ya tiene tablas previas a las migraciones.")
        return 0

    scratch = os.environ.get("E2E_SCRATCH_DIR") or tempfile.gettempdir()
    os.makedirs(scratch, exist_ok=True)
    directorio = tempfile.mkdtemp(prefix="app360-baseline-", dir=scratch)
    try:
        _extraer_modelos(directorio)
        sys.path.insert(0, directorio)
        from flask import Flask

        from models import db

        app = Flask("app360_baseline")
        app.config["SQLALCHEMY_DATABASE_URI"] = url
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)
        with app.app_context():
            db.create_all()
            total = len(inspect(db.engine).get_table_names())
        print(f"BASELINE_OK: {total} tablas creadas desde {COMMIT_PREVIO_A_MIGRACIONES}")
    finally:
        _borrar_arbol(directorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
