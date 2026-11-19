"""Administración de usuarios (C2): alta con clave temporal, activación, versión de token, auditoría,
salida por POST, pantalla y migración.

Cubre del pliego de DISENO-APP360 §7 lo que corresponde a C2 (P-01 a P-05, P-12, P-13, P-15 a P-17,
P-23, P-33 y P-34 en SQLite) y las pruebas propias del corte. Datos sintéticos rotulados PROBE;
ninguna prueba apunta a una base real.
"""

import importlib.util
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import jwt
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import security
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from security import SIN_ACCESO_ROUTE, generate_access_token, generate_refresh_token
from services import usuarios_admin as ua
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-actual-no-real"
NUEVA = "PROBE-clave-nueva-2026"
ALFABETO_CLAVE = re.compile(r"[abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789]{16}")
INSTANTE = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "20261119_usuarios_c2_admin.py"


@pytest.fixture(autouse=True)
def _limitador_reiniciado(monkeypatch):
    from extensions import limiter

    # Sin app creada no hay almacenamiento del limitador que reiniciar (corre el archivo solo).
    if getattr(limiter, "_storage", None) is not None:
        limiter.reset()
    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    yield
    if getattr(limiter, "_storage", None) is not None:
        limiter.reset()


@pytest.fixture
def reloj(monkeypatch):
    """Reloj controlado: security.ahora() devuelve el instante que fija la prueba."""
    instante = {"ahora": INSTANTE}
    monkeypatch.setattr(security, "ahora", lambda: instante["ahora"])
    return instante


@pytest.fixture
def csrf_activo(app_seguridad):
    app_seguridad.config["WTF_CSRF_CHECK_DEFAULT"] = True
    app_seguridad.config["WTF_CSRF_SSL_STRICT"] = False
    yield app_seguridad


# -----------------------------------------------------------------------------
# Montaje
# -----------------------------------------------------------------------------
def _crear(app, username, role, *, clave=CLAVE, must_change=False, active=True, vence=None):
    with app.app_context():
        usuario = User.query.filter_by(username=username).one_or_none()
        if usuario is None:
            usuario = User(username=username, role=role, active=active)
            db.session.add(usuario)
        usuario.role = role
        usuario.active = active
        usuario.must_change_password = must_change
        usuario.password_changed_at = None
        usuario.temp_password_expires_at = vence
        usuario.deactivated_at = None
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
            "active": usuario.active is True,
            "tv": usuario.token_version,
            "must": bool(usuario.must_change_password),
            "vence": usuario.temp_password_expires_at,
            "hash": usuario.password_hash,
            "desactivado": usuario.deactivated_at,
            "login": usuario.last_login_at,
        }


def _total(app):
    with app.app_context():
        return User.query.count()


def _ruta(respuesta):
    return urlsplit(respuesta.location).path


def _login(cliente, usuario, clave):
    return cliente.post("/", data={"username": usuario, "password": clave})


def _alta(cliente, usuario, rol, **extra):
    return cliente.post("/api/admin/usuarios", json={"username": usuario, "role": rol, **extra})


def _desactivar(cliente, usuario_id):
    return cliente.post(f"/api/admin/usuarios/{usuario_id}/desactivar")


def _reactivar(cliente, usuario_id):
    return cliente.post(f"/api/admin/usuarios/{usuario_id}/reactivar")


def _tokens(app, usuario_id):
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        version = usuario.token_version or 0
        return (
            generate_access_token(usuario.id, usuario.username, usuario.role, version),
            generate_refresh_token(usuario.id, usuario.username, version),
        )


def _jwt_sin_tv(app, usuario_id, username, role):
    """Token emitido antes de C2: sin claim tv. Se firma con la misma clave de la aplicación."""
    ahora = datetime.now(timezone.utc)
    payload = {
        "user_id": usuario_id,
        "username": username,
        "role": role,
        "type": "access",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=15),
    }
    return jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# -----------------------------------------------------------------------------
# Alta (P-01, P-04, P-05)
# -----------------------------------------------------------------------------
def test_alta_valida_genera_clave_temporal_y_guarda_solo_el_hash(app_seguridad, reloj, caplog):
    caplog.set_level(logging.DEBUG)
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))

    respuesta = _alta(admin, "Probe.Alta", "sales")

    assert respuesta.status_code == 201
    assert respuesta.headers["Cache-Control"] == "no-store"
    cuerpo = respuesta.get_json()
    clave = cuerpo["clave_temporal"]
    assert ALFABETO_CLAVE.fullmatch(clave), "16 caracteres de un alfabeto sin ambiguos"
    assert cuerpo["usuario"]["username"] == "probe.alta"
    assert cuerpo["usuario"]["estado"] == "cambiar_clave"
    assert datetime.fromisoformat(cuerpo["clave_temporal_vence"]) == INSTANTE + timedelta(hours=72)
    with app.app_context():
        usuario = User.query.filter_by(username="probe.alta").one()
        assert usuario.role == "sales" and usuario.active is True
        assert usuario.must_change_password is True
        assert usuario.password_hash != clave and usuario.check_password(clave)
        assert usuario.token_version == 0 and usuario.deactivated_at is None
        evento = UserAuditLog.query.filter_by(accion="user_created").one()
        assert evento.actor_username == "probe-admin" and evento.target_username == "probe.alta"
        assert evento.detalle == {"rol": "sales", "vence": (INSTANTE + timedelta(hours=72)).isoformat()}
    assert clave not in caplog.text


@pytest.mark.parametrize(
    "usuario, rol, campo",
    [
        ("ab", "sales", "username"),
        ("ana perez", "sales", "username"),
        ("ana@estudio", "sales", "username"),
        ("ana-ñ", "sales", "username"),
        (".ana", "sales", "username"),
        ("x" * 81, "sales", "username"),
        ("", "sales", "username"),
        ("probe.rol", "root", "role"),
        ("probe.manager", "manager", "role"),
        ("probe.sinrol", "", "role"),
    ],
)
def test_alta_invalida_responde_error_por_campo_y_no_crea_nada(app_seguridad, usuario, rol, campo):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    antes = _total(app)

    respuesta = _alta(admin, usuario, rol)

    assert respuesta.status_code == 400
    cuerpo = respuesta.get_json()
    assert campo in cuerpo["campos"]
    assert _total(app) == antes


def test_manager_no_se_ofrece_en_altas_nuevas_pero_se_muestra_si_existe(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    assert _alta(admin, "probe.gestor", "manager").get_json()["campos"]["role"].startswith("Ese rol")
    antiguo = _crear(app, "probe.antiguo", "manager")
    lista = admin.get("/api/admin/usuarios").get_json()["usuarios"]
    fila = next(u for u in lista if u["id"] == antiguo)
    assert fila["rol_nombre"] == "Administrador (manager)"


def test_usuario_repetido_sin_distinguir_mayusculas_responde_409(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    _crear(app, "probe.dup", "sales")
    _crear(app, "Probe.Viejo", "sales")  # cuenta anterior con mayúsculas guardadas (riesgo R2)

    for nombre in ("PROBE.DUP", "probe.viejo"):
        respuesta = _alta(admin, nombre, "sales")
        assert respuesta.status_code == 409, nombre
        cuerpo = respuesta.get_json()
        assert cuerpo["codigo"] == "USERNAME_TAKEN"
        assert "username" in cuerpo["campos"]


# -----------------------------------------------------------------------------
# Clave temporal: entrada única, cambio obligatorio y vencimiento (P-06, D1)
# -----------------------------------------------------------------------------
def test_clave_temporal_entra_una_vez_y_obliga_a_cambiarla(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    alta = _alta(admin, "probe.nuevo", "sales").get_json()
    clave = alta["clave_temporal"]
    uid = alta["usuario"]["id"]

    nuevo = app.test_client()
    ingreso = _login(nuevo, "probe.nuevo", clave)
    assert ingreso.status_code == 302 and _ruta(ingreso) == "/cambiar-clave"
    assert _ruta(nuevo.get("/leads")) == "/cambiar-clave"
    assert _estado(app, uid)["must"] is True

    cambio = nuevo.post("/cambiar-clave", data={"clave_actual": clave, "clave_nueva": NUEVA, "repetir_clave": NUEVA})
    assert cambio.status_code == 302
    estado = _estado(app, uid)
    assert estado["must"] is False and estado["vence"] is None

    intento = _login(app.test_client(), "probe.nuevo", clave)
    assert intento.status_code == 200
    assert "Usuario o contraseña incorrectos." in intento.get_data(as_text=True)
    ok = _login(app.test_client(), "probe.nuevo", NUEVA)
    assert ok.status_code == 302 and _ruta(ok) != "/cambiar-clave"


def test_clave_temporal_vencida_no_permite_entrar(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    alta = _alta(admin, "probe.vence", "sales").get_json()
    uid = alta["usuario"]["id"]

    reloj["ahora"] = INSTANTE + timedelta(hours=73)
    intento = _login(app.test_client(), "probe.vence", alta["clave_temporal"])
    assert intento.status_code == 200
    assert "Usuario o contraseña incorrectos." in intento.get_data(as_text=True)
    api = app.test_client().post("/api/login", json={"username": "probe.vence", "password": alta["clave_temporal"]})
    assert api.status_code == 401
    with app.app_context():
        assert security.verificar_clave_login(db.session.get(User, uid), alta["clave_temporal"]) is False


def test_sesion_con_clave_temporal_vencida_se_corta_en_la_siguiente_peticion(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    alta = _alta(admin, "probe.abierta", "sales").get_json()
    cliente = app.test_client()
    assert _login(cliente, "probe.abierta", alta["clave_temporal"]).status_code == 302

    reloj["ahora"] = INSTANTE + timedelta(hours=73)
    respuesta = cliente.get("/cambiar-clave")

    assert respuesta.status_code == 302 and _ruta(respuesta) == "/"
    with cliente.session_transaction() as sesion:
        assert "user" not in sesion


# -----------------------------------------------------------------------------
# Activar y desactivar (U4): reglas duras en el servidor (P-13, P-15, P-16)
# -----------------------------------------------------------------------------
def test_ultimo_administrador_activo_no_se_desactiva(app_seguridad):
    app = app_seguridad
    adm = _crear(app, "probe-admin", "admin")
    ger = _crear(app, "probe-gerente", "gerente")
    admin = _cliente(app, adm)

    assert _desactivar(admin, ger).status_code == 200
    respuesta = _desactivar(admin, adm)

    assert respuesta.status_code == 409
    assert respuesta.get_json()["codigo"] == "ULTIMO_ADMINISTRADOR"
    assert _estado(app, adm)["active"] is True
    assert _reactivar(admin, ger).status_code == 200


def test_servicio_rechaza_el_ultimo_administrador_aunque_el_actor_no_sea_administrador(app_seguridad):
    app = app_seguridad
    adm = _crear(app, "probe-admin", "admin")
    ven = _crear(app, "probe-ventas", "sales")
    with app.app_context():
        actor = db.session.get(User, ven)
        objetivo = db.session.get(User, adm)
        with pytest.raises(ua.ErrorUsuarios) as info:
            ua.desactivar_usuario(actor, objetivo)
        assert info.value.codigo == "ULTIMO_ADMINISTRADOR"
        db.session.rollback()
    assert _estado(app, adm)["active"] is True


def test_autodesactivacion_bloqueada_aunque_haya_otro_administrador(app_seguridad):
    app = app_seguridad
    uno = _crear(app, "probe-admin", "admin")
    _crear(app, "probe-admin-b", "gerente")
    admin = _cliente(app, uno)

    respuesta = _desactivar(admin, uno)

    assert respuesta.status_code == 403
    assert respuesta.get_json()["codigo"] == "AUTODESACTIVACION"
    estado = _estado(app, uno)
    assert estado["active"] is True and estado["tv"] == 0


def test_desactivar_corta_sesion_web_y_tokens_y_reactivar_no_los_revive(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    obj = _crear(app, "probe.objetivo", "sales")
    sesion_web = _cliente(app, obj)
    acceso, refresco = _tokens(app, obj)
    assert app.test_client().get("/api/me", headers=_bearer(acceso)).status_code == 200

    assert _desactivar(admin, obj).status_code == 200

    assert _ruta(sesion_web.get("/leads")) == "/"
    assert app.test_client().get("/api/me", headers=_bearer(acceso)).status_code == 401
    assert app.test_client().post("/api/refresh", json={"refresh_token": refresco}).status_code == 401

    assert _reactivar(admin, obj).status_code == 200
    assert app.test_client().get("/api/me", headers=_bearer(acceso)).status_code == 401
    assert app.test_client().post("/api/refresh", json={"refresh_token": refresco}).status_code == 401
    assert _ruta(sesion_web.get("/leads")) == "/"

    nuevo = app.test_client().post("/api/login", json={"username": "probe.objetivo", "password": CLAVE})
    assert nuevo.status_code == 200
    token_nuevo = nuevo.get_json()["access_token"]
    assert app.test_client().get("/api/me", headers=_bearer(token_nuevo)).status_code == 200


def test_reactivar_limpia_la_baja_y_no_restablece_la_clave(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    obj = _crear(app, "probe.reactiva", "sales", must_change=True, vence=INSTANTE + timedelta(hours=72))
    antes = _estado(app, obj)

    assert _desactivar(admin, obj).status_code == 200
    assert _estado(app, obj)["desactivado"] is not None
    assert _reactivar(admin, obj).status_code == 200

    despues = _estado(app, obj)
    assert despues["active"] is True and despues["desactivado"] is None
    assert despues["hash"] == antes["hash"]
    assert despues["vence"] == antes["vence"]
    assert despues["must"] is True


def test_desactivar_y_reactivar_responden_409_si_ya_estaban_en_ese_estado(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    obj = _crear(app, "probe.estado", "sales")
    assert _reactivar(admin, obj).get_json()["codigo"] == "YA_ACTIVO"
    assert _desactivar(admin, obj).status_code == 200
    respuesta = _desactivar(admin, obj)
    assert respuesta.status_code == 409 and respuesta.get_json()["codigo"] == "YA_DESACTIVADO"


def test_desactivar_y_reactivar_quedan_auditados_con_actor_y_destino(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    obj = _crear(app, "probe.auditado", "sales")
    _desactivar(admin, obj)
    _reactivar(admin, obj)
    with app.app_context():
        acciones = [
            (e.accion, e.actor_username, e.target_username)
            for e in UserAuditLog.query.order_by(UserAuditLog.id).all()
        ]
    assert acciones == [
        ("user_deactivated", "probe-admin", "probe.auditado"),
        ("user_reactivated", "probe-admin", "probe.auditado"),
    ]


# -----------------------------------------------------------------------------
# Versión de token (U5)
# -----------------------------------------------------------------------------
def test_token_sin_claim_tv_sirve_con_version_cero_y_cae_al_incrementarla(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.tv", "sales")
    legado = _jwt_sin_tv(app, uid, "probe.tv", "sales")
    assert app.test_client().get("/api/me", headers=_bearer(legado)).status_code == 200

    with app.app_context():
        db.session.get(User, uid).token_version = 1
        db.session.commit()

    assert app.test_client().get("/api/me", headers=_bearer(legado)).status_code == 401


def test_token_con_otra_version_se_rechaza(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.tv2", "sales")
    with app.app_context():
        db.session.get(User, uid).token_version = 2
        db.session.commit()
        viejo = generate_access_token(uid, "probe.tv2", "sales", 1)
        vigente = generate_access_token(uid, "probe.tv2", "sales", 2)
    assert app.test_client().get("/api/me", headers=_bearer(viejo)).status_code == 401
    assert app.test_client().get("/api/me", headers=_bearer(vigente)).status_code == 200


# -----------------------------------------------------------------------------
# Auditoría atómica (U6)
# -----------------------------------------------------------------------------
def test_si_falla_la_auditoria_la_desactivacion_no_se_aplica(app_seguridad, monkeypatch):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    obj = _crear(app, "probe.atomico", "sales")

    def fallo(*args, **kwargs):
        raise RuntimeError("fallo simulado de auditoría")

    monkeypatch.setattr(ua, "registrar_auditoria", fallo)
    respuesta = _desactivar(admin, obj)

    assert respuesta.status_code == 500
    cuerpo = respuesta.get_json()
    assert cuerpo["codigo"] == "ERROR_INTERNO"
    assert "fallo" not in cuerpo["error"]
    estado = _estado(app, obj)
    assert estado["active"] is True and estado["tv"] == 0 and estado["desactivado"] is None


def test_si_falla_la_auditoria_el_alta_no_crea_el_usuario(app_seguridad, monkeypatch):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))

    def fallo(*args, **kwargs):
        raise RuntimeError("fallo simulado de auditoría")

    monkeypatch.setattr(ua, "registrar_auditoria", fallo)
    respuesta = _alta(admin, "probe.sinauditoria", "sales")

    assert respuesta.status_code == 500
    assert "clave_temporal" not in respuesta.get_json()
    with app.app_context():
        assert User.query.filter_by(username="probe.sinauditoria").first() is None


# -----------------------------------------------------------------------------
# Clave mostrada una vez y secretos fuera de pantallas, API y logs (P-02, P-23)
# -----------------------------------------------------------------------------
def test_la_clave_no_aparece_en_la_lista_ni_en_la_auditoria_ni_en_los_logs(app_seguridad, caplog):
    caplog.set_level(logging.DEBUG)
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    clave = _alta(admin, "probe.secreta", "sales").get_json()["clave_temporal"]
    _desactivar(admin, _crear(app, "probe.otro", "sales"))

    pantalla = admin.get("/admin/usuarios")
    listado = admin.get("/api/admin/usuarios")
    auditoria = admin.get("/api/admin/usuarios/auditoria")

    for respuesta in (pantalla, listado, auditoria):
        assert clave not in respuesta.get_data(as_text=True)
    assert clave not in caplog.text
    with app.app_context():
        assert all(clave not in str(e.detalle) for e in UserAuditLog.query.all())


def test_la_pantalla_de_usuarios_usa_cierre_por_post_y_sin_cache(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    pagina = admin.get("/admin/usuarios")
    html = pagina.get_data(as_text=True)
    assert pagina.status_code == 200
    assert pagina.headers["Cache-Control"] == "no-store"
    assert 'action="/logout"' in html and 'method="post"' in html
    assert 'href="/logout"' not in html
    assert 'href="/admin/usuarios"' in html


# -----------------------------------------------------------------------------
# IDOR, CSRF, roles y anónimo (U8)
# -----------------------------------------------------------------------------
def test_id_inexistente_responde_404_json(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    for accion in ("desactivar", "reactivar"):
        respuesta = admin.post(f"/api/admin/usuarios/999999/{accion}")
        assert respuesta.status_code == 404
        assert respuesta.is_json and "error" in respuesta.get_json()


def test_csrf_rechaza_el_post_sin_token_y_acepta_el_de_la_pantalla(csrf_activo):
    app = csrf_activo
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    obj = _crear(app, "probe.csrf", "sales")

    assert _alta(admin, "probe.nueva", "sales").status_code == 400
    assert _desactivar(admin, obj).status_code == 400

    pagina = admin.get("/admin/usuarios").get_data(as_text=True)
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', pagina).group(1)
    con_token = admin.post(
        "/api/admin/usuarios", json={"username": "probe.nueva", "role": "sales"}, headers={"X-CSRFToken": token}
    )
    assert con_token.status_code == 201


@pytest.mark.parametrize("rol", ["sales", "hr", "caja"])
def test_rol_sin_administracion_recibe_403_en_pantalla_y_api(app_seguridad, rol):
    app = app_seguridad
    adm = _crear(app, "probe-admin", "admin")
    cliente = _cliente(app, _crear(app, f"probe.{rol}", rol))
    antes = _total(app)

    assert cliente.get("/admin/usuarios").status_code == 403
    assert cliente.get("/api/admin/usuarios").status_code == 403
    assert cliente.get("/api/admin/usuarios").get_json()["codigo"] == "SIN_PERMISO"
    assert cliente.get("/api/admin/usuarios/auditoria").status_code == 403
    assert _alta(cliente, "probe.intruso", "sales").status_code == 403
    assert _desactivar(cliente, adm).status_code == 403
    assert _reactivar(cliente, adm).status_code == 403
    assert _total(app) == antes
    assert _estado(app, adm)["active"] is True


def test_anonimo_recibe_401_en_la_api_y_login_en_la_pantalla(app_seguridad):
    app = app_seguridad
    adm = _crear(app, "probe-admin", "admin")
    anonimo = app.test_client()

    assert anonimo.get("/api/admin/usuarios").status_code == 401
    assert anonimo.get("/api/admin/usuarios").is_json
    assert _alta(anonimo, "probe.anonimo", "sales").status_code == 401
    assert anonimo.get("/api/admin/usuarios/auditoria").status_code == 401
    assert _desactivar(anonimo, adm).status_code == 401
    pantalla = anonimo.get("/admin/usuarios")
    assert pantalla.status_code == 302 and _ruta(pantalla) == "/"


# -----------------------------------------------------------------------------
# Lista, visor y menú (U2, U6)
# -----------------------------------------------------------------------------
def test_lista_filtra_por_estado_y_busqueda_y_usa_etiquetas_en_espanol(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    _crear(app, "probe.lista.activo", "sales")
    _crear(app, "probe.lista.baja", "sales", active=False)
    _crear(app, "probe.lista.clave", "purchases", must_change=True)

    baja = admin.get("/api/admin/usuarios?estado=desactivado").get_json()["usuarios"]
    assert [u["username"] for u in baja] == ["probe.lista.baja"]
    assert baja[0]["estado_nombre"] == "Desactivado" and baja[0]["ultimo_acceso_texto"] == "Nunca"

    clave = admin.get("/api/admin/usuarios?estado=cambiar_clave").get_json()["usuarios"]
    assert [u["username"] for u in clave] == ["probe.lista.clave"]
    assert clave[0]["estado_nombre"] == "Debe cambiar la clave"

    assert admin.get("/api/admin/usuarios?q=LISTA").get_json()["total"] == 3
    assert admin.get("/api/admin/usuarios?q=%25").get_json()["total"] == 0
    todos = admin.get("/api/admin/usuarios?estado=inventado").get_json()["total"]
    assert todos == admin.get("/api/admin/usuarios").get_json()["total"]


def test_pantalla_ofrece_roles_en_espanol_sin_manager(app_seguridad):
    app = app_seguridad
    html = _cliente(app, _crear(app, "probe-admin", "admin")).get("/admin/usuarios").get_data(as_text=True)
    for codigo, nombre in ua.ROLES_ASIGNABLES:
        assert f'value="{codigo}">{nombre}</option>' in html
    assert 'value="manager"' not in html
    assert ua.ETIQUETAS_ROL["manager"] == "Administrador (manager)"


def test_menu_muestra_usuarios_solo_a_administradores(app_seguridad):
    app = app_seguridad
    admin_html = _cliente(app, _crear(app, "probe-admin", "admin")).get("/admin/usuarios").get_data(as_text=True)
    assert 'href="/admin/usuarios"' in admin_html
    ventas = _cliente(app, _crear(app, "probe.menu", "sales"))
    pagina = ventas.get(SIN_ACCESO_ROUTE)
    assert pagina.status_code == 200
    assert 'href="/admin/usuarios"' not in pagina.get_data(as_text=True)


def test_visor_muestra_las_ultimas_50_acciones_en_espanol(app_seguridad):
    app = app_seguridad
    adm = _crear(app, "probe-admin", "admin")
    with app.app_context():
        actor = db.session.get(User, adm)
        objetivo = User(username="probe.visor", role="sales", active=True)
        db.session.add(objetivo)
        db.session.flush()
        for _ in range(55):
            ua.registrar_auditoria(actor, "user_deactivated", objetivo, {"rol": "sales"})
        db.session.commit()

    eventos = _cliente(app, adm).get("/api/admin/usuarios/auditoria").get_json()["eventos"]

    assert len(eventos) == 50
    assert eventos[0]["accion"] == "Desactivación"
    assert eventos[0]["quien"] == "probe-admin" and eventos[0]["a_quien"] == "probe.visor"


# -----------------------------------------------------------------------------
# Salida por POST (U7, D15)
# -----------------------------------------------------------------------------
def test_logout_por_get_no_cierra_y_por_post_si(app_seguridad):
    app = app_seguridad
    cliente = _cliente(app, _crear(app, "probe.salida", "sales"))
    assert cliente.get("/logout").status_code == 302
    assert cliente.get("/leads").status_code == 200
    assert cliente.post("/logout").status_code == 302
    assert _ruta(cliente.get("/leads")) == "/"


# -----------------------------------------------------------------------------
# Migración 20261119_usuarios_c2_admin (P-34, en SQLite): upgrade, downgrade y upgrade
# -----------------------------------------------------------------------------
USUARIOS_PREVIOS = [
    ("admin", "admin", True, "hash-sintetico-admin"),
    ("gerente", "gerente", True, "hash-sintetico-gerente"),
    ("ventas", "sales", True, "hash-sintetico-ventas"),
    ("rrhh", "hr", True, "hash-sintetico-rrhh"),
    ("tesoreria", "caja", True, "hash-sintetico-tesoreria"),
    ("direccion", "director", True, "hash-sintetico-direccion"),
    ("anibal.lopez", "sales", True, "hash-sintetico-anibal"),
    ("test_user", "sales", False, "hash-sintetico-test"),
]
NUEVAS_COLUMNAS = {"token_version", "temp_password_expires_at", "deactivated_at"}


def _modulo_migracion():
    especificacion = importlib.util.spec_from_file_location("migracion_usuarios_c2", MIGRACION)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _ejecutar(motor, funcion):
    with motor.begin() as conexion:
        with Operations.context(MigrationContext.configure(conexion)):
            funcion()


def _columnas(motor):
    return {columna["name"] for columna in sa.inspect(motor).get_columns("users")}


def _fotografia(motor):
    with motor.connect() as conexion:
        filas = conexion.execute(sa.text("SELECT username, role, active, password_hash FROM users ORDER BY id")).all()
    return [tuple(fila) for fila in filas]


def test_migracion_c2_upgrade_downgrade_upgrade_con_usuarios_existentes(tmp_path):
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'usuarios_c2.db'}")
    with motor.begin() as conexion:
        conexion.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, "
                "password_hash VARCHAR(255), role VARCHAR(40) NOT NULL, active BOOLEAN DEFAULT 1, "
                "must_change_password BOOLEAN NOT NULL DEFAULT 0, password_changed_at DATETIME, "
                "last_login_at DATETIME)"
            )
        )
        conexion.execute(
            sa.text("INSERT INTO users (username, role, active, password_hash) VALUES (:u, :r, :a, :h)"),
            [{"u": u, "r": r, "a": a, "h": h} for u, r, a, h in USUARIOS_PREVIOS],
        )
    antes = _fotografia(motor)
    assert len(antes) == 8
    modulo = _modulo_migracion()

    _ejecutar(motor, modulo.upgrade)
    assert NUEVAS_COLUMNAS <= _columnas(motor)
    assert "user_audit_log" in sa.inspect(motor).get_table_names()
    indices = {i["name"] for i in sa.inspect(motor).get_indexes("user_audit_log")}
    assert {"ix_user_audit_log_created_at", "ix_user_audit_log_target"} <= indices
    with motor.connect() as conexion:
        valores = conexion.execute(
            sa.text("SELECT token_version, temp_password_expires_at, deactivated_at FROM users")
        ).all()
    assert len(valores) == 8 and all(fila[0] == 0 and fila[1] is None and fila[2] is None for fila in valores)
    assert _fotografia(motor) == antes, "claves, roles y estado activo no cambian al migrar"

    _ejecutar(motor, modulo.downgrade)
    assert not (NUEVAS_COLUMNAS & _columnas(motor))
    assert "user_audit_log" not in sa.inspect(motor).get_table_names()
    assert _fotografia(motor) == antes

    _ejecutar(motor, modulo.upgrade)
    assert NUEVAS_COLUMNAS <= _columnas(motor)
    assert _fotografia(motor) == antes
