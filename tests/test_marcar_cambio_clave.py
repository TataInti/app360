"""Script de marcado de cambio de clave (C1 de usuarios): scripts/marcar_cambio_clave.py.

Marca y desmarca must_change_password por nombre de usuario, sin tocar la clave ni imprimirla.
Base SQLite en memoria con datos sintéticos rotulados PROBE.
"""

import importlib
import sys
from pathlib import Path

from models import db
from models.core.user import User
from sesion_de_prueba import marcar_sesion  # noqa: F401  (mantiene el mismo montaje que la suite)

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

marcar = importlib.import_module("marcar_cambio_clave")
CLAVE = "PROBE-clave-no-real-marcado"


def _crear(app, nombre):
    with app.app_context():
        usuario = User(username=nombre, role="sales", active=True)
        usuario.set_password(CLAVE)
        db.session.add(usuario)
        db.session.commit()


def _bandera(app, nombre):
    with app.app_context():
        return bool(User.query.filter_by(username=nombre).one().must_change_password)


def test_marca_y_desmarca_sin_tocar_la_clave(app_seguridad, capsys):
    app = app_seguridad
    _crear(app, "anibal.marca")
    assert _bandera(app, "anibal.marca") is False

    assert marcar.main(["--usuario", "anibal.marca"], app=app) == 0
    assert _bandera(app, "anibal.marca") is True
    salida = capsys.readouterr().out
    assert "deberá cambiar su clave" in salida and CLAVE not in salida
    with app.app_context():
        assert User.query.filter_by(username="anibal.marca").one().check_password(CLAVE)

    assert marcar.main(["--usuario", "anibal.marca", "--quitar"], app=app) == 0
    assert _bandera(app, "anibal.marca") is False


def test_usuario_inexistente_no_cambia_nada(app_seguridad, capsys):
    app = app_seguridad
    _crear(app, "otro.marca")
    assert marcar.main(["--usuario", "no.existe"], app=app) == 1
    assert "No existe" in capsys.readouterr().out
    assert _bandera(app, "otro.marca") is False
