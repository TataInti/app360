"""Claves de los scripts de alta de usuarios (hallazgo R-07).

Cubre: las cuentas existentes no se reasignan; las claves nuevas no se imprimen sin
--mostrar-claves; los --reset piden confirmación; el admin inicial usa ADMIN_PASSWORD
solo al crearse, y no quedan claves fijas en scripts/. Base SQLite en memoria con
datos sintéticos rotulados PROBE. Ninguna prueba escribe en el repositorio.
"""

import importlib
import re
import sys
from pathlib import Path

import pytest

from config import Config
from models.core.user import User

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

claves_seguras = importlib.import_module("claves_seguras")
setup_comercial = importlib.import_module("setup_comercial")
setup_database = importlib.import_module("setup_database")
setup_users = importlib.import_module("setup_users")

CLAVE_GENERADA = "PROBE-clave-generada-no-real"
# Las claves fijas anteriores tenían la forma 'Palabra123!'. El patrón evita repetirlas aquí.
PATRON_CLAVE_FIJA = re.compile(r"[A-Za-z]+\d+!")


def _usuario(username):
    return User.query.filter_by(username=username).first()


@pytest.fixture
def montaje(app_seguridad, monkeypatch, tmp_path):
    """Scripts contra la app de prueba, sin siembras de negocio y en un directorio vacío."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", None)
    for modulo in (setup_comercial, setup_users, setup_database):
        monkeypatch.setattr(modulo, "create_app", lambda: app_seguridad)
    monkeypatch.setattr(setup_comercial, "seed_business_data", lambda: ((), (), (), None))
    monkeypatch.setattr(setup_comercial, "seed_demo_lead", lambda *args: None)
    monkeypatch.setattr(setup_comercial, "seed_rrhh_data", lambda *args: None)
    monkeypatch.setattr(setup_comercial, "generar_clave", lambda: CLAVE_GENERADA)
    monkeypatch.setattr(setup_users, "generar_clave", lambda: CLAVE_GENERADA)
    return app_seguridad


def test_scripts_no_contienen_claves_fijas():
    for archivo in SCRIPTS.rglob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        assert not PATRON_CLAVE_FIJA.search(texto), (
            f"{archivo.name} contiene un literal con forma de clave fija"
        )


def test_generar_clave_es_aleatoria_y_larga():
    claves = {claves_seguras.generar_clave() for _ in range(20)}
    assert len(claves) == 20
    assert all(len(clave) >= 22 for clave in claves)  # token_urlsafe(16) da 22 caracteres


def test_confirmar_solo_acepta_si(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "SI")
    assert claves_seguras.confirmar("Prueba.") is True
    for respuesta in ("si", "", "no"):
        monkeypatch.setattr("builtins.input", lambda _, r=respuesta: r)
        assert claves_seguras.confirmar("Prueba.") is False

    def sin_entrada(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", sin_entrada)
    assert claves_seguras.confirmar("Prueba.") is False


# -----------------------------------------------------------------------------
# setup_comercial
# -----------------------------------------------------------------------------
def test_cuentas_nuevas_no_imprimen_clave_sin_flag(montaje, capsys):
    setup_comercial.main([])
    salida = capsys.readouterr().out
    assert CLAVE_GENERADA not in salida
    assert "--mostrar-claves" in salida
    assert _usuario("jefe_comercial").check_password(CLAVE_GENERADA)


def test_mostrar_claves_imprime_una_vez_y_no_escribe_archivos(montaje, capsys, tmp_path):
    setup_comercial.main(["--mostrar-claves"])
    assert capsys.readouterr().out.count(CLAVE_GENERADA) == 5  # una por cuenta nueva
    assert list(tmp_path.iterdir()) == []


def test_admin_nuevo_usa_admin_password_y_no_lo_imprime(montaje, monkeypatch, capsys):
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-entorno")
    setup_comercial.main(["--mostrar-claves"])
    salida = capsys.readouterr().out
    assert _usuario("admin").check_password("PROBE-admin-entorno")
    assert "PROBE-admin-entorno" not in salida
    assert salida.count(CLAVE_GENERADA) == 4  # las cuatro cuentas de demo


def test_cuentas_existentes_conservan_su_clave(montaje, capsys):
    setup_comercial.main([])
    hash_antes = _usuario("jefe_comercial").password_hash
    setup_comercial.main([])  # segunda corrida: no debe reasignar
    assert _usuario("jefe_comercial").password_hash == hash_antes
    assert _usuario("jefe_comercial").check_password(CLAVE_GENERADA)
    assert "existe, clave sin cambios" in capsys.readouterr().out


def test_reset_claves_requiere_confirmacion(montaje, monkeypatch, capsys):
    setup_comercial.main([])
    hash_antes = _usuario("jefe_comercial").password_hash
    monkeypatch.setattr(setup_comercial, "confirmar", lambda mensaje: False)
    monkeypatch.setattr(setup_comercial, "generar_clave", lambda: "PROBE-regenerada")
    setup_comercial.main(["--reset-claves", "--mostrar-claves"])
    assert _usuario("jefe_comercial").password_hash == hash_antes
    salida = capsys.readouterr().out
    assert "Sin confirmación: no se regeneran claves." in salida
    assert "PROBE-regenerada" not in salida

    monkeypatch.setattr(setup_comercial, "confirmar", lambda mensaje: True)
    setup_comercial.main(["--reset-claves", "--mostrar-claves"])
    assert _usuario("jefe_comercial").check_password("PROBE-regenerada")
    assert "PROBE-regenerada" in capsys.readouterr().out


def test_resumen_advierte_roles_de_demo_sin_mapeo(montaje, capsys):
    setup_comercial.main([])
    salida = capsys.readouterr().out
    advertencia = next(linea for linea in salida.splitlines() if linea.startswith("ADVERTENCIA"))
    assert "ACCESS_MAP" in advertencia
    for cuenta in ("jefe_comercial", "jefe_compras", "jefe_rrhh", "jefe_operaciones"):
        assert cuenta in advertencia
    assert "admin" not in advertencia


# -----------------------------------------------------------------------------
# setup_database: admin inicial
# -----------------------------------------------------------------------------
def test_admin_inicial_se_crea_con_admin_password(app_seguridad, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-inicial")
    assert setup_database.ensure_admin_user() == "creado"
    admin = _usuario("admin")
    assert admin.role == "admin"
    assert admin.check_password("PROBE-admin-inicial")


def test_admin_existente_conserva_su_clave(app_seguridad, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-inicial")
    setup_database.ensure_admin_user()
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-cambiada-en-entorno")
    assert setup_database.ensure_admin_user() == "existe, sin cambio de clave"
    assert _usuario("admin").check_password("PROBE-admin-inicial")
    assert setup_database.ensure_admin_user(reset_password=True) == "clave reasignada"
    assert _usuario("admin").check_password("PROBE-admin-cambiada-en-entorno")


def test_sin_admin_password_no_crea_admin(app_seguridad, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", None)
    assert setup_database.ensure_admin_user() is None
    assert _usuario("admin") is None


def test_setup_database_reset_admin_requiere_confirmacion(montaje, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://PROBE-no-se-conecta")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-inicial")
    setup_database.setup_database()
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-reset")

    monkeypatch.setattr(setup_database, "confirmar", lambda mensaje: False)
    setup_database.setup_database(reset_admin_password=True)
    assert _usuario("admin").check_password("PROBE-admin-inicial")
    assert "Sin confirmación" in capsys.readouterr().out

    monkeypatch.setattr(setup_database, "confirmar", lambda mensaje: True)
    setup_database.setup_database(reset_admin_password=True)
    assert _usuario("admin").check_password("PROBE-admin-reset")


# -----------------------------------------------------------------------------
# setup_users
# -----------------------------------------------------------------------------
def test_setup_users_no_imprime_claves_sin_flag(montaje, capsys):
    setup_users.main([])
    salida = capsys.readouterr().out
    assert CLAVE_GENERADA not in salida
    assert "--mostrar-claves" in salida
    assert _usuario("tesoreria").check_password(CLAVE_GENERADA)
    assert _usuario("tesoreria").role == "caja"
    assert _usuario("direccion").role == "director"


def test_setup_users_mostrar_claves_imprime_una_vez(montaje, capsys, tmp_path):
    setup_users.main(["--mostrar-claves"])
    assert capsys.readouterr().out.count(CLAVE_GENERADA) == 2
    assert list(tmp_path.iterdir()) == []


def test_setup_users_reset_requiere_confirmacion(montaje, monkeypatch, capsys):
    setup_users.main([])
    hash_antes = _usuario("tesoreria").password_hash
    monkeypatch.setattr(setup_users, "confirmar", lambda mensaje: False)
    monkeypatch.setattr(setup_users, "generar_clave", lambda: "PROBE-regenerada")
    setup_users.main(["--reset", "--mostrar-claves"])
    assert _usuario("tesoreria").password_hash == hash_antes
    salida = capsys.readouterr().out
    assert "Sin confirmación" in salida
    assert "PROBE-regenerada" not in salida

    monkeypatch.setattr(setup_users, "confirmar", lambda mensaje: True)
    setup_users.main(["--reset"])
    assert _usuario("tesoreria").check_password("PROBE-regenerada")
    assert "PROBE-regenerada" not in capsys.readouterr().out
