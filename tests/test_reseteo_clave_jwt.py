"""Reseteo de clave y JWT previos (C1, hallazgo medio 1 de la verificación del PR #19).

Cualquier cambio de clave hecho con User.set_password (scripts de setup, consola o el cambio
propio) registra password_changed_at. Así, los access y refresh emitidos antes dejan de valer,
los emitidos después valen aunque sean del mismo segundo, y las cuentas sin fecha de cambio
siguen sirviendo. Datos sintéticos rotulados PROBE; base SQLite en memoria.
"""

from urllib.parse import urlsplit

import pytest

from models import db
from models.core.user import User
from security import decode_token, generate_access_token, token_anterior_al_cambio_de_clave
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-inicial-2026"
NUEVA = "PROBE-clave-reseteada-2026"


@pytest.fixture(autouse=True)
def _limitador_apagado(monkeypatch):
    """Con el limitador apagado, los logins y refresh de estas pruebas no reciben 429."""
    from extensions import limiter

    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    yield


def _crear(app, usuario, rol="sales"):
    """Alta sintética con set_password, como en los scripts de setup. Devuelve el id."""
    with app.app_context():
        cuenta = User(username=usuario, role=rol, active=True)
        db.session.add(cuenta)
        cuenta.set_password(CLAVE)
        db.session.commit()
        return cuenta.id


def _resetear(app, uid, clave):
    """Reseteo como lo hacen los scripts y la consola: set_password y commit."""
    with app.app_context():
        cuenta = db.session.get(User, uid)
        cuenta.set_password(clave)
        db.session.commit()


def _entrar_api(cliente, usuario, clave=CLAVE):
    return cliente.post("/api/login", json={"username": usuario, "password": clave})


def _cabecera(token):
    return {"Authorization": f"Bearer {token}"}


def test_reseteo_invalida_access_y_refresh_previos_y_uno_nuevo_vale(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "PROBE-reset-api")
    cliente = app.test_client()
    previo = _entrar_api(cliente, "PROBE-reset-api").get_json()
    assert cliente.get("/api/me", headers=_cabecera(previo["access_token"])).status_code == 200

    _resetear(app, uid, NUEVA)

    assert cliente.get("/api/me", headers=_cabecera(previo["access_token"])).status_code == 401
    previo_renovado = cliente.post("/api/refresh", json={"refresh_token": previo["refresh_token"]})
    assert previo_renovado.status_code == 401

    nuevo = _entrar_api(cliente, "PROBE-reset-api", NUEVA)
    assert nuevo.status_code == 200
    datos = nuevo.get_json()
    assert cliente.get("/api/me", headers=_cabecera(datos["access_token"])).status_code == 200
    renovado = cliente.post("/api/refresh", json={"refresh_token": datos["refresh_token"]})
    assert renovado.status_code == 200


def test_reseteo_cierra_la_sesion_web_previa(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "PROBE-reset-web")
    web = app.test_client()
    marcar_sesion(web, uid)
    assert web.get("/cambiar-clave").status_code == 200

    _resetear(app, uid, NUEVA)

    cierre = web.get("/cambiar-clave")
    assert cierre.status_code == 302
    assert urlsplit(cierre.location).path == "/"


def test_cuenta_sin_fecha_de_cambio_sigue_sirviendo(app_seguridad):
    """Cuentas previas al C1: password_changed_at NULL no invalida ningún token."""
    app = app_seguridad
    uid = _crear(app, "PROBE-legado-api")
    with app.app_context():
        cuenta = db.session.get(User, uid)
        cuenta.password_changed_at = None
        db.session.commit()

    cliente = app.test_client()
    datos = _entrar_api(cliente, "PROBE-legado-api").get_json()
    assert cliente.get("/api/me", headers=_cabecera(datos["access_token"])).status_code == 200
    renovado = cliente.post("/api/refresh", json={"refresh_token": datos["refresh_token"]})
    assert renovado.status_code == 200


def test_token_emitido_justo_despues_del_alta_no_es_anterior(app_seguridad):
    """El alta fija password_changed_at; un token emitido después, aun en el mismo segundo, vale."""
    app = app_seguridad
    uid = _crear(app, "PROBE-alta-token")
    with app.app_context():
        cuenta = db.session.get(User, uid)
        token = generate_access_token(uid, "PROBE-alta-token", "sales")
        payload = decode_token(token)
        assert payload is not None
        assert token_anterior_al_cambio_de_clave(cuenta, payload) is False


def test_alta_nueva_entra_y_obtiene_token(app_seguridad):
    app = app_seguridad
    _crear(app, "PROBE-alta-nueva")
    cliente = app.test_client()
    datos = _entrar_api(cliente, "PROBE-alta-nueva").get_json()
    assert cliente.get("/api/me", headers=_cabecera(datos["access_token"])).status_code == 200
    renovado = cliente.post("/api/refresh", json={"refresh_token": datos["refresh_token"]})
    assert renovado.status_code == 200

    web = app.test_client()
    entrada = web.post("/", data={"username": "PROBE-alta-nueva", "password": CLAVE})
    assert entrada.status_code == 302


def test_cambio_propio_invalida_jwt_previos_y_registra_la_fecha(app_seguridad):
    """/cambiar-clave sigue fijando password_changed_at (una sola vez) y corta los JWT previos."""
    app = app_seguridad
    uid = _crear(app, "PROBE-propio-jwt")
    cliente = app.test_client()
    marcar_sesion(cliente, uid)
    previo = _entrar_api(cliente, "PROBE-propio-jwt").get_json()
    assert cliente.get("/api/me", headers=_cabecera(previo["access_token"])).status_code == 200

    cambio = cliente.post(
        "/cambiar-clave",
        data={"clave_actual": CLAVE, "clave_nueva": NUEVA, "repetir_clave": NUEVA},
    )
    assert cambio.status_code == 302
    with app.app_context():
        cuenta = db.session.get(User, uid)
        assert cuenta.password_changed_at is not None
        assert cuenta.check_password(NUEVA)

    assert cliente.get("/api/me", headers=_cabecera(previo["access_token"])).status_code == 401
    nuevo = _entrar_api(cliente, "PROBE-propio-jwt", NUEVA).get_json()
    assert cliente.get("/api/me", headers=_cabecera(nuevo["access_token"])).status_code == 200
