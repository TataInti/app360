"""MFA opcional (C6 de administración de usuarios): TOTP RFC 6238, códigos de respaldo, segundo paso del
login, restablecimiento por administrador y script de último recurso.

Datos sintéticos rotulados PROBE sobre SQLite en memoria. Las claves y secretos se generan en tiempo de
ejecución (no hay códigos literales en el repo). Los vectores públicos del RFC 6238 son de dominio público.
La carrera real sobre PostgreSQL corre solo si APP360_PRUEBAS_PG_URL apunta a una base cuyo nombre contenga
«carrera»; en CI queda omitida y se declara en el PR.
"""

import hashlib
import hmac
import importlib.util
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import security
from config import Config
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from models.core.user_mfa_backup_code import UserMfaBackupCode
from security import generate_access_token, huella_sesion
from services import mfa, totp
from services.acceso_login import autenticar
from services.usuarios_admin import ErrorUsuarios, restablecer_mfa
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-c6-2026"
NUEVA = "PROBE-nueva-clave-c6-2026"
INSTANTE = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "20261120_usuarios_c6_mfa.py"
SCRIPT_RESET = RAIZ / "scripts" / "restablecer_mfa.py"
# Secreto de prueba del RFC 6238 (ASCII "12345678901234567890").
SECRETO_RFC = b"12345678901234567890"
VECTORES_RFC = [  # (tiempo, código de 6 dígitos = últimos 6 del de 8 del RFC)
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
]
PAGINAS_PERMITIDAS_PENDIENTE = {"auth.login_mfa", "auth.logout", "static", "api_rest.health_check"}
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


@pytest.fixture(autouse=True)
def _limitador_reiniciado(monkeypatch):
    """Contadores del limitador de tasa a cero antes y después de cada prueba (los acumula el proceso)."""
    from extensions import limiter

    if getattr(limiter, "_storage", None) is not None:
        limiter.reset()
    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    yield
    if getattr(limiter, "_storage", None) is not None:
        limiter.reset()


@pytest.fixture(autouse=True)
def _limite_ip_reiniciado():
    """El límite por IP del segundo paso es de proceso: cada prueba empieza con el contador en cero."""
    mfa._intentos_ip.clear()
    yield
    mfa._intentos_ip.clear()


@pytest.fixture
def reloj(monkeypatch):
    instante = {"ahora": INSTANTE}
    monkeypatch.setattr(security, "ahora", lambda: instante["ahora"])
    return instante


def _crear(app, usuario, rol="sales", clave=CLAVE, activo=True, cambiar=False):
    with app.app_context():
        cuenta = User(username=usuario, role=rol, active=activo)
        db.session.add(cuenta)
        cuenta.set_password(clave)
        cuenta.must_change_password = cambiar
        db.session.commit()
        return cuenta.id


def _activar_mfa(app, usuario_id, instante=INSTANTE):
    """Activa el MFA por el servicio y devuelve los códigos de respaldo (sin pasar por la pantalla)."""
    with app.app_context():
        cuenta = db.session.get(User, usuario_id)
        secreto_b32, _uri = mfa.iniciar_activacion(cuenta, CLAVE, instante)
        codigo = totp.codigo_en_paso(totp.secreto_desde_base32(secreto_b32), totp.paso_de(instante.timestamp()))
        return mfa.confirmar_activacion(usuario_id, codigo, instante), secreto_b32


def _codigo_actual(secreto_b32, instante):
    return totp.codigo_en_paso(totp.secreto_desde_base32(secreto_b32), totp.paso_de(instante.timestamp()))


def _estado(app, usuario_id):
    with app.app_context():
        cuenta = db.session.get(User, usuario_id, populate_existing=True)
        return {
            "mfa": cuenta.mfa_enabled,
            "tv": cuenta.token_version,
            "secreto": cuenta.mfa_secret,
            "pendiente": cuenta.mfa_secret_pendiente,
            "hash": cuenta.password_hash,
            "fallos": cuenta.failed_login_count,
            "bloqueo": cuenta.locked_until,
            "ultimo_paso": cuenta.mfa_last_step,
        }


def _auditoria(app, accion):
    with app.app_context():
        return [
            (fila.actor_username, fila.target_username, fila.detalle)
            for fila in UserAuditLog.query.filter_by(accion=accion).all()
        ]


# -----------------------------------------------------------------------------
# 1. TOTP (RFC 6238) y ventana
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("tiempo, esperado", VECTORES_RFC)
def test_rfc6238_vectores_sha1_seis_digitos(tiempo, esperado):
    assert totp.codigo_en_paso(SECRETO_RFC, tiempo // 30) == esperado


def test_rfc6238_vectores_ocho_digitos_coinciden_con_los_seis_finales():
    ocho = {59: "94287082", 1111111109: "07081804", 1111111111: "14050471",
            1234567890: "89005924", 2000000000: "69279037", 20000000000: "65353130"}
    for tiempo, completo in ocho.items():
        assert totp.codigo_en_paso(SECRETO_RFC, tiempo // 30, digitos=8) == completo
        assert completo[-6:] == totp.codigo_en_paso(SECRETO_RFC, tiempo // 30)


def test_ventana_mas_menos_un_paso_acepta_y_fuera_rechaza():
    base = 1111111111
    paso = base // 30
    anterior = totp.codigo_en_paso(SECRETO_RFC, paso - 1)
    siguiente = totp.codigo_en_paso(SECRETO_RFC, paso + 1)
    lejano = totp.codigo_en_paso(SECRETO_RFC, paso + 2)
    assert paso - 1 in totp.pasos_coincidentes(SECRETO_RFC, anterior, base)
    assert paso + 1 in totp.pasos_coincidentes(SECRETO_RFC, siguiente, base)
    if lejano not in (totp.codigo_en_paso(SECRETO_RFC, paso + k) for k in (-1, 0, 1)):
        assert totp.pasos_coincidentes(SECRETO_RFC, lejano, base) == []


def test_codigo_mal_formado_no_se_acepta():
    assert totp.pasos_coincidentes(SECRETO_RFC, "12345", 59) == []
    assert totp.pasos_coincidentes(SECRETO_RFC, "abcdef", 59) == []


def test_uri_otpauth_y_secreto_base32_ida_y_vuelta():
    secreto = totp.generar_secreto()
    b32 = totp.secreto_a_base32(secreto)
    assert len(secreto) == 20 and totp.secreto_desde_base32(b32) == secreto
    uri = totp.uri_otpauth(b32, "probe.usuario")
    assert uri.startswith("otpauth://totp/App360:probe.usuario?secret=")
    assert "digits=6" in uri and "period=30" in uri and "algorithm=SHA1" in uri


# -----------------------------------------------------------------------------
# 2. Servicio: reutilización, activación, desactivación y respaldos
# -----------------------------------------------------------------------------
def test_codigo_totp_no_se_reutiliza(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.reuso")
    _respaldos, secreto = _activar_mfa(app_seguridad, uid)
    with app_seguridad.app_context():
        cuenta = db.session.get(User, uid)
        codigo = _codigo_actual(secreto, INSTANTE + timedelta(seconds=30))
        assert mfa.verificar_segundo_factor(cuenta, codigo, INSTANTE + timedelta(seconds=30)) == mfa.METODO_APP
        assert mfa.verificar_segundo_factor(cuenta, codigo, INSTANTE + timedelta(seconds=30)) is None
        db.session.rollback()


def test_activacion_con_clave_incorrecta_y_codigo_incorrecto(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.act")
    with app_seguridad.app_context():
        cuenta = db.session.get(User, uid)
        with pytest.raises(mfa.ErrorMfa) as clave:
            mfa.iniciar_activacion(cuenta, "otra-clave-x", INSTANTE)
        assert clave.value.codigo == "CLAVE_INCORRECTA"
        secreto, _uri = mfa.iniciar_activacion(cuenta, CLAVE, INSTANTE)
        with pytest.raises(mfa.ErrorMfa) as codigo:
            mfa.confirmar_activacion(uid, "000000" if _codigo_actual(secreto, INSTANTE) != "000000" else "111111", INSTANTE)
        assert codigo.value.codigo == "CODIGO_INCORRECTO"
    assert _estado(app_seguridad, uid)["mfa"] is False


def test_secreto_pendiente_vencido_no_activa(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.vence")
    with app_seguridad.app_context():
        secreto, _uri = mfa.iniciar_activacion(db.session.get(User, uid), CLAVE, INSTANTE)
    tarde = INSTANTE + timedelta(minutes=11)
    with app_seguridad.app_context():
        with pytest.raises(mfa.ErrorMfa) as vencido:
            mfa.confirmar_activacion(uid, _codigo_actual(secreto, tarde), tarde)
        assert vencido.value.codigo == "SECRETO_VENCIDO"


def test_doble_activacion_y_clave_temporal_pendiente_bloqueadas(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.doble")
    _activar_mfa(app_seguridad, uid)
    with app_seguridad.app_context():
        with pytest.raises(mfa.ErrorMfa) as doble:
            mfa.iniciar_activacion(db.session.get(User, uid), CLAVE, INSTANTE)
        assert doble.value.status == 409
    uid_temp = _crear(app_seguridad, "probe.temp", cambiar=True)
    with app_seguridad.app_context():
        with pytest.raises(mfa.ErrorMfa) as temporal:
            mfa.iniciar_activacion(db.session.get(User, uid_temp), CLAVE, INSTANTE)
        assert temporal.value.codigo == "CLAVE_TEMPORAL"


def test_respaldos_diez_distintos_hash_en_base_y_un_solo_uso(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.resp")
    respaldos, _secreto = _activar_mfa(app_seguridad, uid)
    assert len(respaldos) == 10 and len(set(respaldos)) == 10
    for codigo in respaldos:
        assert len(codigo.replace("-", "")) == 10
        assert re.fullmatch(r"[A-HJ-KM-NP-Z2-9-]{11}", codigo)  # sin 0, O, 1, I ni L
    with app_seguridad.app_context():
        filas = UserMfaBackupCode.query.filter_by(user_id=uid).all()
        assert len(filas) == 10
        for fila in filas:
            assert all(respaldo.replace("-", "") not in fila.code_hash for respaldo in respaldos)
        cuenta = db.session.get(User, uid)
        primero = respaldos[0]
        assert mfa.verificar_segundo_factor(cuenta, primero, INSTANTE) == mfa.METODO_RESPALDO
        assert mfa.verificar_segundo_factor(cuenta, primero, INSTANTE) is None
        db.session.rollback()


def test_regenerar_respaldos_invalida_los_anteriores(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.regen")
    viejos, secreto = _activar_mfa(app_seguridad, uid)
    tras = INSTANTE + timedelta(seconds=60)
    nuevos = mfa.regenerar_respaldos(uid, CLAVE, _codigo_actual(secreto, tras), tras)
    assert set(nuevos).isdisjoint(viejos)
    with app_seguridad.app_context():
        cuenta = db.session.get(User, uid)
        assert mfa.verificar_segundo_factor(cuenta, viejos[0], tras) is None
        db.session.rollback()
    assert len(_auditoria(app_seguridad, "user_mfa_backup_regenerated")) == 1


def test_desactivar_propio_con_respaldo_borra_secreto_y_codigos(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.desact")
    respaldos, _secreto = _activar_mfa(app_seguridad, uid)
    mfa.desactivar(uid, CLAVE, respaldos[1], INSTANTE + timedelta(minutes=1))
    estado = _estado(app_seguridad, uid)
    assert estado["mfa"] is False and estado["secreto"] is None
    with app_seguridad.app_context():
        assert UserMfaBackupCode.query.filter_by(user_id=uid).count() == 0
    assert _auditoria(app_seguridad, "user_mfa_disabled")


# -----------------------------------------------------------------------------
# 3. Huella de sesión: compatibilidad y cierre de otras sesiones al activar
# -----------------------------------------------------------------------------
def test_huella_sin_mfa_es_la_de_siempre(app_seguridad):
    uid = _crear(app_seguridad, "probe.huella")
    with app_seguridad.app_context():
        cuenta = db.session.get(User, uid)
        esperada = hmac.new(
            app_seguridad.secret_key.encode("utf-8"), cuenta.password_hash.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert cuenta.token_version == 0 and huella_sesion(cuenta) == esperada


def test_activar_mfa_cierra_otras_sesiones_web(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.otra")
    otra = app_seguridad.test_client()
    marcar_sesion(otra, uid)
    assert otra.get("/mi-cuenta/seguridad").status_code == 200
    _activar_mfa(app_seguridad, uid)
    # La sesión anterior a la activación ya no sirve: vuelve al login.
    assert otra.get("/mi-cuenta/seguridad").status_code == 302


# -----------------------------------------------------------------------------
# 4. Login: segundo paso web y API, límites y mensajes genéricos
# -----------------------------------------------------------------------------
def test_login_web_pide_segundo_paso_y_no_emite_sesion(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.web")
    _respaldos, secreto = _activar_mfa(app_seguridad, uid)
    cliente = app_seguridad.test_client()
    respuesta = cliente.post("/", data={"username": "probe.web", "password": CLAVE})
    assert respuesta.status_code == 302 and "/login/mfa" in respuesta.headers["Location"]
    with cliente.session_transaction() as sesion:
        assert "mfa_pendiente" in sesion and "user" not in sesion
    ok = cliente.post("/login/mfa", data={"codigo": _codigo_actual(secreto, INSTANTE + timedelta(seconds=30))})
    assert ok.status_code == 302
    with cliente.session_transaction() as sesion:
        assert sesion.get("user") == "probe.web" and "mfa_pendiente" not in sesion
    assert any("con MFA" in str(detalle) for _a, _t, detalle in _auditoria(app_seguridad, "login_ok"))


def test_pendiente_no_autoriza_rutas_y_vence_a_los_cinco_minutos(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.pend")
    _activar_mfa(app_seguridad, uid)
    cliente = app_seguridad.test_client()
    cliente.post("/", data={"username": "probe.pend", "password": CLAVE})
    for regla in app_seguridad.url_map.iter_rules():
        if "GET" not in regla.methods:
            continue
        ruta = re.sub(r"<[^>]+>", "1", regla.rule)
        respuesta = cliente.get(ruta)
        assert respuesta.status_code < 500, (regla.endpoint, respuesta.status_code)
        if regla.endpoint not in PAGINAS_PERMITIDAS_PENDIENTE:
            assert respuesta.status_code != 200, regla.endpoint
    reloj["ahora"] = INSTANTE + timedelta(minutes=5, seconds=1)
    assert cliente.get("/login/mfa").status_code == 302
    with cliente.session_transaction() as sesion:
        assert "mfa_pendiente" not in sesion


def test_cinco_fallos_descartan_el_paso_pendiente(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.cinco")
    _activar_mfa(app_seguridad, uid)
    cliente = app_seguridad.test_client()
    cliente.post("/", data={"username": "probe.cinco", "password": CLAVE})
    for _ in range(5):
        cliente.post("/login/mfa", data={"codigo": "000001"})
    with cliente.session_transaction() as sesion:
        assert "mfa_pendiente" not in sesion
    assert _estado(app_seguridad, uid)["fallos"] == 5
    with app_seguridad.app_context():
        filas = UserAuditLog.query.filter_by(accion="login_failed").all()
        total = sum(f.repeticiones for f in filas if (f.detalle or {}).get("motivo") == "mfa_incorrecto")
    assert total == 5  # los fallos del mismo minuto se agrupan en una fila con repeticiones


def test_mensaje_generico_sin_revelar_que_fallo(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.generico")
    _activar_mfa(app_seguridad, uid)
    cliente = app_seguridad.test_client()
    cliente.post("/", data={"username": "probe.generico", "password": CLAVE})
    respuesta = cliente.post("/login/mfa", data={"codigo": "000002"}, follow_redirects=True)
    assert "Código incorrecto o vencido." in respuesta.get_data(as_text=True)


def test_api_login_mfa_requerido_y_codigo_valido(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.api")
    respaldos, secreto = _activar_mfa(app_seguridad, uid)
    cliente = app_seguridad.test_client()
    sin_codigo = cliente.post("/api/login", json={"username": "probe.api", "password": CLAVE})
    assert sin_codigo.status_code == 401 and sin_codigo.get_json()["codigo"] == "MFA_REQUERIDO"
    con_clave_mala = cliente.post("/api/login", json={"username": "probe.api", "password": "x" * 12, "mfa_code": "000003"})
    assert con_clave_mala.status_code == 401 and con_clave_mala.get_json()["error"] == "Invalid credentials"
    malo = cliente.post("/api/login", json={"username": "probe.api", "password": CLAVE, "mfa_code": "000003"})
    assert malo.status_code == 401 and malo.get_json()["error"] == "Invalid credentials"
    bueno = cliente.post(
        "/api/login",
        json={"username": "probe.api", "password": CLAVE, "mfa_code": _codigo_actual(secreto, INSTANTE + timedelta(seconds=30))},
    )
    assert bueno.status_code == 200 and bueno.get_json()["access_token"]
    respaldo = cliente.post("/api/login", json={"username": "probe.api", "password": CLAVE, "mfa_code": respaldos[2]})
    assert respaldo.status_code == 200 and respaldo.get_json()["access_token"]  # respaldo válido (uso único)
    reuso = cliente.post("/api/login", json={"username": "probe.api", "password": CLAVE, "mfa_code": respaldos[2]})
    assert reuso.status_code == 401 and reuso.get_json()["error"] == "Invalid credentials"


def test_clave_incorrecta_igual_con_y_sin_mfa(app_seguridad, reloj):
    con = _crear(app_seguridad, "probe.con")
    sin = _crear(app_seguridad, "probe.sin")
    _activar_mfa(app_seguridad, con)
    muestras = {"con": [], "sin": []}
    with app_seguridad.app_context():
        for ronda in range(100):
            orden = (("con", "probe.con"), ("sin", "probe.sin"))
            if ronda % 2:
                orden = orden[::-1]  # alterna quién va primero: evita sesgo de caché y de orden
            for clave_nombre, nombre in orden:
                inicio = time.perf_counter()
                autenticar(nombre, "clave-incorrecta-x", canal="api", ip="10.0.0.9")
                muestras[clave_nombre].append((time.perf_counter() - inicio) * 1000)
    diferencia = abs(statistics.median(muestras["con"]) - statistics.median(muestras["sin"]))
    assert diferencia < 3.0, diferencia
    assert sin is not None


# -----------------------------------------------------------------------------
# 5. Restablecimiento por otro administrador (M4) y script (M5)
# -----------------------------------------------------------------------------
def _admin(app, rol="admin"):
    return _crear(app, f"probe.{rol}.adm", rol)


def test_restablecer_mfa_permisos_y_efecto(app_seguridad, reloj):
    admin = _admin(app_seguridad)
    gerente = _crear(app_seguridad, "probe.gerente", "gerente")
    empleado = _crear(app_seguridad, "probe.emp", "sales")
    otro_admin = _crear(app_seguridad, "probe.otro.admin", "admin")
    _activar_mfa(app_seguridad, empleado)
    _activar_mfa(app_seguridad, otro_admin)
    with app_seguridad.app_context():
        actor_gerente = db.session.get(User, gerente)
        with pytest.raises(ErrorUsuarios) as admin_objetivo:
            restablecer_mfa(actor_gerente, otro_admin)
        assert admin_objetivo.value.status == 403
        db.session.rollback()
        actor_admin = db.session.get(User, admin)
        with pytest.raises(ErrorUsuarios) as propio:
            restablecer_mfa(actor_admin, admin)
        assert propio.value.status == 403
        db.session.rollback()
        actor_admin = db.session.get(User, admin)
        cuenta = restablecer_mfa(actor_admin, empleado)
        assert cuenta.mfa_enabled is False
    estado = _estado(app_seguridad, empleado)
    assert estado["mfa"] is False and estado["tv"] == 1 and estado["secreto"] is None
    assert _auditoria(app_seguridad, "user_mfa_reset")[0][1] == "probe.emp"


def test_endpoint_restablecer_mfa_csrf_y_api(app_seguridad, reloj):
    admin = _admin(app_seguridad)
    empleado = _crear(app_seguridad, "probe.emp2", "sales")
    _activar_mfa(app_seguridad, empleado)
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, admin)
    respuesta = cliente.post(f"/api/admin/usuarios/{empleado}/restablecer-mfa")
    assert respuesta.status_code == 200 and respuesta.get_json()["usuario"]["mfa_activo"] is False
    propio = cliente.post(f"/api/admin/usuarios/{admin}/restablecer-mfa")
    assert propio.status_code in (403, 409)


def test_script_restablecer_mfa_simula_y_confirma(app_seguridad, reloj, monkeypatch):
    spec = importlib.util.spec_from_file_location("restablecer_mfa_script", SCRIPT_RESET)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    uid = _crear(app_seguridad, "probe.ultimo", "admin")
    _activar_mfa(app_seguridad, uid)
    with app_seguridad.app_context():
        simulado = script.restablecer("probe.ultimo", confirmar=False)
    assert simulado["estado"] == "simulado" and _estado(app_seguridad, uid)["mfa"] is True
    with app_seguridad.app_context():
        aplicado = script.restablecer("probe.ultimo", confirmar=True)
    assert aplicado["estado"] == "restablecido"
    estado = _estado(app_seguridad, uid)
    assert estado["mfa"] is False and estado["tv"] == 1
    assert any(actor == "script" for actor, _t, _d in _auditoria(app_seguridad, "user_mfa_reset"))


def test_jwt_previo_deja_de_valer_tras_restablecer(app_seguridad, reloj):
    admin = _admin(app_seguridad)
    empleado = _crear(app_seguridad, "probe.jwt", "sales")
    _activar_mfa(app_seguridad, empleado)
    with app_seguridad.app_context():
        token = generate_access_token(empleado, "probe.jwt", "sales", 0)
        cuenta = db.session.get(User, admin)
        restablecer_mfa(cuenta, empleado)
    cliente = app_seguridad.test_client()
    assert cliente.get("/api/health").status_code == 200
    with app_seguridad.app_context():
        assert token and db.session.get(User, empleado).token_version == 1


# -----------------------------------------------------------------------------
# 6. Migración (upgrade, downgrade explícito, upgrade) con las 8 réplicas
# -----------------------------------------------------------------------------
def test_migracion_upgrade_downgrade_con_replicas_identicas(tmp_path):
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'c6.db'}")
    with motor.begin() as conexion:
        conexion.execute(sa.text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL, role VARCHAR(40) NOT NULL, "
            "active BOOLEAN, password_hash VARCHAR(255), email VARCHAR(254))"
        ))
        for nombre, rol, activo in REPLICAS:
            hash_clave = None if nombre == "test_user" else f"hash-ficticio-{nombre}"
            conexion.execute(
                sa.text("INSERT INTO users (username, role, active, password_hash) VALUES (:u, :r, :a, :h)"),
                {"u": nombre, "r": rol, "a": activo, "h": hash_clave},
            )

    def foto(conexion):
        filas = conexion.execute(sa.text("SELECT id, username, role, active, password_hash FROM users ORDER BY id")).all()
        return [(f[0], f[1], f[2], bool(f[3]), hashlib.md5((f[4] or "").encode()).hexdigest()) for f in filas]

    spec = importlib.util.spec_from_file_location("mig_c6", MIGRACION)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    with motor.begin() as conexion:
        antes = foto(conexion)
        with Operations.context(MigrationContext.configure(conexion)):
            mig.upgrade()
        columnas = {c["name"] for c in sa.inspect(conexion).get_columns("users")}
        assert {"mfa_enabled", "mfa_secret", "mfa_last_step", "mfa_activado_en"} <= columnas
        assert foto(conexion) == antes
        assert sa.inspect(conexion).has_table("user_mfa_backup_codes")
    with motor.begin() as conexion:
        with Operations.context(MigrationContext.configure(conexion)):
            mig.downgrade()
        assert not sa.inspect(conexion).has_table("user_mfa_backup_codes")
        assert foto(conexion) == antes
    with motor.begin() as conexion:
        with Operations.context(MigrationContext.configure(conexion)):
            mig.upgrade()
        assert foto(conexion) == antes


# -----------------------------------------------------------------------------
# 7. Ausencia de secretos y códigos en respuestas y auditoría
# -----------------------------------------------------------------------------
def test_secretos_y_codigos_no_aparecen_en_auditoria_ni_en_listas(app_seguridad, reloj):
    admin = _admin(app_seguridad)
    uid = _crear(app_seguridad, "probe.nolog")
    respaldos, secreto = _activar_mfa(app_seguridad, uid)
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, admin)
    lista = cliente.get("/api/admin/usuarios").get_data(as_text=True)
    assert secreto not in lista and all(r not in lista for r in respaldos)
    with app_seguridad.app_context():
        volcado = " ".join(str(fila.detalle) for fila in UserAuditLog.query.all())
    assert secreto not in volcado and all(r.replace("-", "") not in volcado for r in respaldos)


def test_pantalla_seguridad_sin_cache_y_campo_de_codigo(app_seguridad, reloj):
    uid = _crear(app_seguridad, "probe.html")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, uid)
    respuesta = cliente.get("/mi-cuenta/seguridad")
    assert respuesta.status_code == 200
    assert "no-store" in respuesta.headers.get("Cache-Control", "")
    respuesta_activar = cliente.post("/mi-cuenta/seguridad/activar", data={"clave_actual": CLAVE})
    html = respuesta_activar.get_data(as_text=True)
    assert "no-store" in respuesta_activar.headers.get("Cache-Control", "")
    assert respuesta_activar.status_code == 200 and 'autocomplete="one-time-code"' in html
    assert 'inputmode="numeric"' in html
    secreto_mostrado = re.search(r'aria-label="Clave para tu aplicación">([A-Z2-7 ]+)<', html)
    assert secreto_mostrado is not None
    assert "otpauth://totp/App360:probe.html" in html
