"""Administración de usuarios (C4): registro de accesos, bloqueo por cuenta, desbloqueo y visor de auditoría.

Cubre el pliego de C4 con datos sintéticos rotulados PROBE, sobre SQLite en memoria (lo mismo que
corre en CI). La carrera real sobre PostgreSQL corre solo si APP360_PRUEBAS_PG_URL apunta a una base
de prueba cuyo nombre contenga «carrera»; en CI queda omitida y se declara en el PR. La migración se
prueba con Alembic sobre SQLite con las 8 réplicas de la instancia; la prueba sobre PostgreSQL se hace
en la instancia C4 (ver el PR). La igualación de tiempos se mide en la instancia con tiempos_login.py.
"""

import hashlib
import hmac
import importlib.util
import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from werkzeug.security import generate_password_hash

import security
from config import Config
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from security import generate_access_token, huella_sesion
from services import acceso_login as al
from services import usuarios_admin as ua
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-c4-2026"
MENSAJE_LOGIN = "Usuario o contraseña incorrectos."
INSTANTE = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
RAIZ = Path(__file__).resolve().parents[1]
PG_URL_ENV = "APP360_PRUEBAS_PG_URL"
MIGRACION = RAIZ / "migrations" / "versions" / "20261120_usuarios_c4_auditoria_bloqueo.py"
PURGA = RAIZ / "scripts" / "purgar_auditoria_usuarios.py"
REPLICAS = [
    ("admin", "admin", True),
    ("gerente", "gerente", True),
    ("ventas", "sales", True),
    ("rrhh", "hr", True),
    ("tesoreria", "caja", True),
    ("direccion", "director", True),
    ("anibal.lopez", "sales", True),
    ("test_user", "sales", False),
]


# -----------------------------------------------------------------------------
# Fixtures y montaje
# -----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _limitador_reiniciado(monkeypatch):
    from extensions import limiter

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


def _crear(app, usuario, rol="sales", *, clave=CLAVE, activo=True, cambiar=False, vence=None):
    with app.app_context():
        cuenta = User(username=usuario, role=rol, active=activo)
        db.session.add(cuenta)
        cuenta.set_password(clave)
        cuenta.must_change_password = cambiar
        cuenta.temp_password_expires_at = vence
        cuenta.deactivated_at = None if activo else INSTANTE
        db.session.commit()
        return cuenta.id


def _sesion(app, usuario, rol):
    """Cliente con sesión web de un usuario recién creado (huella vigente)."""
    cliente = app.test_client()
    marcar_sesion(cliente, _crear(app, usuario, rol))
    return cliente


def _api(cliente, usuario, clave):
    return cliente.post("/api/login", json={"username": usuario, "password": clave})


def _web(cliente, usuario, clave):
    return cliente.post("/", data={"username": usuario, "password": clave})


def _aware(valor):
    return None if valor is None else (valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor)


def _estado(app, usuario):
    with app.app_context():
        cuenta = User.query.populate_existing().filter_by(username=usuario).one()
        return {
            "id": cuenta.id,
            "intentos": cuenta.failed_login_count,
            "ventana": _aware(cuenta.failed_login_window_start),
            "bloqueo": _aware(cuenta.locked_until),
            "ultimo": _aware(cuenta.last_login_at),
            "activo": cuenta.active is True,
            "tv": cuenta.token_version,
        }


def _filas(app, accion=None):
    with app.app_context():
        consulta = UserAuditLog.query
        if accion:
            consulta = consulta.filter_by(accion=accion)
        return [
            {
                "accion": fila.accion,
                "actor": fila.actor_username,
                "objetivo": fila.target_username,
                "actor_id": fila.actor_user_id,
                "objetivo_id": fila.target_user_id,
                "detalle": fila.detalle or {},
                "ip": fila.ip,
                "rep": fila.repeticiones,
                "clave": fila.clave_agrupacion,
            }
            for fila in consulta.order_by(UserAuditLog.id).all()
        ]


def _fallos(app, usuario_o_none="__todos__"):
    return [f for f in _filas(app, "login_failed") if usuario_o_none == "__todos__" or f["actor"] == usuario_o_none]


def _bloquear(app, usuario, veces=10):
    cliente = app.test_client()
    for _ in range(veces):
        _api(cliente, usuario, "PROBE-mal-intento")
    return cliente


def _token_pantalla(cliente):
    pagina = cliente.get("/admin/usuarios").get_data(as_text=True)
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', pagina).group(1)


def _texto(respuesta):
    return respuesta.get_data(as_text=True)


# -----------------------------------------------------------------------------
# Registro de accesos (A1)
# -----------------------------------------------------------------------------
def test_login_ok_web_y_api_quedan_en_auditoria_con_canal_e_ip(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.ventas")
    assert _web(app.test_client(), "probe.ventas", CLAVE).status_code == 302
    assert _api(app.test_client(), "probe.ventas", CLAVE).status_code == 200
    ok = _filas(app, "login_ok")
    assert [f["detalle"]["canal"] for f in ok] == ["web", "api"]
    assert all(f["actor"] == "probe.ventas" and f["objetivo"] == "probe.ventas" for f in ok)
    assert all(f["ip"] and f["rep"] == 1 and f["clave"] is None for f in ok)
    assert _estado(app, "probe.ventas")["ultimo"] == INSTANTE


def test_cada_motivo_de_fallo_queda_registrado_web_y_api(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.activa")
    _crear(app, "probe.inactiva", activo=False)
    _crear(app, "probe.vencida", cambiar=True, vence=INSTANTE - timedelta(hours=1))
    cliente = app.test_client()
    _api(cliente, "probe.activa", "PROBE-mal-1")
    _web(app.test_client(), "probe.activa", "PROBE-mal-2")
    _api(cliente, "probe.inexistente", CLAVE)
    _web(app.test_client(), "probe.inactiva", CLAVE)
    _api(cliente, "probe.vencida", CLAVE)
    motivos = {(f["detalle"]["motivo"], f["detalle"]["canal"]) for f in _fallos(app)}
    assert motivos == {
        ("clave_incorrecta", "api"),
        ("clave_incorrecta", "web"),
        ("usuario_inexistente", "api"),
        ("cuenta_inactiva", "web"),
        ("clave_temporal_vencida", "api"),
    }
    inexistente = [f for f in _fallos(app) if f["detalle"]["motivo"] == "usuario_inexistente"]
    assert inexistente and all(f["objetivo_id"] is None and f["actor_id"] is None for f in inexistente)
    inactiva = [f for f in _fallos(app) if f["detalle"]["motivo"] == "cuenta_inactiva"]
    assert inactiva[0]["objetivo_id"] is not None


def test_la_clave_no_aparece_en_auditoria_ni_en_logs_de_seguridad(app_seguridad, reloj, monkeypatch):
    app = app_seguridad
    _crear(app, "probe.clave")
    registros = []
    monkeypatch.setattr(security, "log_security_event", lambda *a, **k: registros.append((a, k)))
    cliente = app.test_client()
    _api(cliente, "probe.clave", "PROBE-mal-xyz")
    _web(app.test_client(), "probe.clave", CLAVE)
    _api(cliente, "probe.clave", CLAVE)
    _api(cliente, "PROBE-" + CLAVE, CLAVE)  # el nombre contiene la clave: no se guarda
    with app.app_context():
        volcado = json.dumps(
            [
                [str(f.accion), str(f.actor_username), str(f.target_username), str(f.detalle), str(f.ip)]
                for f in UserAuditLog.query.all()
            ],
            ensure_ascii=False,
        )
    assert CLAVE not in volcado and "PROBE-mal-xyz" not in volcado
    assert CLAVE not in repr(registros)
    assert any(f["actor"] == "(dato omitido)" for f in _filas(app, "login_failed"))


def test_nombre_escrito_se_trunca_a_80_y_pierde_caracteres_no_imprimibles(app_seguridad, reloj):
    app = app_seguridad
    _api(app.test_client(), "probe\x00\x07" + "n" * 120, CLAVE)
    fila = _fallos(app)[0]
    assert len(fila["actor"]) == 80
    assert all(caracter.isprintable() for caracter in fila["actor"])
    assert fila["actor"].startswith("proben")


def test_html_en_el_nombre_se_guarda_como_texto(app_seguridad, reloj):
    app = app_seguridad
    _api(app.test_client(), "<img src=x onerror=alert(1)>", CLAVE)
    assert _fallos(app)[0]["actor"] == "<img src=x onerror=alert(1)>"


def test_inundacion_de_500_nombres_deja_una_fila_y_el_login_responde(app_seguridad, reloj):
    app = app_seguridad
    cliente = app.test_client()
    estados = {_api(cliente, f"probe.nadie.{i}", "PROBE-mal").status_code for i in range(500)}
    assert estados == {401}
    filas = _fallos(app)
    assert len(filas) == 1 and filas[0]["rep"] == 500
    assert filas[0]["detalle"]["motivo"] == "usuario_inexistente"
    _crear(app, "probe.sigue")
    assert _api(cliente, "probe.sigue", CLAVE).status_code == 200


def test_la_fila_de_fallo_se_agrupa_por_cuenta_y_no_por_nombre(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.uno")
    _crear(app, "probe.dos")
    cliente = app.test_client()
    _api(cliente, "probe.uno", "PROBE-mal")
    _api(cliente, "probe.uno", "PROBE-mal")
    _api(cliente, "probe.dos", "PROBE-mal")
    reloj["ahora"] = INSTANTE + timedelta(minutes=1)
    _api(cliente, "probe.uno", "PROBE-mal")
    filas = _fallos(app)
    assert [(f["actor"], f["rep"]) for f in filas] == [("probe.uno", 2), ("probe.dos", 1), ("probe.uno", 1)]


def test_si_falla_la_auditoria_el_login_responde_igual(app_seguridad, reloj, monkeypatch):
    app = app_seguridad
    _crear(app, "probe.resiste")
    registros = []
    monkeypatch.setattr(security, "log_security_event", lambda *a, **k: registros.append(a))

    def escritura_rota(valores):
        raise RuntimeError("fallo simulado de la auditoría")

    monkeypatch.setattr(al, "_escribir_evento", escritura_rota)
    cliente = app.test_client()
    assert _api(cliente, "probe.resiste", CLAVE).status_code == 200
    rechazo = _api(cliente, "probe.resiste", "PROBE-mal")
    assert rechazo.status_code == 401 and rechazo.get_json() == {"error": "Invalid credentials"}
    assert _web(app.test_client(), "probe.resiste", CLAVE).status_code == 302
    assert any(evento[0] == "AUDITORIA_LOGIN_NO_REGISTRADA" for evento in registros)


def test_cuenta_con_clave_temporal_vigente_registra_cambio_pendiente(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.temporal", cambiar=True, vence=INSTANTE + timedelta(hours=72))
    respuesta = _api(app.test_client(), "probe.temporal", CLAVE)
    assert respuesta.status_code == 403 and respuesta.get_json()["codigo"] == "cambio_clave_obligatorio"
    ok = _filas(app, "login_ok")
    assert ok and ok[0]["detalle"] == {"canal": "api", "cambio_clave_pendiente": True}
    assert _estado(app, "probe.temporal")["ultimo"] is None


# -----------------------------------------------------------------------------
# Bloqueo por cuenta (A2)
# -----------------------------------------------------------------------------
def test_diez_fallos_bloquean_y_el_intento_11_con_clave_correcta_falla_igual(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.bloq")
    _crear(app, "probe.ref")
    cliente = app.test_client()
    referencia = _api(cliente, "probe.ref", "PROBE-mal")
    cliente_bloq = app.test_client()
    for _ in range(10):
        assert _api(cliente_bloq, "probe.bloq", "PROBE-mal").status_code == 401
    estado = _estado(app, "probe.bloq")
    assert estado["intentos"] == 10 and estado["bloqueo"] == INSTANTE + timedelta(minutes=15)
    once = _api(cliente_bloq, "probe.bloq", CLAVE)
    assert once.status_code == referencia.status_code == 401
    assert once.get_json() == referencia.get_json()
    web = _web(app.test_client(), "probe.bloq", CLAVE)
    web_ref = _web(app.test_client(), "probe.ref", "PROBE-mal")
    assert web.status_code == web_ref.status_code == 200
    assert MENSAJE_LOGIN in _texto(web) and MENSAJE_LOGIN in _texto(web_ref)
    assert _estado(app, "probe.bloq")["bloqueo"] == INSTANTE + timedelta(minutes=15)
    motivos = {f["detalle"]["motivo"] for f in _fallos(app, "probe.bloq")}
    assert {"clave_incorrecta", "cuenta_bloqueada"} <= motivos


def test_durante_el_bloqueo_no_se_extiende_el_tiempo(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.fijo")
    cliente = _bloquear(app, "probe.fijo")
    reloj["ahora"] = INSTANTE + timedelta(minutes=5)
    for _ in range(3):
        assert _api(cliente, "probe.fijo", "PROBE-mal").status_code == 401
    estado = _estado(app, "probe.fijo")
    assert estado["bloqueo"] == INSTANTE + timedelta(minutes=15) and estado["intentos"] == 10


def test_a_los_15_minutos_entra_con_la_clave_correcta_y_reinicia(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.vuelve")
    cliente = _bloquear(app, "probe.vuelve")
    reloj["ahora"] = INSTANTE + timedelta(minutes=14, seconds=59)
    assert _api(cliente, "probe.vuelve", CLAVE).status_code == 401
    reloj["ahora"] = INSTANTE + timedelta(minutes=15)
    assert _api(cliente, "probe.vuelve", CLAVE).status_code == 200
    estado = _estado(app, "probe.vuelve")
    assert estado["intentos"] == 0 and estado["bloqueo"] is None and estado["ventana"] is None


def test_acierto_fuera_del_bloqueo_reinicia_el_contador(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.reinicia")
    cliente = app.test_client()
    for _ in range(9):
        _api(cliente, "probe.reinicia", "PROBE-mal")
    assert _estado(app, "probe.reinicia")["intentos"] == 9
    assert _api(cliente, "probe.reinicia", CLAVE).status_code == 200
    assert _estado(app, "probe.reinicia")["intentos"] == 0
    for _ in range(9):
        _api(cliente, "probe.reinicia", "PROBE-mal")
    estado = _estado(app, "probe.reinicia")
    assert estado["intentos"] == 9 and estado["bloqueo"] is None


def test_la_ventana_de_15_minutos_se_reinicia_cuando_vence(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.ventana")
    cliente = app.test_client()
    for _ in range(9):
        _api(cliente, "probe.ventana", "PROBE-mal")
    reloj["ahora"] = INSTANTE + timedelta(minutes=16)
    for _ in range(9):
        _api(cliente, "probe.ventana", "PROBE-mal")
    estado = _estado(app, "probe.ventana")
    assert estado["intentos"] == 9 and estado["bloqueo"] is None
    assert estado["ventana"] == INSTANTE + timedelta(minutes=16)


def test_diez_fallos_dentro_de_la_ventana_bloquean_aunque_sean_espaciados(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.espaciado")
    cliente = app.test_client()
    for _ in range(9):
        _api(cliente, "probe.espaciado", "PROBE-mal")
    reloj["ahora"] = INSTANTE + timedelta(minutes=14)
    _api(cliente, "probe.espaciado", "PROBE-mal")
    estado = _estado(app, "probe.espaciado")
    assert estado["intentos"] == 10 and estado["bloqueo"] == INSTANTE + timedelta(minutes=29)


def test_cuenta_inexistente_responde_igual_que_clave_incorrecta(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.existe")
    cliente = app.test_client()
    inexistente = _api(cliente, "probe.noexiste", "PROBE-mal")
    incorrecta = _api(cliente, "probe.existe", "PROBE-mal")
    assert inexistente.status_code == incorrecta.status_code == 401
    assert inexistente.get_json() == incorrecta.get_json()
    web_inexistente = _web(app.test_client(), "probe.noexiste", "PROBE-mal")
    web_incorrecta = _web(app.test_client(), "probe.existe", "PROBE-mal")
    assert web_inexistente.status_code == web_incorrecta.status_code == 200
    assert MENSAJE_LOGIN in _texto(web_inexistente) and MENSAJE_LOGIN in _texto(web_incorrecta)
    assert _estado(app, "probe.existe")["intentos"] == 2


def test_cuenta_inactiva_responde_igual_y_no_suma_fallos(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.baja", activo=False)
    cliente = app.test_client()
    for _ in range(12):
        respuesta = _api(cliente, "probe.baja", CLAVE)
        assert respuesta.status_code == 401 and respuesta.get_json() == {"error": "Invalid credentials"}
    estado = _estado(app, "probe.baja")
    assert estado["intentos"] == 0 and estado["bloqueo"] is None and estado["activo"] is False
    assert {f["detalle"]["motivo"] for f in _fallos(app, "probe.baja")} == {"cuenta_inactiva"}


def test_web_y_api_comparten_el_mismo_bloqueo(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.compartida")
    cliente = app.test_client()
    for _ in range(5):
        _web(cliente, "probe.compartida", "PROBE-mal")
        _api(cliente, "probe.compartida", "PROBE-mal")
    assert _estado(app, "probe.compartida")["bloqueo"] == INSTANTE + timedelta(minutes=15)
    assert MENSAJE_LOGIN in _texto(_web(app.test_client(), "probe.compartida", CLAVE))
    assert _api(app.test_client(), "probe.compartida", CLAVE).status_code == 401


def test_el_hash_se_calcula_en_todos_los_casos_incluido_el_bloqueo(app_seguridad, reloj, monkeypatch):
    """Igualación de tiempos (M4): un intento hace exactamente una verificación de clave, con o sin cuenta."""
    app = app_seguridad
    _crear(app, "probe.tiempo")
    _crear(app, "probe.tiempo.baja", activo=False)
    _crear(app, "probe.tiempo.bloqueo")
    _bloquear(app, "probe.tiempo.bloqueo")
    cuenta = {"n": 0}
    original = security.check_password_hash

    def contando(*args, **kwargs):
        cuenta["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(security, "check_password_hash", contando)
    monkeypatch.setattr("models.core.user.check_password_hash", contando)
    cliente = app.test_client()
    for usuario, clave in [
        ("probe.inexistente", "PROBE-mal"),
        ("probe.tiempo", "PROBE-mal"),
        ("probe.tiempo.baja", CLAVE),
        ("probe.tiempo.bloqueo", CLAVE),
        ("probe.tiempo", CLAVE),
    ]:
        antes = cuenta["n"]
        _api(cliente, usuario, clave)
        assert cuenta["n"] - antes == 1, usuario


def test_bloqueo_y_fallos_de_cuentas_sin_estado_no_tocan_la_fila(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.sinestado", activo=False)
    _api(app.test_client(), "probe.sinestado", "PROBE-mal")
    estado = _estado(app, "probe.sinestado")
    assert estado["intentos"] == 0 and estado["ventana"] is None and estado["tv"] == 0


@pytest.mark.skipif(
    not os.environ.get(PG_URL_ENV) or "carrera" not in os.environ.get(PG_URL_ENV, ""),
    reason=f"Carrera real: requiere {PG_URL_ENV} con una base PostgreSQL de prueba cuyo nombre contenga «carrera»",
)
def test_carrera_en_postgresql_veinte_intentos_bloquean_una_sola_vez(monkeypatch):
    url = os.environ[PG_URL_ENV]
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "test-admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", url)
    monkeypatch.setattr(Config, "WTF_CSRF_CHECK_DEFAULT", False, raising=False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        cuenta = User(username="probe.carrera", role="sales", active=True)
        cuenta.set_password(CLAVE)
        db.session.add(cuenta)
        db.session.commit()
    barrera = threading.Barrier(20)
    resultados = []
    candado = threading.Lock()

    def intento():
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                resultado = al.autenticar("probe.carrera", "PROBE-mal", canal="api", ip="10.0.0.9")
                with candado:
                    resultados.append(resultado.ok)
            finally:
                db.session.remove()

    hilos = [threading.Thread(target=intento) for _ in range(20)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=120)
    with app.app_context():
        estado = User.query.populate_existing().filter_by(username="probe.carrera").one()
        intentos, bloqueo = estado.failed_login_count, _aware(estado.locked_until)
        suma = sum(f.repeticiones for f in UserAuditLog.query.filter_by(accion="login_failed").all())
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    assert resultados == [False] * 20
    assert intentos == 10 and bloqueo is not None
    assert suma == 20


# -----------------------------------------------------------------------------
# Desbloqueo (A3)
# -----------------------------------------------------------------------------
def test_desbloquear_permisos_y_respuestas(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.objetivo")
    _bloquear(app, "probe.objetivo")
    uid = _estado(app, "probe.objetivo")["id"]
    ventas = _sesion(app, "probe.ventas.dl", "sales")
    rrhh = _sesion(app, "probe.rrhh.dl", "hr")
    anonimo = app.test_client()
    assert anonimo.post(f"/api/admin/usuarios/{uid}/desbloquear").status_code == 401
    assert ventas.post(f"/api/admin/usuarios/{uid}/desbloquear").status_code == 403
    assert rrhh.post(f"/api/admin/usuarios/{uid}/desbloquear").status_code == 403
    assert _estado(app, "probe.objetivo")["bloqueo"] is not None
    gerente = _sesion(app, "probe.gerente.dl", "gerente")
    respuesta = gerente.post(f"/api/admin/usuarios/{uid}/desbloquear")
    assert respuesta.status_code == 200 and respuesta.get_json()["usuario"]["bloqueada"] is False


def test_desbloquear_exige_csrf_y_no_cambia_nada_sin_el(csrf_activo, reloj):
    app = csrf_activo
    _crear(app, "probe.csrf")
    _bloquear(app, "probe.csrf")
    uid = _estado(app, "probe.csrf")["id"]
    admin = _sesion(app, "probe.admin.csrf", "admin")
    assert admin.post(f"/api/admin/usuarios/{uid}/desbloquear").status_code == 400
    assert _estado(app, "probe.csrf")["bloqueo"] is not None
    token = _token_pantalla(admin)
    assert admin.post(f"/api/admin/usuarios/{uid}/desbloquear", headers={"X-CSRFToken": token}).status_code == 200
    assert _estado(app, "probe.csrf")["bloqueo"] is None


def test_desbloquear_cuenta_no_bloqueada_responde_409(app_seguridad, reloj):
    app = app_seguridad
    uid = _crear(app, "probe.libre")
    admin = _sesion(app, "probe.admin.409", "admin")
    respuesta = admin.post(f"/api/admin/usuarios/{uid}/desbloquear")
    assert respuesta.status_code == 409 and respuesta.get_json()["codigo"] == "NO_BLOQUEADA"
    assert _filas(app, "user_unlocked") == []


def test_desbloquear_limpia_contador_ventana_y_bloqueo_y_audita(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.limpia")
    _bloquear(app, "probe.limpia")
    uid = _estado(app, "probe.limpia")["id"]
    admin = _sesion(app, "probe.admin.limpia", "admin")
    assert admin.post(f"/api/admin/usuarios/{uid}/desbloquear").status_code == 200
    estado = _estado(app, "probe.limpia")
    assert estado["intentos"] == 0 and estado["ventana"] is None and estado["bloqueo"] is None
    auditoria = _filas(app, "user_unlocked")
    assert len(auditoria) == 1 and auditoria[0]["detalle"] == {"intentos": 10}
    assert auditoria[0]["actor"] == "probe.admin.limpia" and auditoria[0]["objetivo"] == "probe.limpia"
    assert _api(app.test_client(), "probe.limpia", CLAVE).status_code == 200


def test_admin_bloqueado_puede_ser_desbloqueado_por_otro_administrador(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.admin.bloqueado", rol="admin")
    _bloquear(app, "probe.admin.bloqueado")
    uid = _estado(app, "probe.admin.bloqueado")["id"]
    otro = _sesion(app, "probe.admin.otro", "admin")
    assert otro.post(f"/api/admin/usuarios/{uid}/desbloquear").status_code == 200
    assert _api(app.test_client(), "probe.admin.bloqueado", CLAVE).status_code == 200


def test_si_falla_la_auditoria_el_desbloqueo_no_se_aplica(app_seguridad, reloj, monkeypatch):
    app = app_seguridad
    _crear(app, "probe.atomico")
    _bloquear(app, "probe.atomico")
    uid = _estado(app, "probe.atomico")["id"]
    admin = _sesion(app, "probe.admin.atomico", "admin")

    def auditoria_rota(*args, **kwargs):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(ua, "registrar_auditoria", auditoria_rota)
    respuesta = admin.post(f"/api/admin/usuarios/{uid}/desbloquear")
    assert respuesta.status_code == 500 and respuesta.get_json()["codigo"] == "ERROR_INTERNO"
    assert _estado(app, "probe.atomico")["bloqueo"] == INSTANTE + timedelta(minutes=15)


def test_lista_filtra_bloqueadas_y_muestra_la_hora_argentina(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.lista.uno")
    _crear(app, "probe.lista.dos")
    _bloquear(app, "probe.lista.uno")
    admin = _sesion(app, "probe.admin.lista", "admin")
    datos = admin.get("/api/admin/usuarios?estado=bloqueada").get_json()
    assert [u["username"] for u in datos["usuarios"]] == ["probe.lista.uno"]
    fila = datos["usuarios"][0]
    assert fila["bloqueada"] is True and fila["bloqueada_hasta_texto"] == "09:15"
    assert fila["bloqueada_hasta"] == (INSTANTE + timedelta(minutes=15)).isoformat()
    # «Activo» es el estado de la columna: la cuenta bloqueada sigue activa y aparece con su marca.
    otros = admin.get("/api/admin/usuarios?estado=activo").get_json()["usuarios"]
    libre = [u for u in otros if u["username"] == "probe.lista.dos"]
    assert libre and libre[0]["bloqueada"] is False and libre[0]["bloqueada_hasta_texto"] is None
    pantalla = admin.get("/admin/usuarios").get_data(as_text=True)
    assert 'value="bloqueada"' in pantalla and 'href="/admin/usuarios/auditoria"' in pantalla
    assert "Ver auditoría completa" in pantalla


# -----------------------------------------------------------------------------
# Visor de auditoría (A4 y A5)
# -----------------------------------------------------------------------------
def _evento_admin(app, minutos, accion="user_role_changed", actor="probe.admin.v", objetivo="probe.v", detalle=None):
    with app.app_context():
        db.session.add(
            UserAuditLog(
                created_at=INSTANTE - timedelta(minutes=minutos),
                actor_username=actor,
                accion=accion,
                target_username=objetivo,
                detalle=detalle if detalle is not None else {"de": "sales", "a": "hr"},
                ip="10.0.0.1",
            )
        )
        db.session.commit()


def test_visor_pantalla_y_api_permisos_y_no_store(app_seguridad, reloj):
    app = app_seguridad
    admin = _sesion(app, "probe.admin.p", "admin")
    gerente = _sesion(app, "probe.gerente.p", "gerente")
    ventas = _sesion(app, "probe.ventas.p", "sales")
    pagina = admin.get("/admin/usuarios/auditoria")
    assert pagina.status_code == 200 and b'id="tablaAuditoriaCompleta"' in pagina.data
    assert pagina.headers["Cache-Control"] == "no-store"
    assert gerente.get("/admin/usuarios/auditoria").status_code == 200
    assert ventas.get("/admin/usuarios/auditoria").status_code == 403
    assert app.test_client().get("/admin/usuarios/auditoria").status_code == 302
    anonima = app.test_client().get("/api/admin/usuarios/auditoria")
    assert anonima.status_code == 401 and anonima.get_json() == {"error": "Sesión requerida"}
    sin_permiso = ventas.get("/api/admin/usuarios/auditoria")
    assert sin_permiso.status_code == 403 and sin_permiso.headers["Cache-Control"] == "no-store"
    assert admin.get("/api/admin/usuarios/auditoria").headers["Cache-Control"] == "no-store"


def test_visor_filtros_combinados_por_usuario_accion_y_fechas(app_seguridad, reloj):
    app = app_seguridad
    _crear(app, "probe.visor.a")
    _crear(app, "probe.visor.b")
    _bloquear(app, "probe.visor.a", veces=3)
    _api(app.test_client(), "probe.visor.b", "PROBE-mal")
    _api(app.test_client(), "probe.visor.a", CLAVE)
    admin = _sesion(app, "probe.admin.visor", "admin")
    base = "/api/admin/usuarios/auditoria?"
    por_usuario = admin.get(base + "q=visor.a").get_json()
    assert por_usuario["total"] == 2 and len(por_usuario["eventos"]) == 2
    combinado = admin.get(base + "q=visor.a&accion=login_failed").get_json()
    assert combinado["total"] == 1 and combinado["eventos"][0]["repeticiones"] == 3
    assert admin.get(base + "accion=login_ok").get_json()["total"] == 1
    assert admin.get(base + "desde=2026-11-20&hasta=2026-11-20").get_json()["total"] == 3
    assert admin.get(base + "desde=2026-11-21").get_json()["total"] == 0
    assert admin.get(base + "hasta=2026-11-19").get_json()["total"] == 0
    assert admin.get(base + "q=%25").get_json()["total"] == 0


def test_visor_rechaza_parametros_invalidos_con_400_json(app_seguridad, reloj):
    app = app_seguridad
    admin = _sesion(app, "probe.admin.invalido", "admin")
    base = "/api/admin/usuarios/auditoria?"
    casos = [
        "desde=2026-13-01",
        "desde=20/11/2026",
        "hasta=1999-01-01",
        "desde=2026-11-21&hasta=2026-11-20",
        "accion=borrar_todo",
        "pagina=0",
        "pagina=-1",
        "pagina=abc",
        "pagina=1e3",
    ]
    for query in casos:
        respuesta = admin.get(base + query)
        assert respuesta.status_code == 400, query
        assert respuesta.is_json and "error" in respuesta.get_json(), query
        assert respuesta.headers["Cache-Control"] == "no-store"
    assert admin.get(base + "desde=2026-11-20&hasta=2026-11-20").status_code == 200


def test_visor_pagina_50_orden_descendente_y_pagina_fuera_de_rango_vacia(app_seguridad, reloj):
    app = app_seguridad
    for minutos in range(120):
        _evento_admin(app, minutos)
    admin = _sesion(app, "probe.admin.pag", "admin")
    primera = admin.get("/api/admin/usuarios/auditoria").get_json()
    assert primera["total"] == 120 and primera["paginas"] == 3 and primera["por_pagina"] == 50
    assert len(primera["eventos"]) == 50 and primera["pagina"] == 1
    fechas = [evento["fecha_iso"] for evento in primera["eventos"]]
    assert fechas == sorted(fechas, reverse=True)
    tercera = admin.get("/api/admin/usuarios/auditoria?pagina=3").get_json()
    assert len(tercera["eventos"]) == 20
    fuera = admin.get("/api/admin/usuarios/auditoria?pagina=4").get_json()
    assert fuera["eventos"] == [] and fuera["total"] == 120 and fuera["paginas"] == 3
    enorme = admin.get("/api/admin/usuarios/auditoria?pagina=999999999999").get_json()
    assert enorme["eventos"] == []


def test_visor_texto_de_detalle_legible_y_sin_json(app_seguridad, reloj):
    app = app_seguridad
    _evento_admin(app, 0, detalle={"de": "sales", "a": "hr"})
    _crear(app, "probe.texto")
    _bloquear(app, "probe.texto", veces=3)
    admin = _sesion(app, "probe.admin.texto", "admin")
    eventos = admin.get("/api/admin/usuarios/auditoria?accion=user_role_changed").get_json()["eventos"]
    assert eventos[0]["detalle"] == "Rol: Ventas → RRHH"
    fallos = admin.get("/api/admin/usuarios/auditoria?accion=login_failed&q=probe.texto").get_json()["eventos"]
    assert fallos[0]["detalle"] == "Motivo: clave incorrecta, 3 intentos · Canal: API"
    assert all("{" not in evento["detalle"] for evento in fallos)


def test_visor_no_interpreta_html_del_nombre_y_el_js_no_usa_innerhtml(app_seguridad, reloj):
    app = app_seguridad
    _api(app.test_client(), "<script>alert(1)</script>", CLAVE)
    admin = _sesion(app, "probe.admin.xss", "admin")
    evento = admin.get("/api/admin/usuarios/auditoria?accion=login_failed").get_json()["eventos"][0]
    assert evento["quien"] == "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in _texto(admin.get("/admin/usuarios/auditoria"))
    for ruta in ("static/js/admin_usuarios_auditoria.js", "static/js/admin_usuarios.js"):
        codigo = (RAIZ / ruta).read_text(encoding="utf-8")
        assert "innerHTML" not in codigo and "outerHTML" not in codigo and "insertAdjacentHTML" not in codigo


def test_selector_de_acciones_tiene_las_etiquetas_en_espanol(app_seguridad):
    etiquetas = dict(ua.ACCIONES_FILTRO)
    assert etiquetas["todas"] == "Todas las acciones"
    assert [etiquetas[c] for c in ("user_created", "user_deactivated", "user_reactivated")] == [
        "Alta de usuario",
        "Desactivación",
        "Reactivación",
    ]
    assert etiquetas["user_role_changed"] == "Cambio de rol"
    assert etiquetas["user_password_reset"] == "Restablecimiento de clave"
    assert etiquetas["user_unlocked"] == "Desbloqueo"
    assert etiquetas["login_ok"] == "Login correcto" and etiquetas["login_failed"] == "Login fallido"


def test_api_c2_sigue_devolviendo_las_ultimas_50_con_sus_claves(app_seguridad, reloj):
    app = app_seguridad
    for minutos in range(60):
        _evento_admin(app, minutos)
    admin = _sesion(app, "probe.admin.c2", "admin")
    cuerpo = admin.get("/api/admin/usuarios/auditoria").get_json()
    assert len(cuerpo["eventos"]) == 50
    assert set(cuerpo["eventos"][0]) >= {"fecha", "fecha_iso", "quien", "accion", "a_quien"}


# -----------------------------------------------------------------------------
# Retención (A4): purga manual
# -----------------------------------------------------------------------------
def _cargar_purga():
    especificacion = importlib.util.spec_from_file_location("purgar_auditoria_usuarios", PURGA)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def test_purga_simula_por_defecto_y_exige_confirmacion(app_seguridad, reloj):
    app = app_seguridad
    purga = _cargar_purga()
    _evento_admin(app, 0)
    with app.app_context():
        db.session.add(
            UserAuditLog(created_at=datetime(2024, 1, 1, 12, tzinfo=timezone.utc), accion="user_created", ip=None)
        )
        db.session.commit()
    with app.app_context():
        assert purga.purgar(date(2025, 1, 1)) == (1, 0)
        assert UserAuditLog.query.count() == 2
        with pytest.raises(ValueError):
            purga.purgar(date(2025, 1, 1), ejecutar=True, confirmar="2024-01-01")
        assert UserAuditLog.query.count() == 2
        assert purga.purgar(date(2025, 1, 1), ejecutar=True, confirmar="2025-01-01") == (1, 1)
        assert UserAuditLog.query.count() == 1


def test_purga_rechaza_fechas_y_confirmaciones_mal_escritas(capsys):
    purga = _cargar_purga()
    with pytest.raises(SystemExit):
        purga.main(["--antes-de", "2025-02-30"])
    assert purga.main(["--antes-de", "2025-01-01", "--ejecutar", "--confirmar", "2024-01-01"]) == 2
    assert "No se borra nada" in capsys.readouterr().err


# -----------------------------------------------------------------------------
# Compatibilidad: sesiones, tokens, huella y ocho usuarios actuales
# -----------------------------------------------------------------------------
def test_huella_con_version_cero_es_la_de_antes_de_c4(app_seguridad, reloj):
    app = app_seguridad
    uid = _crear(app, "probe.huella")
    with app.app_context():
        cuenta = db.session.get(User, uid)
        esperada = hmac.new(
            app.secret_key.encode("utf-8"), cuenta.password_hash.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert cuenta.token_version == 0
        assert huella_sesion(cuenta) == esperada


def test_sesiones_y_tokens_previos_siguen_validos_tras_intentos_y_acierto(app_seguridad, reloj):
    app = app_seguridad
    uid = _crear(app, "probe.previo", rol="admin")
    with app.app_context():
        token = generate_access_token(uid, "probe.previo", "admin", 0)
    sesion = _sesion(app, "probe.previo.web", "admin")
    _bloquear(app, "probe.previo.otro")
    _api(app.test_client(), "probe.previo", "PROBE-mal")
    assert _api(app.test_client(), "probe.previo", CLAVE).status_code == 200
    jwt = app.test_client().get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert jwt.status_code == 200
    assert sesion.get("/api/admin/usuarios").status_code == 200


def test_los_ocho_usuarios_actuales_entran_con_su_clave(app_seguridad, reloj):
    app = app_seguridad
    claves = {}
    for nombre, rol, activo in REPLICAS:
        clave = f"c4-{nombre}-ficticia-2026"
        claves[nombre] = clave
        if nombre == "test_user":
            with app.app_context():
                cuenta = User(username=nombre, role=rol, active=False)
                db.session.add(cuenta)
                db.session.commit()
            continue
        _crear(app, nombre, rol, clave=clave, activo=activo)
    cliente = app.test_client()
    for nombre, _, activo in REPLICAS:
        esperado = 200 if activo else 401
        assert _api(cliente, nombre, claves.get(nombre, "PROBE-x")).status_code == esperado, nombre


# -----------------------------------------------------------------------------
# Migración 20261120 (upgrade, downgrade, upgrade) con las 8 réplicas
# -----------------------------------------------------------------------------
def _modulo_migracion():
    especificacion = importlib.util.spec_from_file_location("migracion_usuarios_c4", MIGRACION)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _ejecutar(motor, funcion):
    with motor.begin() as conexion:
        with Operations.context(MigrationContext.configure(conexion)):
            funcion()


def _foto(motor):
    with motor.connect() as conexion:
        filas = conexion.execute(
            sa.text("SELECT id, username, role, active, password_hash FROM users ORDER BY id")
        ).all()
    return [tuple(fila) for fila in filas]


def _columnas(motor, tabla):
    return {columna["name"] for columna in sa.inspect(motor).get_columns(tabla)}


def test_migracion_upgrade_downgrade_upgrade_con_las_8_replicas(tmp_path):
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'c4.db'}")
    with motor.begin() as conexion:
        conexion.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, "
                "password_hash VARCHAR(255), role VARCHAR(40) NOT NULL, active BOOLEAN DEFAULT 1, "
                "must_change_password BOOLEAN NOT NULL DEFAULT 0, password_changed_at DATETIME, "
                "last_login_at DATETIME, token_version INTEGER NOT NULL DEFAULT 0, "
                "temp_password_expires_at DATETIME, deactivated_at DATETIME)"
            )
        )
        conexion.execute(
            sa.text(
                "CREATE TABLE user_audit_log (id INTEGER PRIMARY KEY, created_at DATETIME NOT NULL "
                "DEFAULT CURRENT_TIMESTAMP, actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "actor_username VARCHAR(80), accion VARCHAR(40) NOT NULL, target_user_id INTEGER "
                "REFERENCES users(id) ON DELETE SET NULL, target_username VARCHAR(80), detalle JSON, "
                "ip VARCHAR(45))"
            )
        )
        for nombre, rol, activo in REPLICAS:
            hash_clave = None if nombre == "test_user" else generate_password_hash(f"PROBE-{nombre}")
            conexion.execute(
                sa.text(
                    "INSERT INTO users (username, role, active, password_hash) VALUES (:u, :r, :a, :h)"
                ),
                {"u": nombre, "r": rol, "a": activo, "h": hash_clave},
            )
    antes = _foto(motor)
    assert len(antes) == 8
    modulo = _modulo_migracion()
    nuevas_usuarios = {"failed_login_count", "failed_login_window_start", "locked_until"}
    nuevas_auditoria = {"clave_agrupacion", "repeticiones"}

    _ejecutar(motor, modulo.upgrade)
    assert nuevas_usuarios <= _columnas(motor, "users") and nuevas_auditoria <= _columnas(motor, "user_audit_log")
    with motor.connect() as conexion:
        defaults = conexion.execute(
            sa.text(
                "SELECT count(*) FROM users WHERE failed_login_count = 0 AND locked_until IS NULL "
                "AND failed_login_window_start IS NULL"
            )
        ).scalar()
    assert defaults == 8
    assert _foto(motor) == antes, "claves, roles y estado activo no cambian al migrar"

    _ejecutar(motor, modulo.downgrade)
    assert not (nuevas_usuarios & _columnas(motor, "users"))
    assert not (nuevas_auditoria & _columnas(motor, "user_audit_log"))
    assert _foto(motor) == antes

    _ejecutar(motor, modulo.upgrade)
    assert nuevas_usuarios <= _columnas(motor, "users")
    assert _foto(motor) == antes
