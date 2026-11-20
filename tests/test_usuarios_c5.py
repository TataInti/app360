"""Administración de usuarios (C5): correo opcional, enlace de recuperación de clave y canje público.

Datos sintéticos rotulados PROBE sobre SQLite en memoria (lo mismo que corre en CI). Las pruebas con
concurrencia real (carrera de canjes y canje frente a revocación) corren solo si APP360_PRUEBAS_PG_URL
apunta a una base de prueba cuyo nombre contenga «carrera»; en CI quedan omitidas y se declara en el PR.
La medición de tiempos parejos corre con APP360_PRUEBAS_TIEMPOS=1 (en la instancia C5). La migración se
prueba con Alembic sobre SQLite con las 8 réplicas; la prueba sobre PostgreSQL se hace en la instancia.
"""

import hashlib
import hmac
import importlib.util
import json
import os
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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
from models.core.user_recovery_token import UserRecoveryToken
from security import generate_access_token, huella_sesion
from services import recuperacion_clave as rc
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-c5-2026"
NUEVA = "PROBE-nueva-clave-c5-2026"
INSTANTE = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "20261120_usuarios_c5_recuperacion.py"
PURGA = RAIZ / "scripts" / "purgar_auditoria_usuarios.py"
PG_URL_ENV = "APP360_PRUEBAS_PG_URL"
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
RUTA_CANJE = "/recuperar-clave"


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


@pytest.fixture(autouse=True)
def _direccion_publica_fija(monkeypatch):
    """Dirección pública fija para los enlaces: no depende de FLASK_ENV ni de SERVER_NAME del entorno."""
    monkeypatch.setattr(Config, "APP_PUBLIC_URL", "https://vyp.ejemplo.test", raising=False)


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


@pytest.fixture
def app_limitado(monkeypatch):
    """App con el limitador activo (límites por IP del canje público)."""
    from app import create_app
    from extensions import limiter

    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "test-admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(Config, "WTF_CSRF_CHECK_DEFAULT", False, raising=False)
    aplicacion = create_app()
    aplicacion.config["TESTING"] = True
    with aplicacion.app_context():
        db.create_all()
        limiter.reset()
        monkeypatch.setattr(limiter, "enabled", True)
        yield aplicacion
        db.session.remove()
        db.drop_all()


def _crear(app, usuario, rol="sales", *, clave=CLAVE, activo=True, correo=None, cambiar=False):
    with app.app_context():
        cuenta = User(username=usuario, role=rol, active=activo, email=correo)
        db.session.add(cuenta)
        cuenta.set_password(clave)
        cuenta.must_change_password = cambiar
        cuenta.deactivated_at = None if activo else INSTANTE
        db.session.commit()
        return cuenta.id


def _cliente_con_sesion(app, usuario_id):
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _admin(app):
    return _cliente_con_sesion(app, _crear(app, "probe.admin", "admin"))


def _estado(app, usuario_id):
    with app.app_context():
        cuenta = db.session.get(User, usuario_id, populate_existing=True)
        return {
            "hash": cuenta.password_hash,
            "tv": cuenta.token_version,
            "must": cuenta.must_change_password,
            "fallos": cuenta.failed_login_count,
            "bloqueo": cuenta.locked_until,
            "activo": cuenta.active,
            "correo": cuenta.email,
        }


def _enlaces(app, usuario_id):
    with app.app_context():
        filas = UserRecoveryToken.query.filter_by(user_id=usuario_id).order_by(UserRecoveryToken.id).all()
        return [
            {
                "id": f.id,
                "used": f.used_at,
                "revoked": f.revoked_at,
                "expires": f.expires_at,
                "hash": f.token_hash,
            }
            for f in filas
        ]


def _filas_auditoria(app, accion=None):
    with app.app_context():
        consulta = UserAuditLog.query
        if accion:
            consulta = consulta.filter_by(accion=accion)
        return [
            {"accion": f.accion, "actor": f.actor_username, "objetivo": f.target_username,
             "actor_id": f.actor_user_id, "detalle": f.detalle or {}, "rep": f.repeticiones}
            for f in consulta.order_by(UserAuditLog.id).all()
        ]


def _emitir(cliente, usuario_id, ttl=30):
    return cliente.post(f"/api/admin/usuarios/{usuario_id}/recuperacion", json={"ttl": ttl})


def _token_de(respuesta):
    return respuesta.get_json()["enlace"].split("#", 1)[1]


def _canjear(cliente, token, clave=NUEVA, repetida=None):
    return cliente.post(
        RUTA_CANJE,
        data={"token": token, "new_password": clave, "confirm": clave if repetida is None else repetida},
    )


def _sin_csrf(respuesta):
    """Cuerpo de la página sin el valor del token CSRF (cambia en cada respuesta)."""
    texto = respuesta.get_data(as_text=True)
    return re.sub(r'name="csrf_token" value="[^"]*"', 'name="csrf_token" value="X"', texto)


def _fila_usuario(cliente, nombre):
    datos = cliente.get("/api/admin/usuarios?q=" + nombre).get_json()
    return next(u for u in datos["usuarios"] if u["username"] == nombre)


# -----------------------------------------------------------------------------
# B1. Correo opcional
# -----------------------------------------------------------------------------
def test_correo_valido_se_guarda_en_minusculas_y_se_recorta(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.correo")
    cliente = _admin(app)
    respuesta = cliente.post(f"/api/admin/usuarios/{uid}/correo", json={"email": "  Ana.Perez+x@Dominio.COM "})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["usuario"]["correo"] == "ana.perez+x@dominio.com"
    assert _estado(app, uid)["correo"] == "ana.perez+x@dominio.com"


@pytest.mark.parametrize(
    "invalido",
    [
        "sin-arroba", "a@b", "a@@b.com", "a b@x.com", ".a@x.com", "a..b@x.com", "a@x-.com", "a@x.c",
        "ñandu@x.com", "a@x..com", "a@-x.com", "a@x.com.", "@x.com", "a@x_y.com",
        "a" * 65 + "@x.com", "a@" + "x" * 64 + ".com",
    ],
)
def test_correo_con_formato_invalido_responde_400_con_campo(app_seguridad, invalido):
    app = app_seguridad
    uid = _crear(app, "probe.formato")
    respuesta = _admin(app).post(f"/api/admin/usuarios/{uid}/correo", json={"email": invalido})
    assert respuesta.status_code == 400
    assert "email" in respuesta.get_json()["campos"]
    assert _estado(app, uid)["correo"] is None


def test_correo_largo_de_255_caracteres_responde_400(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.largo")
    correo = "a" * 249 + "@x.com"
    assert len(correo) == 255
    respuesta = _admin(app).post(f"/api/admin/usuarios/{uid}/correo", json={"email": correo})
    assert respuesta.status_code == 400
    assert _estado(app, uid)["correo"] is None


def test_correo_vacio_borra_y_audita(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.vacio", correo="vacio@dominio.com")
    cliente = _admin(app)
    respuesta = cliente.post(f"/api/admin/usuarios/{uid}/correo", json={"email": "   "})
    assert respuesta.status_code == 200 and respuesta.get_json()["cambiado"] is True
    assert _estado(app, uid)["correo"] is None
    assert _filas_auditoria(app, "user_email_changed")[-1]["detalle"] == {"correo": "(borrado)"}


def test_correo_sin_clave_email_responde_400_y_no_borra(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.sinclave", correo="conserva@dominio.com")
    respuesta = _admin(app).post(f"/api/admin/usuarios/{uid}/correo", json={})
    assert respuesta.status_code == 400
    assert _estado(app, uid)["correo"] == "conserva@dominio.com"


def test_correo_duplicado_sin_distinguir_mayusculas_responde_409(app_seguridad):
    app = app_seguridad
    _crear(app, "probe.uno", correo="ventas@dominio.com")
    uid = _crear(app, "probe.dos")
    cliente = _admin(app)
    respuesta = cliente.post(f"/api/admin/usuarios/{uid}/correo", json={"email": "VENTAS@Dominio.com"})
    assert respuesta.status_code == 409
    assert respuesta.get_json()["codigo"] == "CORREO_DUPLICADO"
    assert _estado(app, uid)["correo"] is None


def test_alta_con_correo_duplicado_responde_409(app_seguridad):
    app = app_seguridad
    _crear(app, "probe.ocupado", correo="uno@dominio.com")
    respuesta = _admin(app).post(
        "/api/admin/usuarios", json={"username": "probe.nuevo", "role": "sales", "email": "UNO@dominio.com"}
    )
    assert respuesta.status_code == 409
    assert respuesta.get_json()["codigo"] == "CORREO_DUPLICADO"


def test_alta_con_correo_valido_lo_guarda_y_audita_enmascarado(app_seguridad):
    app = app_seguridad
    cliente = _admin(app)
    respuesta = cliente.post(
        "/api/admin/usuarios", json={"username": "probe.alta", "role": "sales", "email": "Compras@Empresa.com.ar"}
    )
    assert respuesta.status_code == 201
    assert respuesta.get_json()["usuario"]["correo"] == "compras@empresa.com.ar"
    alta = _filas_auditoria(app, "user_created")[-1]
    assert alta["detalle"].get("correo") == "c***@empresa.com.ar"


def test_correo_redos_entrada_larga_responde_rapido(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.redos")
    cliente = _admin(app)
    comienzo = time.perf_counter()
    for entrada in ["a" * 200_000 + "@" + "b" * 200_000, "a." * 100_000 + "@x", "a@" + "b." * 100_000]:
        assert cliente.post(f"/api/admin/usuarios/{uid}/correo", json={"email": entrada}).status_code == 400
    assert time.perf_counter() - comienzo < 2.0


def test_correo_auditoria_enmascarada_y_sin_correo_completo(app_seguridad, caplog):
    app = app_seguridad
    uid = _crear(app, "probe.mascara")
    with caplog.at_level("DEBUG"):
        _admin(app).post(f"/api/admin/usuarios/{uid}/correo", json={"email": "maria.lopez@ejemplo.com"})
    evento = _filas_auditoria(app, "user_email_changed")[-1]
    assert evento["detalle"] == {"correo": "m***@ejemplo.com"}
    assert "maria.lopez@ejemplo.com" not in json.dumps(evento, ensure_ascii=False)
    assert "maria.lopez@ejemplo.com" not in caplog.text


@pytest.mark.parametrize("rol_usuario", ["ventas", "rrhh", "tesoreria", "direccion", "anibal.lopez"])
def test_correo_solo_para_administracion(app_seguridad, rol_usuario):
    app = app_seguridad
    roles = {"ventas": "sales", "rrhh": "hr", "tesoreria": "caja", "direccion": "director", "anibal.lopez": "sales"}
    objetivo = _crear(app, "probe.objetivo")
    cliente = _cliente_con_sesion(app, _crear(app, rol_usuario, roles[rol_usuario]))
    assert cliente.post(f"/api/admin/usuarios/{objetivo}/correo", json={"email": "x@dominio.com"}).status_code == 403
    assert _estado(app, objetivo)["correo"] is None


def test_correo_anonimo_responde_401(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.anon")
    assert app.test_client().post(f"/api/admin/usuarios/{uid}/correo", json={"email": "a@dominio.com"}).status_code == 401


# -----------------------------------------------------------------------------
# B2. Emitir enlace de recuperación
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("rol_usuario", ["ventas", "rrhh", "tesoreria", "direccion", "anibal.lopez"])
def test_emitir_solo_para_administracion(app_seguridad, reloj, rol_usuario):
    app = app_seguridad
    roles = {"ventas": "sales", "rrhh": "hr", "tesoreria": "caja", "direccion": "director", "anibal.lopez": "sales"}
    objetivo = _crear(app, "probe.objetivo")
    cliente = _cliente_con_sesion(app, _crear(app, rol_usuario, roles[rol_usuario]))
    assert _emitir(cliente, objetivo).status_code == 403
    assert _enlaces(app, objetivo) == []


def test_emitir_anonimo_responde_401_json(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.anonimo")
    respuesta = _emitir(app.test_client(), uid)
    assert respuesta.status_code == 401
    assert respuesta.is_json


def test_emitir_con_jwt_sin_sesion_responde_401(app_seguridad, reloj):
    app = app_seguridad
    admin_id = _crear(app, "probe.admin.jwt", "admin")
    objetivo = _crear(app, "probe.objetivo.jwt")
    with app.app_context():
        token = generate_access_token(admin_id, "probe.admin.jwt", "admin")
    respuesta = app.test_client().post(
        f"/api/admin/usuarios/{objetivo}/recuperacion",
        json={"ttl": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 401
    assert "Sesión requerida" in respuesta.get_json()["error"]
    assert _enlaces(app, objetivo) == []


def test_emitir_exige_csrf_y_no_cambia_nada_sin_el(csrf_activo, reloj):
    app = csrf_activo
    objetivo = _crear(app, "probe.csrf")
    antes = _estado(app, objetivo)
    respuesta = _admin(app).post(f"/api/admin/usuarios/{objetivo}/recuperacion", json={"ttl": 30})
    assert respuesta.status_code == 400
    assert _enlaces(app, objetivo) == []
    assert _estado(app, objetivo) == antes


def test_emitir_para_uno_mismo_responde_403_autoobjetivo(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    yo = _crear(app, "probe.yo", "gerente")
    cliente_yo = _cliente_con_sesion(app, yo)
    respuesta = _emitir(cliente_yo, yo)
    assert respuesta.status_code == 403
    assert respuesta.get_json()["codigo"] == "AUTOOBJETIVO"
    assert "Cambiar mi clave" in respuesta.get_json()["error"]
    assert _enlaces(app, yo) == []
    assert cliente.get("/api/admin/usuarios").status_code == 200


def test_emitir_a_cuenta_inactiva_responde_409(app_seguridad, reloj):
    app = app_seguridad
    inactiva = _crear(app, "probe.inactiva", activo=False)
    respuesta = _emitir(_admin(app), inactiva)
    assert respuesta.status_code == 409
    assert respuesta.get_json()["codigo"] == "USUARIO_INACTIVO"
    assert _enlaces(app, inactiva) == []


@pytest.mark.parametrize("ttl", [0, 4, 1441, "abc", True, None, 99999999999999999999])
def test_ttl_fuera_de_rango_responde_400(app_seguridad, reloj, ttl):
    app = app_seguridad
    objetivo = _crear(app, "probe.ttl")
    respuesta = _emitir(_admin(app), objetivo, ttl=ttl)
    assert respuesta.status_code == 400
    assert "ttl" in respuesta.get_json()["campos"]
    assert _enlaces(app, objetivo) == []


def test_ttl_limites_5_y_1440_son_validos(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.limites")
    assert _emitir(cliente, objetivo, ttl=5).status_code == 201
    assert _emitir(cliente, objetivo, ttl=1440).status_code == 201


def test_limite_de_5_emisiones_cada_10_minutos_por_administrador(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivos = [_crear(app, f"probe.lim{i}") for i in range(7)]
    for uid in objetivos[:5]:
        assert _emitir(cliente, uid).status_code == 201
    respuesta = _emitir(cliente, objetivos[5])
    assert respuesta.status_code == 429
    assert respuesta.get_json()["codigo"] == "LIMITE_EMISIONES"
    reloj["ahora"] = INSTANTE + timedelta(minutes=10, seconds=1)
    assert _emitir(cliente, objetivos[6]).status_code == 201


def test_ids_inexistentes_responden_404_json(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    for uid in (999_999, 0, 2_147_483_647):
        respuesta = _emitir(cliente, uid)
        assert respuesta.status_code == 404
        assert respuesta.is_json and respuesta.get_json()["codigo"] == "USUARIO_NO_ENCONTRADO"


def test_el_enlace_se_muestra_una_vez_y_no_queda_en_ningun_lugar(app_seguridad, reloj, caplog):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.unavez", correo="unavez@dominio.com")
    with caplog.at_level("DEBUG"):
        respuesta = _emitir(cliente, objetivo)
        token = _token_de(respuesta)
    assert respuesta.status_code == 201
    assert "no-store" in respuesta.headers.get("Cache-Control", "")
    assert len(token) >= 43
    paginas = [
        cliente.get("/api/admin/usuarios").get_data(as_text=True),
        cliente.get("/api/admin/usuarios/auditoria").get_data(as_text=True),
        cliente.get("/admin/usuarios").get_data(as_text=True),
        cliente.get("/admin/usuarios/auditoria").get_data(as_text=True),
    ]
    with app.app_context():
        volcado = json.dumps([
            {c.name: str(getattr(f, c.name)) for c in UserRecoveryToken.__table__.columns}
            for f in UserRecoveryToken.query.all()
        ])
        volcado += json.dumps([f.detalle or {} for f in UserAuditLog.query.all()], ensure_ascii=False)
    for texto in paginas + [volcado, caplog.text]:
        assert texto.count(token) == 0
    with app.app_context():
        fila = UserRecoveryToken.query.filter_by(user_id=objetivo).one()
        assert fila.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert fila.token_hash != token and len(fila.token_hash) == 64


def test_un_enlace_nuevo_revoca_el_anterior(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.reemplazo")
    _emitir(cliente, objetivo)
    _emitir(cliente, objetivo)
    primero, segundo = _enlaces(app, objetivo)
    assert primero["revoked"] is not None
    assert segundo["revoked"] is None and segundo["used"] is None
    assert _filas_auditoria(app, "user_recovery_issued")[-1]["detalle"]["reemplazados"] == 1


def test_efecto_d2_clave_anterior_sesiones_y_jwt_caen(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.d2", "sales")
    otro = _crear(app, "probe.otro", "sales")
    sesion = _cliente_con_sesion(app, objetivo)
    assert sesion.get("/").status_code == 302
    with app.app_context():
        token_jwt = generate_access_token(objetivo, "probe.d2", "sales", 0)
    cabecera = {"Authorization": f"Bearer {token_jwt}"}
    assert app.test_client().get("/api/me", headers=cabecera).status_code == 200
    with app.app_context():
        huella_otro_antes = huella_sesion(db.session.get(User, otro))
    antes = _estado(app, objetivo)
    assert app.test_client().post("/api/login", json={"username": "probe.d2", "password": CLAVE}).status_code == 200

    _emitir(cliente, objetivo)

    despues = _estado(app, objetivo)
    assert despues["hash"] != antes["hash"] and despues["tv"] == antes["tv"] + 1
    assert despues["must"] == antes["must"]
    assert app.test_client().post("/api/login", json={"username": "probe.d2", "password": CLAVE}).status_code == 401
    assert sesion.get("/").status_code == 200, "la sesión web previa debe quedar cerrada"
    assert app.test_client().get("/api/me", headers=cabecera).status_code == 401
    with app.app_context():
        assert huella_sesion(db.session.get(User, otro)) == huella_otro_antes


def test_huella_con_version_cero_es_la_de_antes_de_c5(app_seguridad):
    app = app_seguridad
    uid = _crear(app, "probe.huella")
    with app.app_context():
        cuenta = db.session.get(User, uid)
        esperada = hmac.new(
            app.secret_key.encode("utf-8"), cuenta.password_hash.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert cuenta.token_version == 0
        assert huella_sesion(cuenta) == esperada


def test_sin_direccion_publica_responde_409_y_no_toca_la_cuenta(app_seguridad, reloj, monkeypatch):
    app = app_seguridad
    monkeypatch.setitem(app.config, "APP_PUBLIC_URL", None)
    monkeypatch.setitem(app.config, "SERVER_NAME", None)
    objetivo = _crear(app, "probe.sindireccion")
    antes = _estado(app, objetivo)
    respuesta = _emitir(_admin(app), objetivo)
    assert respuesta.status_code == 409
    assert respuesta.get_json()["codigo"] == "SIN_DIRECCION_PUBLICA"
    assert _enlaces(app, objetivo) == [] and _estado(app, objetivo) == antes


def test_el_host_del_enlace_sale_de_configuracion_no_de_cabeceras(app_seguridad, reloj, monkeypatch):
    app = app_seguridad
    monkeypatch.setitem(app.config, "APP_PUBLIC_URL", "https://vyp.ejemplo.test/")
    objetivo = _crear(app, "probe.host")
    respuesta = _admin(app).post(
        f"/api/admin/usuarios/{objetivo}/recuperacion",
        json={"ttl": 30},
        headers={"X-Forwarded-Host": "atacante.example"},
    )
    assert respuesta.get_json()["enlace"].startswith("https://vyp.ejemplo.test/recuperar-clave#")


def test_lista_muestra_correo_y_estado_del_enlace(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.lista", correo="lista@dominio.com")
    assert _fila_usuario(cliente, "probe.lista")["correo"] == "lista@dominio.com"
    assert _fila_usuario(cliente, "probe.lista")["recuperacion"] is None
    _emitir(cliente, objetivo)
    recuperacion = _fila_usuario(cliente, "probe.lista")["recuperacion"]
    assert recuperacion["estado"] == "vigente"
    assert recuperacion["nombre"].startswith("Enlace de recuperación vigente hasta ")
    reloj["ahora"] = INSTANTE + timedelta(minutes=31)
    assert _fila_usuario(cliente, "probe.lista")["recuperacion"]["nombre"] == "Enlace vencido"


# -----------------------------------------------------------------------------
# B3. Revocar
# -----------------------------------------------------------------------------
def test_revocar_deja_la_cuenta_sin_clave_utilizable(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.revoca")
    token = _token_de(_emitir(cliente, objetivo))
    rid = _enlaces(app, objetivo)[-1]["id"]
    respuesta = cliente.post(f"/api/admin/usuarios/{objetivo}/recuperacion/{rid}/revocar")
    assert respuesta.status_code == 200
    assert _fila_usuario(cliente, "probe.revoca")["recuperacion"]["nombre"] == "Recuperación pendiente"
    assert _filas_auditoria(app, "user_recovery_revoked")[-1]["detalle"] == {"recuperacion_id": rid}
    assert _canjear(app.test_client(), token).status_code == 400
    assert app.test_client().post("/api/login", json={"username": "probe.revoca", "password": CLAVE}).status_code == 401


def test_revocar_inexistente_o_no_vigente_responde_409(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.revoca2")
    _emitir(cliente, objetivo)
    rid = _enlaces(app, objetivo)[-1]["id"]
    assert cliente.post(f"/api/admin/usuarios/{objetivo}/recuperacion/{rid}/revocar").status_code == 200
    for ruta in (f"/api/admin/usuarios/{objetivo}/recuperacion/{rid}/revocar", f"/api/admin/usuarios/{objetivo}/recuperacion/9999/revocar"):
        respuesta = cliente.post(ruta)
        assert respuesta.status_code == 409 and respuesta.get_json()["codigo"] == "RECOVERY_NOT_ACTIVE"


def test_revocar_exige_permiso_y_csrf(csrf_activo, reloj):
    app = csrf_activo
    objetivo = _crear(app, "probe.revoca3")
    with app.app_context():
        fila = UserRecoveryToken(
            user_id=objetivo, token_hash="0" * 64, expires_at=INSTANTE + timedelta(minutes=30),
            created_at=INSTANTE,
        )
        db.session.add(fila)
        db.session.commit()
        rid = fila.id
    ventas = _cliente_con_sesion(app, _crear(app, "probe.ventas.rev", "sales"))
    assert ventas.post(f"/api/admin/usuarios/{objetivo}/recuperacion/{rid}/revocar").status_code == 400
    assert _enlaces(app, objetivo)[0]["revoked"] is None


def test_restablecer_clave_revoca_los_enlaces_vigentes(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.reset")
    token = _token_de(_emitir(cliente, objetivo))
    assert cliente.post(f"/api/admin/usuarios/{objetivo}/restablecer-clave").status_code == 200
    assert _enlaces(app, objetivo)[-1]["revoked"] is not None
    assert _canjear(app.test_client(), token).status_code == 400


# -----------------------------------------------------------------------------
# B4. Canje público
# -----------------------------------------------------------------------------
def test_pagina_de_canje_sin_sesion_y_con_cabeceras(app_seguridad):
    app = app_seguridad
    respuesta = app.test_client().get(RUTA_CANJE)
    assert respuesta.status_code == 200
    assert "no-store" in respuesta.headers["Cache-Control"]
    assert respuesta.headers["Referrer-Policy"] == "no-referrer"
    assert respuesta.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "recuperar_clave.js" in respuesta.get_data(as_text=True)


def test_la_pagina_no_depende_del_token_en_la_query(app_seguridad):
    app = app_seguridad
    texto_sin = app.test_client().get(RUTA_CANJE).get_data(as_text=True)
    respuesta = app.test_client().get(RUTA_CANJE + "?token=" + "A" * 43)
    assert respuesta.status_code == 200
    assert ("A" * 43) not in respuesta.get_data(as_text=True)
    assert _sin_csrf(respuesta).count("name=\"token\"") == texto_sin.count("name=\"token\"") == 1


def test_canje_exitoso_cambia_clave_y_limpia_estado(app_seguridad, reloj):
    app = app_seguridad
    cliente = _admin(app)
    objetivo = _crear(app, "probe.canje", "sales", cambiar=True)
    with app.app_context():
        cuenta = db.session.get(User, objetivo)
        cuenta.failed_login_count, cuenta.locked_until = 4, INSTANTE + timedelta(minutes=15)
        db.session.commit()
    token = _token_de(_emitir(cliente, objetivo))
    publica = app.test_client()
    respuesta = _canjear(publica, token)
    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/")
    estado = _estado(app, objetivo)
    assert estado["must"] is False and estado["fallos"] == 0 and estado["bloqueo"] is None
    assert estado["tv"] == 2
    assert _enlaces(app, objetivo)[-1]["used"] is not None
    ingreso = app.test_client().post("/", data={"username": "probe.canje", "password": NUEVA})
    assert ingreso.status_code == 302 and "cambiar" not in ingreso.headers["Location"]
    assert app.test_client().post("/api/login", json={"username": "probe.canje", "password": NUEVA}).status_code == 200
    evento = _filas_auditoria(app, "user_recovery_redeemed")[-1]
    assert evento["actor"] == "probe.canje" and evento["actor_id"] == objetivo
    assert "recuperacion_id" in evento["detalle"]


def test_canje_quita_la_clave_temporal_y_su_vencimiento(app_seguridad, reloj):
    app = app_seguridad
    objetivo = _crear(app, "probe.temporal", cambiar=True)
    with app.app_context():
        db.session.get(User, objetivo).temp_password_expires_at = INSTANTE + timedelta(hours=72)
        db.session.commit()
    token = _token_de(_emitir(_admin(app), objetivo))
    assert _canjear(app.test_client(), token).status_code == 302
    assert _estado(app, objetivo)["must"] is False
    with app.app_context():
        assert db.session.get(User, objetivo).temp_password_expires_at is None


def test_el_mismo_enlace_dos_veces_responde_generico(app_seguridad, reloj):
    app = app_seguridad
    token = _token_de(_emitir(_admin(app), _crear(app, "probe.dos_veces")))
    primera = _canjear(app.test_client(), token)
    segunda = _canjear(app.test_client(), token)
    assert primera.status_code == 302 and segunda.status_code == 400
    assert "No pudimos usar este enlace" in segunda.get_data(as_text=True)


def _respuestas_invalidas(app, reloj):
    """Respuestas a enlaces inválidos de todos los motivos, para comparar que sean idénticas."""
    cliente_admin = _admin(app)
    publica = app.test_client()
    respuestas = {}
    respuestas["inexistente"] = _canjear(publica, "x" * 43)
    token_base = _token_de(_emitir(cliente_admin, _crear(app, "probe.base")))
    respuestas["corto_31"] = _canjear(publica, "a" * 31)
    respuestas["largo_5000"] = _canjear(publica, "a" * 5000)
    respuestas["espacio_interno"] = _canjear(publica, token_base[:20] + " " + token_base[20:])
    respuestas["control"] = _canjear(publica, token_base[:20] + "\x00" + token_base[20:])
    respuestas["vencido"] = None
    uid_v = _crear(app, "probe.vence")
    token_v = _token_de(_emitir(cliente_admin, uid_v, ttl=5))
    reloj["ahora"] = INSTANTE + timedelta(minutes=6)
    respuestas["vencido"] = _canjear(publica, token_v)
    reloj["ahora"] = INSTANTE
    uid_r = _crear(app, "probe.revocado")
    token_r = _token_de(_emitir(cliente_admin, uid_r))
    cliente_admin.post(f"/api/admin/usuarios/{uid_r}/recuperacion/{_enlaces(app, uid_r)[-1]['id']}/revocar")
    respuestas["revocado"] = _canjear(publica, token_r)
    uid_i = _crear(app, "probe.inactivo_c5")
    token_i = _token_de(_emitir(cliente_admin, uid_i))
    with app.app_context():
        db.session.get(User, uid_i).active = False
        db.session.commit()
    respuestas["inactivo"] = _canjear(publica, token_i)
    return respuestas


def test_todos_los_motivos_invalidos_responden_identico(app_seguridad, reloj):
    app = app_seguridad
    respuestas = _respuestas_invalidas(app, reloj)
    referencia = _sin_csrf(respuestas["inexistente"])
    for motivo, respuesta in respuestas.items():
        assert respuesta.status_code == 400, motivo
        assert _sin_csrf(respuesta) == referencia, motivo


def test_clave_que_no_cumple_politica_no_consume_el_token(app_seguridad, reloj):
    app = app_seguridad
    objetivo = _crear(app, "probe.politica")
    token = _token_de(_emitir(_admin(app), objetivo))
    publica = app.test_client()
    corta = _canjear(publica, token, clave="corta")
    assert corta.status_code == 400
    assert "al menos 12 caracteres" in corta.get_data(as_text=True)
    assert _enlaces(app, objetivo)[-1]["used"] is None
    assert _canjear(publica, token, clave=NUEVA, repetida="otra clave distinta").status_code == 400
    assert _canjear(publica, token).status_code == 302


def test_clave_igual_al_usuario_o_comun_no_consume(app_seguridad, reloj):
    app = app_seguridad
    objetivo = _crear(app, "probe.comun")
    token = _token_de(_emitir(_admin(app), objetivo))
    respuesta = _canjear(app.test_client(), token, clave="contraseña123", repetida="contraseña123")
    assert respuesta.status_code == 400
    assert _enlaces(app, objetivo)[-1]["used"] is None


def test_canje_con_csrf_exige_el_token(csrf_activo, reloj):
    app = csrf_activo
    objetivo = _crear(app, "probe.csrf_canje")
    token = "k" * 43
    _fila_directa(app, objetivo, token)
    sin_token = app.test_client().post(RUTA_CANJE, data={"token": token, "new_password": NUEVA, "confirm": NUEVA})
    assert sin_token.status_code == 400
    assert _enlaces(app, objetivo)[-1]["used"] is None


def test_limite_de_5_canjes_cada_10_minutos_por_ip(app_limitado, reloj):
    app = app_limitado
    publica = app.test_client()
    estados = [_canjear(publica, "x" * 43).status_code for _ in range(6)]
    assert estados[:5] == [400] * 5
    assert estados[5] == 429


def test_fallos_de_canje_quedan_agrupados_sin_token(app_seguridad, reloj):
    app = app_seguridad
    objetivo = _crear(app, "probe.agrupa")
    token = _token_de(_emitir(_admin(app), objetivo))
    publica = app.test_client()
    for _ in range(3):
        _canjear(publica, "y" * 43)
    _canjear(publica, token, clave="corta")
    fallos = _filas_auditoria(app, "recovery_failed")
    assert len(fallos) == 1 and fallos[0]["rep"] == 3
    assert fallos[0]["detalle"] == {"motivo": "inexistente"}
    assert token not in json.dumps(fallos)


def test_sesion_abierta_antes_de_la_emision_se_cierra(app_seguridad, reloj):
    app = app_seguridad
    objetivo = _crear(app, "probe.abierta", "sales")
    sesion = _cliente_con_sesion(app, objetivo)
    assert sesion.get("/").status_code == 302
    _emitir(_admin(app), objetivo)
    assert sesion.get("/").status_code == 200


def test_canje_no_interfiere_con_el_login_de_clave_temporal(app_seguridad, reloj):
    app = app_seguridad
    objetivo = _crear(app, "probe.guardia", "sales", cambiar=True)
    token = _token_de(_emitir(_admin(app), objetivo))
    assert app.test_client().get(RUTA_CANJE).status_code == 200
    assert _canjear(app.test_client(), token).status_code == 302


def _fila_directa(app, uid, token, minutos=30, usado=False):
    """Enlace insertado directamente (sin pasar por la emisión, que tiene límite por administrador)."""
    ahora = security.ahora()
    with app.app_context():
        db.session.add(UserRecoveryToken(
            user_id=uid,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            created_at=ahora,
            expires_at=ahora + timedelta(minutes=minutos),
            used_at=ahora if usado else None,
        ))
        db.session.commit()


def test_tiempos_parejos_medianas_en_la_instancia(app_seguridad, reloj):
    """Medición de tiempos (100 intentos por motivo). Solo corre con APP360_PRUEBAS_TIEMPOS=1."""
    if os.environ.get("APP360_PRUEBAS_TIEMPOS") != "1":
        pytest.skip("Medición de tiempos: solo en la instancia (APP360_PRUEBAS_TIEMPOS=1).")
    app = app_seguridad
    publica = app.test_client()
    uid = _crear(app, "probe.tiempos")
    muestras = {"inexistente": [], "vencido": [], "usado": [], "valido_clave_invalida": []}
    for i in range(100):
        t0 = time.perf_counter()
        _canjear(publica, f"{i:043d}")
        muestras["inexistente"].append(time.perf_counter() - t0)
        token_v = f"v{i:042d}"
        _fila_directa(app, uid, token_v, minutos=-1)
        t0 = time.perf_counter()
        _canjear(publica, token_v)
        muestras["vencido"].append(time.perf_counter() - t0)
        token_u = f"u{i:042d}"
        _fila_directa(app, uid, token_u, usado=True)
        t0 = time.perf_counter()
        _canjear(publica, token_u)
        muestras["usado"].append(time.perf_counter() - t0)
        token_c = f"c{i:042d}"
        _fila_directa(app, uid, token_c)
        t0 = time.perf_counter()
        _canjear(publica, token_c, clave="corta")
        muestras["valido_clave_invalida"].append(time.perf_counter() - t0)
    medianas = {k: statistics.median(v) * 1000 for k, v in muestras.items()}
    print("MEDIANAS_MS", {k: round(v, 2) for k, v in medianas.items()})
    base = medianas["inexistente"]
    for motivo, valor in medianas.items():
        assert abs(valor - base) <= max(5.0, base * 0.25), (motivo, valor, base)


# -----------------------------------------------------------------------------
# Concurrencia real (solo PostgreSQL, base con «carrera» en el nombre)
# -----------------------------------------------------------------------------
def _app_pg(monkeypatch):
    url = os.environ.get(PG_URL_ENV, "")
    if not url or "carrera" not in url:
        pytest.skip("Concurrencia real: requiere APP360_PRUEBAS_PG_URL con una base «carrera».")
    from app import create_app

    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", url)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)
    app = create_app()
    app.config["TESTING"] = True
    return app


def test_carrera_10_canjes_simultaneos_solo_uno_gana(monkeypatch):
    app = _app_pg(monkeypatch)
    with app.app_context():
        db.drop_all()
        db.create_all()
        cuenta = User(username="probe.carrera", role="sales", active=True)
        db.session.add(cuenta)
        cuenta.set_password(CLAVE)
        db.session.commit()
        uid = cuenta.id
        token = "c" * 43
        db.session.add(UserRecoveryToken(
            user_id=uid, token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ))
        db.session.commit()
    barrera = threading.Barrier(10)

    def intento(_):
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                resultado, _dato = rc.canjear(token, NUEVA, NUEVA, ip="10.0.0.9")
                return resultado
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=10) as pool:
        resultados = list(pool.map(intento, range(10)))
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    assert resultados.count("ok") == 1
    assert len(resultados) == 10


def test_canje_y_revocacion_simultaneos_solo_uno_gana(monkeypatch):
    app = _app_pg(monkeypatch)
    with app.app_context():
        db.drop_all()
        db.create_all()
        cuenta = User(username="probe.carrera2", role="sales", active=True)
        db.session.add(cuenta)
        cuenta.set_password(CLAVE)
        db.session.commit()
        uid = cuenta.id
        token = "d" * 43
        fila = UserRecoveryToken(
            user_id=uid, token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.session.add(fila)
        db.session.commit()
        rid = fila.id
    barrera = threading.Barrier(2)
    resultado = {}

    def canje():
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                resultado["canje"], _ = rc.canjear(token, NUEVA, NUEVA, ip="10.0.0.8")
            finally:
                db.session.remove()

    def revocar():
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                admin = db.session.get(User, uid)
                rc.revocar(admin, uid, rid)
                resultado["revocar"] = "ok"
            except Exception as error:
                db.session.rollback()
                resultado["revocar"] = getattr(error, "codigo", "error")
            finally:
                db.session.remove()

    hilos = [threading.Thread(target=canje), threading.Thread(target=revocar)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=120)
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    assert (resultado.get("canje") == "ok") != (resultado.get("revocar") == "ok")


# -----------------------------------------------------------------------------
# B5. Purga
# -----------------------------------------------------------------------------
def _cargar_purga():
    especificacion = importlib.util.spec_from_file_location("purga_c5", PURGA)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def test_purga_de_enlaces_simula_y_exige_confirmacion(app_seguridad):
    app = app_seguridad
    purga = _cargar_purga()
    uid = _crear(app, "probe.purga")
    with app.app_context():
        viejo_usado = UserRecoveryToken(user_id=uid, token_hash="1" * 64, created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                                        expires_at=datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc), used_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
        viejo_vencido = UserRecoveryToken(user_id=uid, token_hash="2" * 64, created_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
                                          expires_at=datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc))
        vigente = UserRecoveryToken(user_id=uid, token_hash="3" * 64, created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                                    expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
        reciente = UserRecoveryToken(user_id=uid, token_hash="4" * 64, created_at=datetime(2026, 11, 19, tzinfo=timezone.utc),
                                     expires_at=datetime(2026, 11, 19, 0, 30, tzinfo=timezone.utc), used_at=datetime(2026, 11, 19, tzinfo=timezone.utc))
        db.session.add_all([viejo_usado, viejo_vencido, vigente, reciente])
        db.session.commit()
        assert purga.purgar_enlaces(date(2026, 11, 1)) == (2, 0)
        with pytest.raises(ValueError):
            purga.purgar_enlaces(date(2026, 11, 1), True, "2026-10-01")
        assert purga.purgar_enlaces(date(2026, 11, 1), True, "2026-11-01") == (2, 2)
        restantes = {f.token_hash for f in UserRecoveryToken.query.all()}
        assert restantes == {"3" * 64, "4" * 64}


# -----------------------------------------------------------------------------
# B6. Migración (SQLite con las 8 réplicas) y compatibilidad
# -----------------------------------------------------------------------------
def _modulo_migracion():
    especificacion = importlib.util.spec_from_file_location("migracion_usuarios_c5", MIGRACION)
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


def _tablas_c4(motor):
    with motor.begin() as conexion:
        conexion.execute(sa.text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, "
            "password_hash VARCHAR(255), role VARCHAR(40) NOT NULL, active BOOLEAN DEFAULT 1, "
            "must_change_password BOOLEAN NOT NULL DEFAULT 0, password_changed_at DATETIME, "
            "last_login_at DATETIME, token_version INTEGER NOT NULL DEFAULT 0, "
            "temp_password_expires_at DATETIME, deactivated_at DATETIME, "
            "failed_login_count INTEGER NOT NULL DEFAULT 0, failed_login_window_start DATETIME, "
            "locked_until DATETIME)"
        ))
        conexion.execute(sa.text(
            "CREATE TABLE user_audit_log (id INTEGER PRIMARY KEY, created_at DATETIME NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP, actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
            "actor_username VARCHAR(80), accion VARCHAR(40) NOT NULL, target_user_id INTEGER "
            "REFERENCES users(id) ON DELETE SET NULL, target_username VARCHAR(80), detalle JSON, "
            "ip VARCHAR(45), clave_agrupacion VARCHAR(200), repeticiones INTEGER NOT NULL DEFAULT 1)"
        ))
        for nombre, rol, activo in REPLICAS:
            hash_clave = None if nombre == "test_user" else generate_password_hash(f"PROBE-{nombre}")
            conexion.execute(
                sa.text("INSERT INTO users (username, role, active, password_hash) VALUES (:u, :r, :a, :h)"),
                {"u": nombre, "r": rol, "a": activo, "h": hash_clave},
            )


def test_migracion_upgrade_downgrade_upgrade_con_las_8_replicas(tmp_path):
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'c5.db'}")
    _tablas_c4(motor)
    antes = _foto(motor)
    assert len(antes) == 8
    modulo = _modulo_migracion()
    assert modulo.down_revision == "20261120_usuarios_c4_auditoria_bloqueo"

    _ejecutar(motor, modulo.upgrade)
    columnas = {c["name"] for c in sa.inspect(motor).get_columns("users")}
    assert "email" in columnas
    assert "user_recovery_tokens" in sa.inspect(motor).get_table_names()
    assert _foto(motor) == antes

    _ejecutar(motor, modulo.downgrade)
    assert "email" not in {c["name"] for c in sa.inspect(motor).get_columns("users")}
    assert "user_recovery_tokens" not in sa.inspect(motor).get_table_names()
    assert _foto(motor) == antes

    _ejecutar(motor, modulo.upgrade)
    assert _foto(motor) == antes


def test_migracion_con_correos_repetidos_aborta_con_mensaje_claro(tmp_path):
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'c5_dup.db'}")
    _tablas_c4(motor)
    with motor.begin() as conexion:
        conexion.execute(sa.text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
        conexion.execute(sa.text("UPDATE users SET email = 'dup@x.com' WHERE id = 1"))
        conexion.execute(sa.text("UPDATE users SET email = 'DUP@x.com' WHERE id = 2"))
    modulo = _modulo_migracion()
    with pytest.raises(RuntimeError, match="correo\\(s\\) repetido\\(s\\)"):
        _ejecutar(motor, modulo.upgrade)
    assert "user_recovery_tokens" not in sa.inspect(motor).get_table_names()
    with motor.connect() as conexion:
        indices = conexion.execute(sa.text("SELECT name FROM sqlite_master WHERE name = 'ix_users_email_lower'")).all()
    assert indices == []


def test_huella_y_sesiones_previas_siguen_validas_tras_el_cambio(app_seguridad):
    app = app_seguridad
    cuentas = [_crear(app, nombre, rol, activo=activo) for nombre, rol, activo in REPLICAS if activo]
    with app.app_context():
        for uid in cuentas:
            cuenta = db.session.get(User, uid)
            assert cuenta.token_version == 0
            esperada = hmac.new(
                app.secret_key.encode("utf-8"), cuenta.password_hash.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            assert huella_sesion(cuenta) == esperada
    for uid in cuentas[:2]:
        cliente = _cliente_con_sesion(app, uid)
        assert cliente.get("/").status_code == 302
