"""Regresiones C3: jerarquía de administración y scripts de setup."""

import importlib
import os
import re
import sys
import threading
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

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


def test_favicon_implicito_no_responde_404(app_seguridad):
    respuesta = app_seguridad.test_client().get("/favicon.ico")
    assert respuesta.status_code == 204 and respuesta.get_data() == b""


def test_bloqueo_mutaciones_usuarios_es_noop_en_sqlite(app_seguridad):
    with app_seguridad.app_context():
        assert db.session.get_bind().dialect.name == "sqlite"
        ua.bloquear_mutaciones_usuarios()


def test_operational_error_deadlock_reintenta_la_operacion_completa(app_seguridad):
    intentos = []

    @ua.reintentar_operacion_concurrente
    def operacion():
        intentos.append(1)
        if len(intentos) == 1:
            raise OperationalError("UPDATE users", {}, SimpleNamespace(pgcode="40P01"))
        return "ok"

    with app_seguridad.app_context():
        assert operacion() == "ok"
    assert len(intentos) == 2


def test_operational_error_repetido_devuelve_409_uniforme(app_seguridad):
    intentos = []

    @ua.reintentar_operacion_concurrente
    def operacion():
        intentos.append(1)
        raise OperationalError("UPDATE users", {}, SimpleNamespace(sqlstate="40001"))

    with app_seguridad.app_context():
        with pytest.raises(ua.ErrorUsuarios) as error:
            operacion()
    assert len(intentos) == 2
    assert error.value.status == 409
    assert error.value.codigo == "OPERACION_CONCURRENTE"
    assert error.value.mensaje == (
        "Otro administrador está modificando esta cuenta; reintentá en unos segundos"
    )


PG_URL_ENV = "APP360_PRUEBAS_PG_URL"


@pytest.mark.skipif(
    not os.environ.get(PG_URL_ENV) or "carrera" not in os.environ.get(PG_URL_ENV, ""),
    reason=f"Carrera real: requiere {PG_URL_ENV} con una base propia y etiqueta carrera",
)
def test_postgres_serializa_reset_reset_y_reset_cambio_propio(monkeypatch):
    from sqlalchemy.engine import make_url

    from sesion_de_prueba import marcar_sesion

    url = os.environ[PG_URL_ENV]
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"} and parsed.port == 55432
    assert parsed.database == "app360_c3fix"

    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "test-admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", url)
    monkeypatch.setattr(Config, "WTF_CSRF_CHECK_DEFAULT", False, raising=False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    try:
        with app.app_context():
            db.drop_all()
            db.create_all()
            admin = User(username="probe-pg-admin", role="admin", active=True)
            manager = User(username="probe-pg-manager", role="manager", active=True)
            target = User(username="probe-pg-target", role="sales", active=True)
            for user in (admin, manager, target):
                user.set_password(os.urandom(24).hex())
                user.must_change_password = False
                user.temp_password_expires_at = None
            db.session.add_all((admin, manager, target))
            db.session.commit()
            admin_id, manager_id, target_id = admin.id, manager.id, target.id
            before_version = target.token_version
            before_audits = UserAuditLog.query.filter_by(
                accion="user_password_reset", target_user_id=target_id
            ).count()

        barrier = threading.Barrier(2)
        results: list[dict[str, object] | None] = [None, None]
        secret_keys: list[str | None] = [None, None]

        def reset_worker(index, actor_id):
            try:
                with app.app_context():
                    actor = db.session.get(User, actor_id)
                    barrier.wait(timeout=30)
                    _user, key, _expiry = ua.restablecer_clave(actor, target_id)
                    secret_keys[index] = key
                    results[index] = {"status": 200}
            except ua.ErrorUsuarios as error:
                db.session.rollback()
                results[index] = {"status": error.status, "code": error.codigo}
            except Exception as error:
                results[index] = {"exception": type(error).__name__}

        workers = [
            threading.Thread(target=reset_worker, args=(0, admin_id)),
            threading.Thread(target=reset_worker, args=(1, manager_id)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=90)
        assert all(not worker.is_alive() for worker in workers)
        with app.app_context():
            target = db.session.get(User, target_id, populate_existing=True)
            matching_keys = sum(bool(key and target.check_password(key)) for key in secret_keys)
            after_version = target.token_version
            after_audits = UserAuditLog.query.filter_by(
                accion="user_password_reset", target_user_id=target_id
            ).count()
        assert all(item and item.get("status") == 200 for item in results), results
        assert matching_keys == 1
        assert after_version == before_version + 2
        assert after_audits == before_audits + 2

        # Reset y cambio propio simultáneos con la clave anterior: el reset final debe
        # dejar el estado temporal coherente; luego el usuario puede cambiar esa clave.
        with app.app_context():
            target = db.session.get(User, target_id, populate_existing=True)
            target.set_password(os.urandom(24).hex())
            target.must_change_password = False
            target.temp_password_expires_at = None
            db.session.commit()
            current_password = f"PROBE-{os.urandom(24).hex()}-X9!"
            target.set_password(current_password)
            target.must_change_password = False
            target.temp_password_expires_at = None
            db.session.commit()
            before_version = target.token_version
            before_audits = UserAuditLog.query.filter_by(
                accion="user_password_reset", target_user_id=target_id
            ).count()

        reset_client = app.test_client()
        change_client = app.test_client()
        marcar_sesion(reset_client, admin_id)
        marcar_sesion(change_client, target_id)
        new_password = f"PROBE-{os.urandom(24).hex()}-X9!"
        race_barrier = threading.Barrier(2)
        race_results = {}
        race_keys = {}

        def reset_http():
            with app.app_context():
                try:
                    race_barrier.wait(timeout=30)
                    response = reset_client.post(f"/api/admin/usuarios/{target_id}/restablecer-clave")
                    body = response.get_json() or {}
                    race_results["reset"] = {
                        "status": response.status_code,
                        "code": body.get("codigo"),
                    }
                    race_keys["reset"] = body.get("clave_temporal")
                finally:
                    db.session.remove()

        def change_http():
            with app.app_context():
                try:
                    race_barrier.wait(timeout=30)
                    response = change_client.post(
                        "/cambiar-clave",
                        data={
                            "clave_actual": current_password,
                            "clave_nueva": new_password,
                            "repetir_clave": new_password,
                        },
                    )
                    race_results["change"] = {"status": response.status_code}
                finally:
                    db.session.remove()

        reset_thread = threading.Thread(target=reset_http)
        change_thread = threading.Thread(target=change_http)
        reset_thread.start()
        change_thread.start()
        reset_thread.join(timeout=90)
        change_thread.join(timeout=90)
        assert not reset_thread.is_alive() and not change_thread.is_alive()
        assert race_results["reset"]["status"] == 200
        with app.app_context():
            target = db.session.get(User, target_id, populate_existing=True)
            temp_key = race_keys["reset"]
            clave_temporal_valida = bool(temp_key) and target.check_password(temp_key)
            assert clave_temporal_valida
            assert target.must_change_password is True
            assert target.temp_password_expires_at is not None
            assert target.token_version == before_version + 1
            assert UserAuditLog.query.filter_by(
                accion="user_password_reset", target_user_id=target_id
            ).count() == before_audits + 1

        cliente = app.test_client()
        login = cliente.post(
            "/",
            data={"username": "probe-pg-target", "password": temp_key},
        )
        assert login.status_code == 302 and "/cambiar-clave" in login.headers.get("Location", "")
        cambio = cliente.post(
            "/cambiar-clave",
            data={
                "clave_actual": temp_key,
                "clave_nueva": new_password,
                "repetir_clave": new_password,
            },
        )
        assert cambio.status_code == 302
        with app.app_context():
            target = db.session.get(User, target_id, populate_existing=True)
            assert target.check_password(new_password)
            assert target.must_change_password is False
            assert target.temp_password_expires_at is None
            assert target.token_version == before_version + 1
    finally:
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
