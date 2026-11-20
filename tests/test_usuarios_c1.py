"""Clave temporal obligatoria, cambio de clave propia y cortes de sesión (C1 de usuarios).

Cubre del pliego: P-06 (clave temporal bloquea páginas y API), P-07 a P-10 (cambio propio:
clave actual, política, limpieza de la bandera y cierre de otras sesiones), P-09 (mínimo de
12), P-12 (JWT previos al cambio), P-19 y P-20 (mensaje genérico y hash ficticio en el login),
CSRF, anónimo → login, usuario desactivado, rutas exentas y el recorrido de todo el url_map
con clave temporal. Datos sintéticos rotulados PROBE; ninguna prueba apunta a una base real.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import RequestRedirect

import security
from models import db
from models.core.user import User
from security import (
    CODIGO_CAMBIO_CLAVE,
    ENDPOINTS_CON_CLAVE_TEMPORAL,
    ENDPOINTS_SIN_REVALIDACION,
    generate_refresh_token,
)
from services.politica_clave import CLAVES_COMUNES, errores_clave_nueva
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-actual-no-real"
NUEVA = "PROBE-clave-nueva-2026"
RUTA_CAMBIO = "/cambiar-clave"


@pytest.fixture(autouse=True)
def _limitador_reiniciado(monkeypatch):
    """Los límites de tasa guardan contadores en memoria, compartidos por toda la suite.

    Cada prueba de este archivo arranca con los contadores en cero y con el limitador apagado.
    El límite de intentos de /cambiar-clave y de /api/login se verificó con la suite completa,
    donde aparecieron respuestas 429 por esos límites.
    """
    from extensions import limiter

    # Sin app creada no hay almacenamiento del limitador que reiniciar (corre el archivo solo).
    if getattr(limiter, "_storage", None) is not None:
        limiter.reset()
    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    yield
    if getattr(limiter, "_storage", None) is not None:
        limiter.reset()


# -----------------------------------------------------------------------------
# Montaje
# -----------------------------------------------------------------------------
def _usuario(app, username, role, *, must_change=False, active=True, clave=CLAVE):
    with app.app_context():
        usuario = User.query.filter_by(username=username).one_or_none()
        if usuario is None:
            usuario = User(username=username, role=role, active=active)
            db.session.add(usuario)
        usuario.role = role
        usuario.active = active
        usuario.must_change_password = must_change
        usuario.password_changed_at = None
        usuario.set_password(clave)
        db.session.commit()
        return usuario.id


def _cliente(app, usuario_id):
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _estado(app, usuario_id):
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        return {
            "must": bool(usuario.must_change_password),
            "cambio": usuario.password_changed_at,
            "login": usuario.last_login_at,
            "activo": bool(usuario.active),
        }


def _actualizar(app, usuario_id, **campos):
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        for campo, valor in campos.items():
            setattr(usuario, campo, valor)
        db.session.commit()


def _clave_sirve(app, usuario_id, clave):
    with app.app_context():
        return db.session.get(User, usuario_id).check_password(clave)


def _login(cliente, usuario, clave):
    return cliente.post("/", data={"username": usuario, "password": clave})


def _json_codigo(respuesta):
    datos = respuesta.get_json()
    return datos is not None and datos.get("codigo") == CODIGO_CAMBIO_CLAVE


def _ruta(respuesta):
    return urlsplit(respuesta.location).path


# -----------------------------------------------------------------------------
# Política de la clave nueva (P-09, D11)
# -----------------------------------------------------------------------------
def test_politica_mensajes_por_campo():
    actual = "clave-actual-ficticia-2026"
    corta = errores_clave_nueva("corta1", "corta1", "ana", actual)
    assert "al menos 12 caracteres" in corta["clave_nueva"]
    igual = errores_clave_nueva(actual, actual, "ana", actual)
    assert "distinta de la actual" in igual["clave_nueva"]
    nombre = errores_clave_nueva("anibal.lopez", "anibal.lopez", "anibal.lopez", actual)
    assert "nombre de usuario" in nombre["clave_nueva"]
    comun = errores_clave_nueva("password1234", "password1234", "ana", actual)
    assert "muy común" in comun["clave_nueva"]
    assert errores_clave_nueva(NUEVA, NUEVA + "x", "ana", actual) == {
        "repetir_clave": "Las claves no coinciden."
    }
    assert errores_clave_nueva("", "", "ana", actual) == {
        "clave_nueva": "Ingresá la clave nueva.",
        "repetir_clave": "Repetí la clave nueva.",
    }


def test_politica_lista_de_comunes_y_sin_complejidad():
    assert len(CLAVES_COMUNES) >= 50
    assert all(clave == clave.casefold() and len(clave) >= 12 for clave in CLAVES_COMUNES)
    for clave in ("123456789012", "contraseña123", "password1234"):
        assert clave in CLAVES_COMUNES
    # Sin reglas de complejidad: doce letras minúsculas sin números ni símbolos alcanzan.
    assert errores_clave_nueva("vinoblancofrio", "vinoblancofrio", "ana", "otra-clave-larga-1") == {}


# -----------------------------------------------------------------------------
# Clave temporal: páginas, API y rutas exentas (P-06, M2)
# -----------------------------------------------------------------------------
def test_clave_temporal_bloquea_paginas_y_api(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "ventas.temporal", "sales", must_change=True)
    cliente = _cliente(app, uid)

    pagina = cliente.get("/dashboard-comercial")
    assert pagina.status_code == 302 and _ruta(pagina) == RUTA_CAMBIO

    api = cliente.get("/api/dashboard-comercial/mix")
    assert api.status_code == 403 and _json_codigo(api)
    assert api.get_json()["error"] == "Tenés que cambiar tu clave para continuar"

    como_fetch = cliente.get("/dashboard-comercial", headers={"Sec-Fetch-Dest": "empty"})
    assert como_fetch.status_code == 403 and _json_codigo(como_fetch)


def test_recorrido_de_rutas_con_clave_temporal_no_entrega_datos(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "ventas.recorrido", "sales", must_change=True)
    adaptador = app.url_map.bind("localhost")
    casos = []
    for regla in app.url_map.iter_rules():
        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            ruta = re.sub(r"<[^>]+>", "1", regla.rule)
            try:
                endpoint, _ = adaptador.match(ruta, method=metodo)
            except (NotFound, MethodNotAllowed, RequestRedirect):
                endpoint = None
            if endpoint == regla.endpoint:
                casos.append((regla.endpoint, metodo, ruta))
    assert len(casos) >= 150, "el recorrido debe cubrir el url_map completo"

    cliente = _cliente(app, uid)
    fallas = []
    for endpoint, metodo, ruta in casos:
        if endpoint in ENDPOINTS_CON_CLAVE_TEMPORAL:
            continue
        respuesta = cliente.open(ruta, method=metodo)
        if respuesta.status_code == 500:
            fallas.append((endpoint, metodo, ruta, "500"))
            continue
        if endpoint in ENDPOINTS_SIN_REVALIDACION:
            # Login, login y refresh de API, sincronización: nunca 200 con datos de sesión.
            if respuesta.status_code == 200:
                fallas.append((endpoint, metodo, ruta, "200"))
            continue
        guardia = (
            respuesta.status_code == 302 and _ruta(respuesta) == RUTA_CAMBIO
        ) or (respuesta.status_code == 403 and _json_codigo(respuesta))
        if not guardia:
            fallas.append((endpoint, metodo, ruta, respuesta.status_code))
    assert not fallas, fallas


def test_rutas_exentas_con_clave_temporal(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "ventas.exentas", "sales", must_change=True)
    cliente = _cliente(app, uid)
    assert cliente.get(RUTA_CAMBIO).status_code == 200
    salud = app.test_client().get("/api/health")
    assert salud.status_code == 200
    salida = cliente.post("/logout")
    assert salida.status_code == 302
    with cliente.session_transaction() as sesion:
        assert "user" not in sesion


# -----------------------------------------------------------------------------
# Cambio de clave propia (P-07, P-08, P-10)
# -----------------------------------------------------------------------------
def test_cambio_propio_valida_y_limpia_la_bandera(app_seguridad, caplog):
    caplog.set_level(logging.INFO)
    app = app_seguridad
    uid = _usuario(app, "ventas.cambio", "sales", must_change=True)
    cliente = _cliente(app, uid)

    def enviar(actual, nueva, repetida):
        return cliente.post(
            RUTA_CAMBIO,
            data={"clave_actual": actual, "clave_nueva": nueva, "repetir_clave": repetida},
        )

    incorrecta = enviar("ERRADA-clave-123456", NUEVA, NUEVA)
    assert incorrecta.status_code == 400
    assert "La clave actual no es correcta." in incorrecta.get_data(as_text=True)
    assert _clave_sirve(app, uid, CLAVE)

    for nueva, mensaje in (
        ("corta1", "al menos 12 caracteres"),
        (CLAVE, "distinta de la actual"),
        ("password1234", "muy común"),
    ):
        respuesta = enviar(CLAVE, nueva, nueva)
        assert respuesta.status_code == 400
        assert mensaje in respuesta.get_data(as_text=True)
    no_coinciden = enviar(CLAVE, NUEVA, NUEVA + "x")
    assert "Las claves no coinciden." in no_coinciden.get_data(as_text=True)
    assert _clave_sirve(app, uid, CLAVE), "ninguna de las respuestas fallidas cambia la clave"

    ok = enviar(CLAVE, NUEVA, NUEVA)
    assert ok.status_code == 302 and _ruta(ok) == "/leads"
    estado = _estado(app, uid)
    assert estado["must"] is False and estado["cambio"] is not None
    assert _clave_sirve(app, uid, NUEVA) and not _clave_sirve(app, uid, CLAVE)

    # La sesión que cambió la clave sigue abierta.
    assert cliente.get(RUTA_CAMBIO).status_code == 200

    # Ninguna clave aparece en los registros de seguridad ni en la aplicación.
    assert CLAVE not in caplog.text and NUEVA not in caplog.text


def test_cambio_corta_las_otras_sesiones_y_conserva_la_actual(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "rrhh.otras", "hr")
    actual = _cliente(app, uid)
    otra = _cliente(app, uid)
    assert otra.get(RUTA_CAMBIO).status_code == 200

    cambio = actual.post(
        RUTA_CAMBIO,
        data={"clave_actual": CLAVE, "clave_nueva": NUEVA, "repetir_clave": NUEVA},
    )
    assert cambio.status_code == 302

    assert actual.get(RUTA_CAMBIO).status_code == 200
    cierre = otra.get(RUTA_CAMBIO)
    assert cierre.status_code == 302 and _ruta(cierre) == "/"
    assert otra.get("/api/dashboard-comercial/mix").status_code == 401
    with otra.session_transaction() as sesion:
        assert "user" not in sesion


def test_login_tras_el_cambio_acepta_la_clave_nueva_y_no_la_vieja(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "gerente.nueva", "gerente")
    cliente = app.test_client()
    _actualizar(app, uid, password_changed_at=None)
    with app.app_context():
        usuario = db.session.get(User, uid)
        usuario.set_password(NUEVA)
        db.session.commit()
    vieja = _login(cliente, "gerente.nueva", CLAVE)
    assert vieja.status_code == 200
    assert "Usuario o contraseña incorrectos." in vieja.get_data(as_text=True)
    nueva = _login(cliente, "gerente.nueva", NUEVA)
    assert nueva.status_code == 302


def test_csrf_en_cambiar_clave(app_seguridad):
    app = app_seguridad
    app.config["WTF_CSRF_CHECK_DEFAULT"] = True
    # El cliente de prueba habla https (PREFERRED_URL_SCHEME): sin esto, Flask-WTF exige un
    # referer igual al host del cliente. Solo se apaga esa comparación; el token se valida igual.
    app.config["WTF_CSRF_SSL_STRICT"] = False
    uid = _usuario(app, "ventas.csrf", "sales", must_change=True)
    cliente = _cliente(app, uid)
    pagina = cliente.get(RUTA_CAMBIO).get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
    datos = {"clave_actual": CLAVE, "clave_nueva": NUEVA, "repetir_clave": NUEVA}

    sin_token = cliente.post(RUTA_CAMBIO, data=datos)
    assert sin_token.status_code == 400
    assert _clave_sirve(app, uid, CLAVE)

    con_token = cliente.post(RUTA_CAMBIO, data={**datos, "csrf_token": token}, headers={"Referer": "https://localhost/cambiar-clave"})
    assert con_token.status_code == 302, con_token.get_data(as_text=True)[:600]
    assert _clave_sirve(app, uid, NUEVA)


def test_anonimo_no_llega_al_cambio_de_clave(app_seguridad):
    app = app_seguridad
    anonimo = app.test_client()
    lectura = anonimo.get(RUTA_CAMBIO)
    assert lectura.status_code == 302 and _ruta(lectura) == "/"
    escritura = anonimo.post(RUTA_CAMBIO, data={"clave_actual": CLAVE, "clave_nueva": NUEVA, "repetir_clave": NUEVA})
    assert escritura.status_code == 302 and _ruta(escritura) == "/"


# -----------------------------------------------------------------------------
# Login: mensaje genérico, hash ficticio, último acceso (P-19, P-20, M4)
# -----------------------------------------------------------------------------
def test_login_mensaje_generico_y_hash_ficticio(app_seguridad, monkeypatch):
    app = app_seguridad
    _usuario(app, "ana.login", "sales")
    _usuario(app, "inactiva.login", "sales", active=False)
    llamadas = []
    verificacion_original = security.check_password_hash

    def espia(hash_guardado, clave):
        llamadas.append(hash_guardado == security.HASH_FICTICIO)
        return verificacion_original(hash_guardado, clave)

    monkeypatch.setattr(security, "check_password_hash", espia)
    cliente = app.test_client()
    intentos = [
        ("no.existe", "clave-inventada-123"),
        ("ana.login", "clave-mala-1234567"),
        ("inactiva.login", CLAVE),
    ]
    for usuario, clave in intentos:
        respuesta = _login(cliente, usuario, clave)
        assert respuesta.status_code == 200
        assert "Usuario o contraseña incorrectos." in respuesta.get_data(as_text=True)
    assert llamadas.count(True) == 2, "sin usuario o inactivo se verifica contra el hash ficticio"


def test_login_registra_ultimo_acceso_web_y_api(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "ventas.acceso", "sales")
    assert _estado(app, uid)["login"] is None
    assert _login(app.test_client(), "ventas.acceso", CLAVE).status_code == 302
    assert _estado(app, uid)["login"] is not None

    _actualizar(app, uid, last_login_at=None)
    respuesta = app.test_client().post("/api/login", json={"username": "ventas.acceso", "password": CLAVE})
    assert respuesta.status_code == 200
    assert _estado(app, uid)["login"] is not None


def test_usuario_desactivado_no_entra_ni_conserva_sesion(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "baja.prueba", "sales")
    cliente = _cliente(app, uid)
    _actualizar(app, uid, active=False)
    respuesta = cliente.get("/dashboard-comercial")
    assert respuesta.status_code == 302 and _ruta(respuesta) == "/"
    assert _login(app.test_client(), "baja.prueba", CLAVE).status_code == 200


# -----------------------------------------------------------------------------
# JWT: clave temporal y cambio de clave (P-12, M2)
# -----------------------------------------------------------------------------
def test_api_clave_temporal_no_emite_ni_renueva_tokens(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "rrhh.jwt", "hr")
    cliente = app.test_client()
    inicio = cliente.post("/api/login", json={"username": "rrhh.jwt", "password": CLAVE})
    assert inicio.status_code == 200
    acceso = inicio.get_json()["access_token"]
    refresco = inicio.get_json()["refresh_token"]

    _actualizar(app, uid, must_change_password=True)
    login = cliente.post("/api/login", json={"username": "rrhh.jwt", "password": CLAVE})
    assert login.status_code == 403 and _json_codigo(login)
    assert "access_token" not in login.get_json() and "refresh_token" not in login.get_json()

    renovacion = cliente.post("/api/refresh", json={"refresh_token": refresco})
    assert renovacion.status_code == 403 and _json_codigo(renovacion)
    assert "access_token" not in renovacion.get_json()

    con_token_previo = cliente.get("/api/me", headers={"Authorization": f"Bearer {acceso}"})
    assert con_token_previo.status_code == 403 and _json_codigo(con_token_previo)


def test_jwt_emitido_antes_del_cambio_de_clave_deja_de_valer(app_seguridad):
    app = app_seguridad
    uid = _usuario(app, "ventas.jwt", "sales")
    cliente = app.test_client()
    previo = cliente.post("/api/login", json={"username": "ventas.jwt", "password": CLAVE}).get_json()

    _actualizar(app, uid, password_changed_at=datetime.now(timezone.utc) + timedelta(seconds=60))
    acceso_previo = {"Authorization": f"Bearer {previo['access_token']}"}
    assert cliente.get("/api/me", headers=acceso_previo).status_code == 401
    assert cliente.post("/api/refresh", json={"refresh_token": previo["refresh_token"]}).status_code == 401

    _actualizar(app, uid, password_changed_at=datetime.now(timezone.utc) - timedelta(seconds=60))
    nuevo = cliente.post("/api/login", json={"username": "ventas.jwt", "password": CLAVE})
    assert nuevo.status_code == 200
    assert cliente.get("/api/me", headers={"Authorization": f"Bearer {nuevo.get_json()['access_token']}"}).status_code == 200


def test_refresh_de_usuario_inexistente_responde_401(app_seguridad):
    app = app_seguridad
    with app.app_context():
        token = generate_refresh_token(999999, "no.existe.jwt")
    respuesta = app.test_client().post("/api/refresh", json={"refresh_token": token})
    assert respuesta.status_code == 401
