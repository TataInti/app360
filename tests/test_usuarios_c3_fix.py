"""Regresiones C3: jerarquía de administración y scripts de setup."""

import importlib
import re
import sys
from types import SimpleNamespace

import pytest

from config import Config
from models import db
from models.core.user import User
from services import usuarios_admin as ua
from sesion_de_prueba import marcar_sesion

SCRIPTS = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts")
ACCIONES = ("rol", "reset", "desactivar", "reactivar")
OBJETIVOS = (
    ("admin", "admin", True),
    ("manager", "manager", True),
    ("gerente", "gerente", True),
    ("ventas", "sales", True),
    ("inactivo", "sales", False),
)
MENSAJE_JERARQUIA = "Esta cuenta la administra un administrador. Pedile a un administrador que haga este cambio."


def _crear(app, username, role, *, active=True, clave="PROBE-credencial-no-real"):
    with app.app_context():
        user = User(username=username, role=role, active=active)
        user.set_password(clave)
        user.must_change_password = False
        user.temp_password_expires_at = None
        db.session.add(user)
        db.session.commit()
        return user.id


def _cliente(app, user_id):
    client = app.test_client()
    marcar_sesion(client, user_id)
    return client


def _hash(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id, populate_existing=True).password_hash


@pytest.mark.parametrize("actor_role", ["admin", "manager", "gerente"])
@pytest.mark.parametrize("objetivo", OBJETIVOS, ids=[item[0] for item in OBJETIVOS])
@pytest.mark.parametrize("accion", ACCIONES)
def test_matriz_jerarquia_acciones(actor_role, objetivo, accion, app_seguridad):
    app = app_seguridad
    actor_id = _crear(app, f"probe-actor-{actor_role}", actor_role)
    _crear(app, "probe-admin-reserva", "admin")
    target_name, target_role, active = objetivo
    target_id = _crear(app, f"probe-target-{target_name}", target_role, active=active)
    client = _cliente(app, actor_id)

    if accion == "rol":
        respuesta = client.post(f"/api/admin/usuarios/{target_id}/rol", json={"role": "hr"})
    else:
        respuesta = client.post(f"/api/admin/usuarios/{target_id}/{ {'reset': 'restablecer-clave', 'desactivar': 'desactivar', 'reactivar': 'reactivar'}[accion] }")

    protegida = actor_role == "gerente" and target_role in {"admin", "manager"}
    if protegida:
        assert respuesta.status_code == 403
        assert respuesta.get_json() == {"codigo": "JERARQUIA_INSUFICIENTE", "error": MENSAJE_JERARQUIA}
        return

    esperado = {
        "rol": 200,
        "reset": 200 if active else 409,
        "desactivar": 200 if active else 409,
        "reactivar": 409 if active else 200,
    }[accion]
    assert respuesta.status_code == esperado, (actor_role, objetivo, accion, respuesta.get_json())


def test_puede_administrar_es_la_regla_unitaria_reutilizable():
    admin = SimpleNamespace(role="admin")
    legacy = SimpleNamespace(role="manager")
    gerente = SimpleNamespace(role="gerente")
    roles_protegidos = [SimpleNamespace(role=role) for role in ("admin", "manager")]
    roles_comunes = [SimpleNamespace(role=role) for role in ("gerente", "sales")]

    for actor in (admin, legacy):
        for objetivo in [*roles_protegidos, *roles_comunes]:
            assert ua.puede_administrar(actor, objetivo) == (True, None, None)
    for objetivo in roles_protegidos:
        assert ua.puede_administrar(gerente, objetivo) == (
            False,
            "JERARQUIA_INSUFICIENTE",
            MENSAJE_JERARQUIA,
        )
    for objetivo in roles_comunes:
        assert ua.puede_administrar(gerente, objetivo) == (True, None, None)
    for rol in ("admin", "manager"):
        assert ua.puede_administrar(gerente, None, rol) == (
            False,
            "JERARQUIA_INSUFICIENTE",
            MENSAJE_JERARQUIA,
        )
    assert ua.puede_administrar(gerente, None, "gerente") == (True, None, None)


@pytest.mark.parametrize("actor_role", ["admin", "manager", "gerente"])
def test_roles_asignables_coinciden_en_api_y_pantalla(actor_role, app_seguridad):
    app = app_seguridad
    actor_id = _crear(app, f"probe-roles-{actor_role}", actor_role)
    client = _cliente(app, actor_id)
    respuesta_api = client.get("/api/admin/usuarios")
    assert respuesta_api.status_code == 200
    codigos_api = [fila["codigo"] for fila in respuesta_api.get_json()["roles_asignables"]]
    pagina = client.get("/admin/usuarios")
    assert pagina.status_code == 200
    html = pagina.get_data(as_text=True)
    bloque = re.search(r'<select id="altaRol"[^>]*>(.*?)</select>', html, flags=re.S)
    assert bloque is not None
    codigos_pantalla = re.findall(r'<option value="([^"]*)"', bloque.group(1))
    codigos_pantalla = [codigo for codigo in codigos_pantalla if codigo]
    esperado = [codigo for codigo, _ in ua.ROLES_ASIGNABLES]
    if actor_role == "gerente":
        esperado = [codigo for codigo in esperado if codigo not in {"admin", "manager"}]
    assert codigos_api == esperado
    assert codigos_pantalla == esperado
    if actor_role == "gerente":
        assert "admin" not in codigos_api and "manager" not in codigos_api


def test_gerente_no_puede_crear_ni_promover_a_roles_superiores(app_seguridad):
    app = app_seguridad
    gerente_id = _crear(app, "probe-gerente-crea", "gerente")
    target_id = _crear(app, "probe-ventas-promocion", "sales")
    client = _cliente(app, gerente_id)

    for role in ("admin", "manager"):
        alta = client.post("/api/admin/usuarios", json={"username": f"probe-alta-{role}", "role": role})
        cambio = client.post(f"/api/admin/usuarios/{target_id}/rol", json={"role": role})
        for respuesta in (alta, cambio):
            assert respuesta.status_code == 403
            assert respuesta.get_json() == {"codigo": "JERARQUIA_INSUFICIENTE", "error": MENSAJE_JERARQUIA}


def _modulo_setup(monkeypatch, nombre, app):
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    modulo = importlib.import_module(nombre)
    monkeypatch.setattr(modulo, "create_app", lambda: app, raising=False)
    return modulo


def test_setup_users_conserva_rol_distinto_y_avisa(app_seguridad, monkeypatch, capsys):
    setup_users = _modulo_setup(monkeypatch, "setup_users", app_seguridad)
    monkeypatch.setattr(setup_users, "generar_clave", lambda: "PROBE-clave-generada-no-real")
    user_id = _crear(app_seguridad, "tesoreria", "sales", clave="PROBE-hash-original-no-real")
    antes_hash = _hash(app_seguridad, user_id)

    setup_users.setup_users(reset_passwords=False, mostrar_claves=False)

    salida = capsys.readouterr().out
    with app_seguridad.app_context():
        user = db.session.get(User, user_id, populate_existing=True)
        assert user.role == "sales" and user.active is True
        assert user.password_hash == antes_hash
    assert "rol conservado" in salida


def test_setup_database_conserva_rol_y_clave_existentes_por_defecto(app_seguridad, monkeypatch):
    setup_database = _modulo_setup(monkeypatch, "setup_database", app_seguridad)
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "probe-admin-setup-db")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-setup-db-no-real")
    user_id = _crear(app_seguridad, "probe-admin-setup-db", "sales", clave="PROBE-clave-admin-db-no-real")
    antes_hash = _hash(app_seguridad, user_id)

    resultado = setup_database.ensure_admin_user()

    with app_seguridad.app_context():
        user = db.session.get(User, user_id, populate_existing=True)
        assert resultado == "existe, sin cambio de clave"
        assert user.role == "sales" and user.password_hash == antes_hash


def test_setup_comercial_conserva_rol_y_clave_de_cuenta_existente(app_seguridad, monkeypatch):
    setup_comercial = _modulo_setup(monkeypatch, "setup_comercial", app_seguridad)
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "probe-admin-comercial")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-comercial-no-real")
    monkeypatch.setattr(setup_comercial, "generar_clave", lambda: "PROBE-clave-demo-nueva-no-real")
    sales_id = _crear(app_seguridad, "jefe_comercial", "sales", clave="PROBE-clave-comercial-no-real")
    admin_id = _crear(app_seguridad, "probe-admin-comercial", "admin", clave="PROBE-clave-admin-comercial-no-real")
    sales_hash = _hash(app_seguridad, sales_id)
    admin_hash = _hash(app_seguridad, admin_id)

    resumen = setup_comercial.seed_users()

    with app_seguridad.app_context():
        sales = db.session.get(User, sales_id, populate_existing=True)
        admin = db.session.get(User, admin_id, populate_existing=True)
        assert sales.role == "sales" and sales.password_hash == sales_hash
        assert admin.role == "admin" and admin.password_hash == admin_hash
    assert next(item for item in resumen if item["usuario"] == "jefe_comercial")["rol"] == "sales"
