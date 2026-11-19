"""Revocación inmediata de accesos (R-04): sesión web en cada request y tokens JWT.

Sesión web (S6): cada request con sesión revalida el usuario por clave primaria. Si está
inactivo, inexistente, sin huella o con clave cambiada, la sesión se vacía. Un cambio de rol
surte efecto en el request siguiente. Tokens JWT (S7): el usuario debe existir y estar activo.

Datos sintéticos rotulados PROBE; SQLite en memoria. Las sesiones se arman con marcar_sesion
o con el login real: el mismo helper de producción (datos_de_sesion_web).
"""

import re
from urllib.parse import urlsplit

from sqlalchemy import event

from models import db
from models.core.user import User
from security import (
    ENDPOINTS_SIN_REVALIDACION,
    SESION_HUELLA_CLAVE,
    generate_access_token,
    generate_refresh_token,
    huella_sesion,
)
from sesion_de_prueba import CLAVE_PRUEBA, marcar_sesion
from test_acceso_anonimo import EXCEPCIONES

# Pantalla de administración: el admin la ve (200). El hr no tiene administración total.
PAGINA = "/dashboard-financiero"
# Claves que identifican una sesión web. Tras revocar, ninguna debe quedar.
IDENTIDAD = {"user", "user_id", "role", SESION_HUELLA_CLAVE}


def _crear(app, username, role):
    with app.app_context():
        usuario = User(username=username, role=role, active=True)
        usuario.set_password(CLAVE_PRUEBA)
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


def _actualizar(app, usuario_id, **campos):
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        for campo, valor in campos.items():
            setattr(usuario, campo, valor)
        db.session.commit()


def _eliminar(app, usuario_id):
    with app.app_context():
        db.session.delete(db.session.get(User, usuario_id))
        db.session.commit()


def _claves_de_sesion(cliente):
    with cliente.session_transaction() as sesion:
        return set(sesion.keys())


def _sesion_incompleta(cliente, usuario_id, role="admin"):
    """Sesión de antes de la revalidación: identidad sin huella."""
    with cliente.session_transaction() as sesion:
        sesion.update({"user": "PROBE", "user_id": usuario_id, "role": role})


def _afirmar_sesion_cortada_html(cliente, respuesta):
    assert respuesta.status_code == 302
    assert urlsplit(respuesta.headers["Location"]).path == "/"
    assert not (_claves_de_sesion(cliente) & IDENTIDAD)


# -----------------------------------------------------------------------------
# (a) Usuario desactivado: HTML redirige al login, API responde 401 JSON
# -----------------------------------------------------------------------------
def test_usuario_desactivado_redirige_al_login_y_vacia_la_sesion(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    assert cliente.get(PAGINA).status_code == 200

    _actualizar(app_seguridad, uid, active=False)

    _afirmar_sesion_cortada_html(cliente, cliente.get(PAGINA))


def test_usuario_desactivado_responde_401_json_en_la_api(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    _actualizar(app_seguridad, uid, active=False)

    respuesta = cliente.get("/api/dashboard-financiero?period=30")

    assert respuesta.status_code == 401
    assert respuesta.is_json
    assert not (_claves_de_sesion(cliente) & IDENTIDAD)


# -----------------------------------------------------------------------------
# (b) Cambio de rol: el request siguiente usa el rol de la base
# -----------------------------------------------------------------------------
def test_cambio_de_rol_surte_efecto_en_el_siguiente_request(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    assert cliente.get("/admin").status_code == 200

    _actualizar(app_seguridad, uid, role="hr")

    assert cliente.get("/admin").status_code == 302
    with cliente.session_transaction() as sesion:
        assert sesion["role"] == "hr"
    assert cliente.get("/rrhh").status_code == 200


# -----------------------------------------------------------------------------
# (c) Cambio de clave: las sesiones previas quedan inválidas
# -----------------------------------------------------------------------------
def test_cambio_de_clave_invalida_la_sesion_previa(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    assert cliente.get(PAGINA).status_code == 200

    with app_seguridad.app_context():
        usuario = db.session.get(User, uid)
        usuario.set_password("PROBE-clave-nueva")
        db.session.commit()

    _afirmar_sesion_cortada_html(cliente, cliente.get(PAGINA))


# -----------------------------------------------------------------------------
# (d) Sesión sin huella (sesión de antes del cambio): inválida
# -----------------------------------------------------------------------------
def test_sesion_sin_huella_es_invalida(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    _sesion_incompleta(cliente, uid)

    _afirmar_sesion_cortada_html(cliente, cliente.get(PAGINA))


# -----------------------------------------------------------------------------
# (e) Usuario eliminado: inválida
# -----------------------------------------------------------------------------
def test_usuario_eliminado_invalida_la_sesion(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    _eliminar(app_seguridad, uid)

    _afirmar_sesion_cortada_html(cliente, cliente.get(PAGINA))


# -----------------------------------------------------------------------------
# (f) Access token de usuario desactivado o eliminado: 401 (S7)
# -----------------------------------------------------------------------------
def test_access_token_de_usuario_desactivado_responde_401(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-hr", "hr")
    with app_seguridad.app_context():
        token = generate_access_token(uid, "PROBE-hr", "hr")
    cabecera = {"Authorization": f"Bearer {token}"}
    cliente = app_seguridad.test_client()
    assert cliente.get("/api/me", headers=cabecera).status_code == 200

    _actualizar(app_seguridad, uid, active=False)

    respuesta = cliente.get("/api/me", headers=cabecera)
    assert respuesta.status_code == 401
    assert respuesta.is_json


def test_access_token_de_usuario_eliminado_responde_401(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-hr", "hr")
    with app_seguridad.app_context():
        token = generate_access_token(uid, "PROBE-hr", "hr")
    _eliminar(app_seguridad, uid)

    respuesta = app_seguridad.test_client().get(
        "/api/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert respuesta.status_code == 401


# -----------------------------------------------------------------------------
# (g) Refresh de usuario desactivado: 401
# -----------------------------------------------------------------------------
def test_refresh_de_usuario_desactivado_responde_401(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-hr", "hr")
    with app_seguridad.app_context():
        refresh = generate_refresh_token(uid, "PROBE-hr")
    cliente = app_seguridad.test_client()
    assert cliente.post("/api/refresh", json={"refresh_token": refresh}).status_code == 200

    _actualizar(app_seguridad, uid, active=False)

    assert cliente.post("/api/refresh", json={"refresh_token": refresh}).status_code == 401


# -----------------------------------------------------------------------------
# (h) Costo: una sola consulta de usuario por request con sesión
# -----------------------------------------------------------------------------
def test_una_consulta_de_usuario_por_request_con_sesion(app_seguridad):
    app_seguridad.add_url_rule("/_test/sesion", "test_sesion_probe", lambda: "ok")
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    with app_seguridad.app_context():
        motor = db.engine

    consultas = []

    def registrar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)

    event.listen(motor, "before_cursor_execute", registrar)
    try:
        # Ruta sin consultas propias: la única consulta es la revalidación por PK.
        assert cliente.get("/_test/sesion").status_code == 200
        assert len(consultas) == 1, consultas
        assert "users" in consultas[0]

        consultas.clear()
        assert cliente.get(PAGINA).status_code == 200
        consultas_de_usuario = [s for s in consultas if re.search(r"\busers\b", s)]
        assert len(consultas_de_usuario) == 1, consultas_de_usuario
    finally:
        event.remove(motor, "before_cursor_execute", registrar)


# -----------------------------------------------------------------------------
# (i) Rutas de excepción: sin sesión y sin revalidación
# -----------------------------------------------------------------------------
def test_rutas_de_excepcion_responden_aunque_la_sesion_sea_invalida(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    _sesion_incompleta(cliente, uid)

    assert cliente.get("/api/health").status_code == 200
    assert cliente.get("/static/css/comercial_paneles.css").status_code == 200
    assert cliente.post("/api/login", json={}).status_code == 400
    assert cliente.post("/api/refresh", json={}).status_code == 400


def test_lista_de_excepciones_coincide_con_la_matriz_sin_sesion():
    endpoints_de_excepcion = {endpoint for endpoint, _metodo in EXCEPCIONES}
    assert ENDPOINTS_SIN_REVALIDACION == endpoints_de_excepcion


# -----------------------------------------------------------------------------
# (j) Logout: vacía la sesión completa, en GET y en POST
# -----------------------------------------------------------------------------
def test_logout_por_post_cierra_la_sesion_y_get_no_la_toca(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)

    # GET /logout ya no cierra la sesión (D15): redirige y la sesión sigue viva.
    assert cliente.get("/logout").status_code == 302
    assert "user" in _claves_de_sesion(cliente)

    assert cliente.post("/logout").status_code == 302
    assert _claves_de_sesion(cliente) <= {"_flashes"}


# -----------------------------------------------------------------------------
# (k) Login normal: deja la huella (no el hash) y la sesión sigue vigente
# -----------------------------------------------------------------------------
def test_login_normal_guarda_la_huella_y_la_sesion_sigue_vigente(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()

    login = cliente.post("/", data={"username": "PROBE-admin", "password": CLAVE_PRUEBA})

    assert login.status_code == 302
    assert urlsplit(login.headers["Location"]).path == "/dashboard"
    with cliente.session_transaction() as sesion:
        huella = sesion[SESION_HUELLA_CLAVE]
        valores = [str(valor) for valor in sesion.values()]
        assert sesion["user"] == "PROBE-admin"
        assert sesion["user_id"] == uid
        assert sesion["role"] == "admin"
    with app_seguridad.app_context():
        usuario = db.session.get(User, uid)
        assert huella == huella_sesion(usuario)
        assert not any(usuario.password_hash in valor for valor in valores)
    assert cliente.get(PAGINA).status_code == 200


# -----------------------------------------------------------------------------
# Extras: sesión vencida y login; huella ligada a la clave del servidor
# -----------------------------------------------------------------------------
def test_sesion_vencida_no_impide_iniciar_sesion(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    _sesion_incompleta(cliente, uid)

    # La pantalla de login muestra el formulario y limpia la sesión vencida.
    assert cliente.get("/").status_code == 200
    assert not (_claves_de_sesion(cliente) & IDENTIDAD)

    _sesion_incompleta(cliente, uid)
    login = cliente.post("/", data={"username": "PROBE-admin", "password": CLAVE_PRUEBA})
    assert login.status_code == 302
    assert urlsplit(login.headers["Location"]).path == "/dashboard"
    assert cliente.get(PAGINA).status_code == 200


def test_huella_depende_de_la_clave_del_servidor(app_seguridad):
    uid = _crear(app_seguridad, "PROBE-admin", "admin")
    with app_seguridad.app_context():
        usuario = db.session.get(User, uid)
        original = huella_sesion(usuario)
        app_seguridad.secret_key = "otra-clave-de-prueba"
        try:
            cambiada = huella_sesion(usuario)
        finally:
            app_seguridad.secret_key = "test-secret"

    assert original is not None and len(original) == 64
    assert original != cambiada
    assert usuario.password_hash not in original
