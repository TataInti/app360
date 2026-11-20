"""Administración de usuarios (C3): cambio de rol, restablecimiento de clave y clave temporal vencida.

Cubre del pliego de DISENO-APP360 §7 lo que corresponde a C3 (P-12 a P-16, P-18 y P-33 en SQLite) y
las pruebas propias del corte: rol, reseteo, vencimiento, guardia de /api/admin/* antes del CSRF,
scripts de alta y compatibilidad de los usuarios actuales. Datos sintéticos rotulados PROBE; ninguna
prueba apunta a una base real. La carrera real sobre PostgreSQL corre solo si APP360_PRUEBAS_PG_URL
apunta a una base de prueba cuyo nombre contenga «carrera»; en CI queda omitida y se declara en el PR.
"""

import hashlib
import hmac
import importlib
import logging
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import security
from config import Config
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from security import SESION_HUELLA_CLAVE, generate_access_token, huella_sesion
from services import usuarios_admin as ua
from sesion_de_prueba import marcar_sesion

CLAVE = "PROBE-clave-actual-no-real"
NUEVA = "PROBE-clave-nueva-2026"
MENSAJE_LOGIN = "Usuario o contraseña incorrectos."
ALFABETO_CLAVE = re.compile(r"[abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789]{16}")
INSTANTE = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
PG_URL_ENV = "APP360_PRUEBAS_PG_URL"


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
def _crear(app, username, role, *, clave=CLAVE, must_change=False, active=True, vence=None, version=0):
    with app.app_context():
        usuario = User.query.filter_by(username=username).one_or_none()
        if usuario is None:
            usuario = User(username=username, role=role, active=active)
            db.session.add(usuario)
        usuario.role = role
        usuario.active = active
        usuario.must_change_password = must_change
        usuario.temp_password_expires_at = vence
        usuario.deactivated_at = None if active else INSTANTE
        usuario.token_version = version
        usuario.set_password(clave)
        usuario.password_changed_at = None
        db.session.commit()
        return usuario.id


def _cliente(app, usuario_id):
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _aware(valor):
    return None if valor is None else (valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor)


def _estado(app, usuario_id):
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        return {
            "rol": usuario.role,
            "active": usuario.active is True,
            "tv": usuario.token_version,
            "must": bool(usuario.must_change_password),
            "vence": _aware(usuario.temp_password_expires_at),
            "hash": usuario.password_hash,
            "desactivado": usuario.deactivated_at,
        }


def _total(app):
    with app.app_context():
        return User.query.count()


def _eventos(app, accion):
    with app.app_context():
        return [
            {"actor": fila.actor_username, "objetivo": fila.target_username, "detalle": fila.detalle}
            for fila in UserAuditLog.query.filter_by(accion=accion).order_by(UserAuditLog.id).all()
        ]


def _ruta(respuesta):
    return urlsplit(respuesta.location).path


def _login(cliente, usuario, clave):
    return cliente.post("/", data={"username": usuario, "password": clave})


def _rol(cliente, usuario_id, rol, headers=None):
    return cliente.post(f"/api/admin/usuarios/{usuario_id}/rol", json={"role": rol}, headers=headers or {})


def _reset(cliente, usuario_id, headers=None):
    return cliente.post(f"/api/admin/usuarios/{usuario_id}/restablecer-clave", headers=headers or {})


def _token_pantalla(cliente):
    pagina = cliente.get("/admin/usuarios").get_data(as_text=True)
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', pagina).group(1)


def _tokens(app, usuario_id):
    with app.app_context():
        usuario = db.session.get(User, usuario_id)
        version = usuario.token_version or 0
        return generate_access_token(usuario.id, usuario.username, usuario.role, version)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _reenviar_cookie(app, valor, ruta):
    """Petición con la cookie de sesión copiada (sin jar: no reemplaza ni actualiza la cookie)."""
    return app.test_client(use_cookies=False).get(ruta, headers={"Cookie": f"session={valor}"})


# -----------------------------------------------------------------------------
# Cambio de rol (R1)
# -----------------------------------------------------------------------------
def test_cambio_de_rol_valido_cambia_audita_y_no_suma_version(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.ventas", "sales")

    respuesta = _rol(admin, objetivo, "hr")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["cambiado"] is True and cuerpo["rol_anterior"] == "sales"
    assert cuerpo["usuario"]["rol"] == "hr" and cuerpo["usuario"]["rol_nombre"] == "RRHH"
    estado = _estado(app, objetivo)
    assert estado["rol"] == "hr" and estado["tv"] == 0
    eventos = _eventos(app, "user_role_changed")
    assert len(eventos) == 1
    assert eventos[0]["actor"] == "probe-admin" and eventos[0]["objetivo"] == "probe.ventas"
    assert eventos[0]["detalle"] == {"de": "sales", "a": "hr"}


@pytest.mark.parametrize("rol", ["root", "manager", "", "   ", None])
def test_rol_fuera_de_la_lista_o_vacio_responde_400_y_no_cambia(app_seguridad, rol):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.objetivo", "sales")
    antes = _estado(app, objetivo)

    respuesta = _rol(admin, objetivo, rol)

    assert respuesta.status_code == 400
    assert "role" in respuesta.get_json()["campos"]
    assert _estado(app, objetivo) == antes
    assert _eventos(app, "user_role_changed") == []


def test_mismo_rol_responde_200_sin_cambios_ni_auditoria(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.igual", "sales")
    antes = _estado(app, objetivo)

    respuesta = _rol(admin, objetivo, "sales")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["cambiado"] is False
    assert _estado(app, objetivo) == antes
    assert _eventos(app, "user_role_changed") == []


def test_manager_conserva_su_rol_pero_no_lo_asigna_a_otros(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    antiguo = _crear(app, "probe.antiguo", "manager")
    otro = _crear(app, "probe.otro", "sales")

    conservado = _rol(admin, antiguo, "manager")
    assignacion = _rol(admin, otro, "manager")
    cambio = _rol(admin, antiguo, "sales")

    assert conservado.status_code == 200 and conservado.get_json()["cambiado"] is False
    assert assignacion.status_code == 400 and assignacion.get_json()["codigo"] == "ROL_INVALIDO"
    assert "ya no se asigna" in assignacion.get_json()["campos"]["role"]
    assert _estado(app, otro)["rol"] == "sales"
    assert cambio.status_code == 200 and _estado(app, antiguo)["rol"] == "sales"


def test_id_inexistente_responde_404_json_en_rol_y_reseteo(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))

    rol = _rol(admin, 999999, "sales")
    reseteo = _reset(admin, 999999)

    for respuesta in (rol, reseteo):
        assert respuesta.status_code == 404 and respuesta.is_json
        assert respuesta.get_json()["codigo"] == "USUARIO_NO_ENCONTRADO"


@pytest.mark.parametrize("rol_actor", ["sales", "hr", "caja", "director", "direccion"])
def test_roles_sin_administracion_reciben_403_y_no_cambian_nada(app_seguridad, rol_actor):
    app = app_seguridad
    actor = _cliente(app, _crear(app, f"probe.sin-{rol_actor}", rol_actor))
    objetivo = _crear(app, "probe.objetivo", "sales")
    antes = _estado(app, objetivo)

    rol = _rol(actor, objetivo, "hr")
    reseteo = _reset(actor, objetivo)

    for respuesta in (rol, reseteo):
        assert respuesta.status_code == 403
        assert respuesta.get_json()["codigo"] == "SIN_PERMISO"
    assert _estado(app, objetivo) == antes


def test_anonimo_y_jwt_reciben_401_json_en_rol_y_reseteo(app_seguridad):
    app = app_seguridad
    admin = _crear(app, "probe-admin", "admin")
    objetivo = _crear(app, "probe.objetivo", "sales")
    anonimo = app.test_client()

    rol = _rol(anonimo, objetivo, "hr")
    reseteo = _reset(anonimo, objetivo)
    con_jwt = app.test_client(use_cookies=False).post(
        f"/api/admin/usuarios/{objetivo}/rol", json={"role": "hr"}, headers=_bearer(_tokens(app, admin))
    )

    for respuesta in (rol, reseteo, con_jwt):
        assert respuesta.status_code == 401 and respuesta.is_json
        assert respuesta.get_json() == {"error": "Sesión requerida"}
    assert _estado(app, objetivo)["rol"] == "sales"


def test_autocambio_de_rol_y_autorreseteo_responden_403(app_seguridad):
    app = app_seguridad
    yo = _crear(app, "probe-admin", "admin")
    _crear(app, "probe-admin-b", "gerente")
    admin = _cliente(app, yo)
    antes = _estado(app, yo)

    rol = _rol(admin, yo, "sales")
    rol_igual = _rol(admin, yo, "admin")
    reseteo = _reset(admin, yo)

    assert rol.status_code == 403 and rol.get_json()["codigo"] == "AUTOCAMBIO_ROL"
    assert rol_igual.status_code == 403
    assert reseteo.status_code == 403 and reseteo.get_json()["codigo"] == "AUTORESET"
    assert "Cambiar mi clave" in reseteo.get_json()["error"]
    assert _estado(app, yo) == antes


@pytest.mark.parametrize("rol_unico", ["admin", "manager", "gerente"])
def test_servicio_rechaza_bajar_al_ultimo_administrador_activo(app_seguridad, rol_unico):
    """El servicio no confía en el actor: aunque no sea administrador, el último activo no baja."""
    app = app_seguridad
    unico = _crear(app, "probe.unico", rol_unico)
    ventas = _crear(app, "probe.ventas", "sales")
    with app.app_context():
        actor = db.session.get(User, ventas)
        with pytest.raises(ua.ErrorUsuarios) as info:
            ua.cambiar_rol(actor, unico, "sales")
        assert info.value.codigo == "ULTIMO_ADMINISTRADOR" and info.value.status == 409
        db.session.rollback()
    assert _estado(app, unico)["rol"] == rol_unico
    assert _eventos(app, "user_role_changed") == []


def test_ultimo_administrador_puede_pasar_a_otro_rol_de_administracion(app_seguridad):
    """admin → gerente no deja al sistema sin administradores: ambos cuentan como administración."""
    app = app_seguridad
    unico = _crear(app, "probe.admin", "admin")
    ventas = _crear(app, "probe.ventas", "sales")
    with app.app_context():
        usuario, anterior, cambiado = ua.cambiar_rol(db.session.get(User, ventas), unico, "gerente")
        assert usuario.role == "gerente" and anterior == "admin" and cambiado is True


def test_usuario_inactivo_puede_cambiar_de_rol_sin_reactivarse(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    baja = _crear(app, "probe.baja", "admin", active=False)

    respuesta = _rol(admin, baja, "sales")

    assert respuesta.status_code == 200 and respuesta.get_json()["cambiado"] is True
    estado = _estado(app, baja)
    assert estado["rol"] == "sales" and estado["active"] is False
    assert len(_eventos(app, "user_role_changed")) == 1


def test_segundo_cambio_ve_el_estado_que_dejo_el_primero(app_seguridad):
    app = app_seguridad
    x = _crear(app, "probe.admin-x", "admin")
    y = _crear(app, "probe.admin-y", "gerente")
    actor = _crear(app, "probe.ventas", "sales")
    with app.app_context():
        ua.cambiar_rol(db.session.get(User, actor), x, "sales")
        with pytest.raises(ua.ErrorUsuarios) as info:
            ua.cambiar_rol(db.session.get(User, actor), y, "sales")
        assert info.value.codigo == "ULTIMO_ADMINISTRADOR"
        db.session.rollback()
    assert _estado(app, y)["rol"] == "gerente" and _estado(app, x)["rol"] == "sales"


@pytest.mark.skipif(
    not os.environ.get(PG_URL_ENV) or "carrera" not in os.environ.get(PG_URL_ENV, ""),
    reason=f"Carrera real: requiere {PG_URL_ENV} con una base PostgreSQL de prueba cuyo nombre contenga «carrera»",
)
def test_carrera_en_postgresql_dos_administradores_nunca_dejan_cero_activos(monkeypatch):
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
        a = User(username="probe.carrera-a", role="admin", active=True)
        a.set_password(CLAVE)
        b = User(username="probe.carrera-b", role="gerente", active=True)
        b.set_password(CLAVE)
        db.session.add_all([a, b])
        db.session.commit()
        ids = (a.id, b.id)

    barrera = threading.Barrier(2)
    resultados = {}

    def cambiar(nombre, actor_id, objetivo_id):
        with app.app_context():
            try:
                actor = db.session.get(User, actor_id)
                barrera.wait(timeout=30)
                ua.cambiar_rol(actor, objetivo_id, "sales")
                resultados[nombre] = "ok"
            except ua.ErrorUsuarios as error:
                db.session.rollback()
                resultados[nombre] = error.codigo
            finally:
                db.session.remove()

    hilos = [
        threading.Thread(target=cambiar, args=("a", ids[0], ids[1])),
        threading.Thread(target=cambiar, args=("b", ids[1], ids[0])),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=120)
    with app.app_context():
        activos = User.query.filter(User.role.in_(ua.ROLES_ADMINISTRACION), User.active.is_(True)).count()
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    assert sorted(resultados.values()) == ["ULTIMO_ADMINISTRADOR", "ok"], resultados
    assert activos >= 1


def test_cambio_de_rol_rige_en_la_siguiente_peticion_web(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.ventas", "sales")
    ventas = _cliente(app, objetivo)
    assert ventas.get("/api/rrhh/empleados").status_code == 403

    assert _rol(admin, objetivo, "hr").status_code == 200

    assert ventas.get("/api/rrhh/empleados").status_code == 200
    with ventas.session_transaction() as sesion:
        assert sesion["role"] == "hr"


def test_cambio_de_rol_rige_en_el_siguiente_jwt_sin_nuevo_inicio(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.ventas", "sales")
    cliente = app.test_client(use_cookies=False)
    cabecera = _bearer(_tokens(app, objetivo))
    assert cliente.get("/api/rrhh/empleados", headers=cabecera).status_code == 403

    assert _rol(admin, objetivo, "hr").status_code == 200

    assert cliente.get("/api/rrhh/empleados", headers=cabecera).status_code == 200
    assert _estado(app, objetivo)["tv"] == 0


# -----------------------------------------------------------------------------
# Restablecer clave (R2)
# -----------------------------------------------------------------------------
def test_restablecer_muestra_la_clave_una_vez_y_fija_72_horas(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.reset", "sales")
    antes = _estado(app, objetivo)

    respuesta = _reset(admin, objetivo)

    assert respuesta.status_code == 200
    assert respuesta.headers["Cache-Control"] == "no-store"
    cuerpo = respuesta.get_json()
    clave = cuerpo["clave_temporal"]
    assert ALFABETO_CLAVE.fullmatch(clave), "16 caracteres de un alfabeto sin ambiguos"
    assert datetime.fromisoformat(cuerpo["clave_temporal_vence"]) == INSTANTE + timedelta(hours=72)
    assert cuerpo["usuario"]["estado"] == "cambiar_clave"
    assert cuerpo["usuario"]["clave_temporal_vence_texto"] == "22/11 09:00"
    estado = _estado(app, objetivo)
    assert estado["must"] is True and estado["vence"] == INSTANTE + timedelta(hours=72)
    assert estado["tv"] == antes["tv"] + 1
    assert estado["hash"] != antes["hash"]
    with app.app_context():
        usuario = db.session.get(User, objetivo)
        assert usuario.check_password(clave) and not usuario.check_password(CLAVE)
        assert _aware(usuario.password_changed_at) == INSTANTE
    eventos = _eventos(app, "user_password_reset")
    assert len(eventos) == 1
    assert eventos[0]["detalle"] == {"vence": (INSTANTE + timedelta(hours=72)).isoformat()}
    assert clave not in str(eventos[0]["detalle"])


def test_la_clave_restablecida_no_aparece_en_lista_auditoria_ni_logs(app_seguridad, caplog):
    caplog.set_level(logging.DEBUG)
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.logs", "sales")
    clave = _reset(admin, objetivo).get_json()["clave_temporal"]

    lista = admin.get("/api/admin/usuarios").get_data(as_text=True)
    auditoria = admin.get("/api/admin/usuarios/auditoria").get_data(as_text=True)
    pantalla = admin.get("/admin/usuarios").get_data(as_text=True)
    with app.app_context():
        detalles = [str(fila.detalle) for fila in UserAuditLog.query.all()]
    conteos = {
        "lista": lista.count(clave),
        "auditoria": auditoria.count(clave),
        "pantalla": pantalla.count(clave),
        "detalles_auditoria": sum(detalle.count(clave) for detalle in detalles),
        "logs": caplog.text.count(clave),
    }
    assert conteos == {"lista": 0, "auditoria": 0, "pantalla": 0, "detalles_auditoria": 0, "logs": 0}, conteos


def test_la_clave_vieja_y_las_sesiones_previas_dejan_de_valer(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.caen", "sales")
    sesion_previa = _cliente(app, objetivo)
    # La cookie queda en el host de SERVER_NAME (fuera de desarrollo) o en localhost (desarrollo).
    # Se la busca en ese host para que la prueba no dependa de FLASK_ENV.
    cookie_previa = sesion_previa.get_cookie("session", domain=app.config.get("SERVER_NAME") or "localhost")
    assert cookie_previa is not None, "la sesión de prueba no dejó cookie"
    cookie = cookie_previa.value
    cabecera = _bearer(_tokens(app, objetivo))
    assert sesion_previa.get("/api/admin/usuarios").status_code == 403
    assert app.test_client(use_cookies=False).get("/api/rrhh/empleados", headers=cabecera).status_code == 403

    assert _reset(admin, objetivo).status_code == 200

    assert _reenviar_cookie(app, cookie, "/api/admin/usuarios").status_code == 401
    assert app.test_client(use_cookies=False).get("/api/rrhh/empleados", headers=cabecera).status_code == 401
    cliente_nuevo = app.test_client()
    respuesta = _login(cliente_nuevo, "probe.caen", CLAVE)
    assert respuesta.status_code == 200 and MENSAJE_LOGIN in respuesta.get_data(as_text=True)


def test_la_clave_nueva_entra_una_vez_y_fuerza_cambiar_clave(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.nueva", "sales")
    clave = _reset(admin, objetivo).get_json()["clave_temporal"]
    cliente = app.test_client()

    entrada = _login(cliente, "probe.nueva", clave)
    assert entrada.status_code == 302 and _ruta(entrada) == "/cambiar-clave"
    assert _ruta(cliente.get("/leads")) == "/cambiar-clave"
    cambio = cliente.post(
        "/cambiar-clave", data={"clave_actual": clave, "clave_nueva": NUEVA, "repetir_clave": NUEVA}
    )
    assert cambio.status_code == 302
    estado = _estado(app, objetivo)
    assert estado["must"] is False and estado["vence"] is None
    assert _login(app.test_client(), "probe.nueva", clave).status_code == 200
    assert _login(app.test_client(), "probe.nueva", NUEVA).status_code == 302


def test_restablecer_a_usuario_inactivo_responde_409_y_no_cambia(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    baja = _crear(app, "probe.baja", "sales", active=False)
    antes = _estado(app, baja)

    respuesta = _reset(admin, baja)

    assert respuesta.status_code == 409 and respuesta.get_json()["codigo"] == "USUARIO_INACTIVO"
    assert "Reactivalo primero" in respuesta.get_json()["error"]
    assert _estado(app, baja) == antes


def test_restablecer_la_propia_clave_responde_403_y_guia_a_cambiar_mi_clave(app_seguridad):
    app = app_seguridad
    yo = _crear(app, "probe-admin", "admin")
    admin = _cliente(app, yo)
    antes = _estado(app, yo)

    respuesta = _reset(admin, yo)

    assert respuesta.status_code == 403 and respuesta.get_json()["codigo"] == "AUTORESET"
    assert "Cambiar mi clave" in respuesta.get_json()["error"]
    assert _estado(app, yo) == antes


def test_si_falla_la_auditoria_el_restablecimiento_no_se_aplica(app_seguridad, monkeypatch):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.atomico", "sales")
    antes = _estado(app, objetivo)

    def falla(*args, **kwargs):
        raise RuntimeError("fallo simulado de la auditoría")

    monkeypatch.setattr(ua, "registrar_auditoria", falla)
    respuesta = _reset(admin, objetivo)

    assert respuesta.status_code == 500 and respuesta.get_json()["codigo"] == "ERROR_INTERNO"
    assert "clave_temporal" not in respuesta.get_json()
    assert _estado(app, objetivo) == antes


def test_clave_temporal_de_restablecimiento_vence_a_las_72_horas(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.vence", "sales")
    clave = _reset(admin, objetivo).get_json()["clave_temporal"]

    reloj["ahora"] = INSTANTE + timedelta(hours=71, minutes=59)
    assert _login(app.test_client(), "probe.vence", clave).status_code == 302

    reloj["ahora"] = INSTANTE + timedelta(hours=72)
    respuesta = _login(app.test_client(), "probe.vence", clave)
    assert respuesta.status_code == 200 and MENSAJE_LOGIN in respuesta.get_data(as_text=True)


# -----------------------------------------------------------------------------
# Clave temporal vencida (R3)
# -----------------------------------------------------------------------------
def test_clave_vencida_se_regenera_con_restablecer_y_la_nueva_vale(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.vencida", "sales", must_change=True, vence=INSTANTE + timedelta(hours=72))
    reloj["ahora"] = INSTANTE + timedelta(hours=73)

    assert MENSAJE_LOGIN in _login(app.test_client(), "probe.vencida", CLAVE).get_data(as_text=True)
    assert _reset(admin, objetivo).status_code == 200
    clave = _reset(admin, objetivo).get_json()["clave_temporal"]

    entrada = _login(app.test_client(), "probe.vencida", clave)
    assert entrada.status_code == 302 and _ruta(entrada) == "/cambiar-clave"
    assert _estado(app, objetivo)["vence"] == INSTANTE + timedelta(hours=73 + 72)


def test_lista_muestra_clave_vencida_y_el_filtro_la_encuentra(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    _crear(app, "probe.vencida", "sales", must_change=True, vence=INSTANTE + timedelta(hours=72))
    _crear(app, "probe.vigente", "sales", must_change=True, vence=INSTANTE + timedelta(hours=100))
    reloj["ahora"] = INSTANTE + timedelta(hours=73)

    def filas(estado):
        cuerpo = admin.get(f"/api/admin/usuarios?estado={estado}").get_json()
        return {fila["username"]: fila for fila in cuerpo["usuarios"]}

    todas = filas("todos")
    assert todas["probe.vencida"]["estado"] == "clave_vencida"
    assert todas["probe.vencida"]["estado_nombre"] == "Clave temporal vencida"
    assert todas["probe.vigente"]["estado"] == "cambiar_clave"
    assert todas["probe.vigente"]["clave_temporal_vence_texto"] == "23/11 13:00"
    assert list(filas("clave_vencida")) == ["probe.vencida"]
    assert list(filas("cambiar_clave")) == ["probe.vigente"]


def test_clave_temporal_que_ya_se_cambio_deja_de_mostrar_vencimiento(app_seguridad, reloj):
    app = app_seguridad
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.cambio", "sales", must_change=True, vence=INSTANTE + timedelta(hours=72))
    cliente = app.test_client()
    assert _login(cliente, "probe.cambio", CLAVE).status_code == 302

    cambio = cliente.post("/cambiar-clave", data={"clave_actual": CLAVE, "clave_nueva": NUEVA, "repetir_clave": NUEVA})

    assert cambio.status_code == 302
    fila = admin.get("/api/admin/usuarios?q=probe.cambio").get_json()["usuarios"][0]
    assert fila["estado"] == "activo" and fila["clave_temporal_vence"] is None
    assert fila["clave_temporal_vence_texto"] is None


# -----------------------------------------------------------------------------
# Guardia de /api/admin/* antes del CSRF (R4 b) y CSRF de los POST nuevos
# -----------------------------------------------------------------------------
def test_api_admin_sin_sesion_responde_401_json_aunque_falte_el_token_csrf(csrf_activo):
    app = csrf_activo
    _crear(app, "probe-admin", "admin")
    anonimo = app.test_client()
    casos = [
        ("post", "/api/admin/usuarios", {"username": "probe.x", "role": "sales"}),
        ("post", "/api/admin/usuarios/1/rol", {"role": "hr"}),
        ("post", "/api/admin/usuarios/1/restablecer-clave", None),
        ("post", "/api/admin/usuarios/1/desactivar", None),
        ("put", "/api/admin/accesos/1", {}),
        ("post", "/api/admin/cualquiera/entidad", {}),
        ("get", "/api/admin/usuarios", None),
    ]
    for metodo, ruta, cuerpo in casos:
        llamada = getattr(anonimo, metodo)
        respuesta = llamada(ruta, json=cuerpo) if cuerpo is not None else llamada(ruta)
        assert respuesta.status_code == 401, (metodo, ruta)
        assert respuesta.is_json and respuesta.get_json() == {"error": "Sesión requerida"}, (metodo, ruta)


def test_sesion_valida_sin_token_csrf_sigue_recibiendo_400(csrf_activo):
    app = csrf_activo
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.csrf", "sales")

    assert _rol(admin, objetivo, "hr").status_code == 400
    assert _reset(admin, objetivo).status_code == 400
    assert _estado(app, objetivo)["rol"] == "sales"

    token = _token_pantalla(admin)
    assert _rol(admin, objetivo, "hr", headers={"X-CSRFToken": token}).status_code == 200


def test_csrf_de_los_post_nuevos_rechaza_token_falso_sin_cambios(csrf_activo):
    app = csrf_activo
    admin = _cliente(app, _crear(app, "probe-admin", "admin"))
    objetivo = _crear(app, "probe.falso", "sales")
    antes = _estado(app, objetivo)

    assert _rol(admin, objetivo, "hr", headers={"X-CSRFToken": "falso"}).status_code == 400
    assert _reset(admin, objetivo, headers={"X-CSRFToken": "falso"}).status_code == 400
    assert _estado(app, objetivo) == antes


def test_el_csrf_del_resto_de_la_aplicacion_sigue_exigiendose(csrf_activo):
    anonimo = csrf_activo.test_client()

    assert anonimo.post("/logout").status_code == 400


# -----------------------------------------------------------------------------
# Scripts de alta: vuelta a activa suma token_version y audita (R4 c)
# -----------------------------------------------------------------------------
@pytest.fixture
def montaje_scripts(app_seguridad, monkeypatch, tmp_path):
    """Scripts contra la app de prueba, en un directorio vacío y con claves fijas de prueba."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    setup_users = importlib.import_module("setup_users")
    setup_database = importlib.import_module("setup_database")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "PROBE-admin-inicial-no-real")
    for modulo in (setup_users, setup_database):
        monkeypatch.setattr(modulo, "create_app", lambda: app_seguridad)
    monkeypatch.setattr(setup_users, "generar_clave", lambda: "PROBE-clave-generada-no-real")
    return setup_users, setup_database


def test_setup_users_reactiva_cuenta_inactiva_con_version_y_auditoria(app_seguridad, montaje_scripts):
    setup_users, _ = montaje_scripts
    app = app_seguridad
    _crear(app, "tesoreria", "caja", active=False, version=2)

    setup_users.setup_users(reset_passwords=False, mostrar_claves=False)

    estado = _estado(app, _id(app, "tesoreria"))
    assert estado["active"] is True and estado["tv"] == 3 and estado["desactivado"] is None
    eventos = _eventos(app, "user_reactivated")
    assert len(eventos) == 1
    assert eventos[0]["actor"] is None and eventos[0]["objetivo"] == "tesoreria"
    assert eventos[0]["detalle"] == {"rol": "caja"}


def test_setup_users_no_suma_version_a_una_cuenta_ya_activa(app_seguridad, montaje_scripts):
    setup_users, _ = montaje_scripts
    app = app_seguridad
    _crear(app, "tesoreria", "caja", version=2)
    antes = _estado(app, _id(app, "tesoreria"))

    setup_users.setup_users(reset_passwords=False, mostrar_claves=False)

    assert _estado(app, _id(app, "tesoreria"))["tv"] == antes["tv"] == 2
    assert _eventos(app, "user_reactivated") == []


def test_setup_users_crea_las_cuentas_nuevas_con_version_cero_y_sin_auditoria(app_seguridad, montaje_scripts):
    setup_users, _ = montaje_scripts
    app = app_seguridad

    setup_users.setup_users(reset_passwords=False, mostrar_claves=False)

    with app.app_context():
        nuevas = User.query.filter(User.username.in_(["tesoreria", "direccion"])).all()
        assert len(nuevas) == 2 and all(u.token_version == 0 and u.active is True for u in nuevas)
    assert _eventos(app, "user_reactivated") == []


def test_setup_database_reactiva_admin_inactivo_con_version_y_auditoria(app_seguridad, montaje_scripts):
    _, setup_database = montaje_scripts
    app = app_seguridad
    _crear(app, "admin", "admin", active=False, version=1)

    resultado = setup_database.ensure_admin_user(reset_password=False)

    assert resultado == "existe, sin cambio de clave"
    estado = _estado(app, _id(app, "admin"))
    assert estado["active"] is True and estado["tv"] == 2
    assert len(_eventos(app, "user_reactivated")) == 1


def test_reactivacion_de_script_sin_tabla_de_auditoria_suma_version_y_no_falla(
    app_seguridad, montaje_scripts, monkeypatch
):
    setup_users, _ = montaje_scripts
    app = app_seguridad
    _crear(app, "tesoreria", "caja", active=False, version=4)
    monkeypatch.setattr(ua, "_tabla_auditoria_existe", lambda: False)

    setup_users.setup_users(reset_passwords=False, mostrar_claves=False)

    assert _estado(app, _id(app, "tesoreria"))["tv"] == 5
    assert _eventos(app, "user_reactivated") == []


def _id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().id


# -----------------------------------------------------------------------------
# Compatibilidad: los usuarios actuales y sus sesiones (R5)
# -----------------------------------------------------------------------------
USUARIOS_ACTUALES = [
    ("admin", "admin", True, False),
    ("gerente", "gerente", True, False),
    ("ventas", "sales", True, False),
    ("rrhh", "hr", True, False),
    ("tesoreria", "caja", True, False),
    ("direccion", "director", True, False),
    ("anibal.lopez", "sales", True, True),
    ("test_user", "sales", False, False),
]


def _montar_usuarios_actuales(app):
    ids = {}
    with app.app_context():
        for nombre, rol, activo, cambio in USUARIOS_ACTUALES:
            usuario = User(username=nombre, role=rol, active=activo)
            if nombre != "test_user":
                usuario.set_password(f"PROBE-{nombre}-no-real")
            usuario.must_change_password = cambio
            usuario.token_version = 0
            db.session.add(usuario)
        db.session.commit()
        for usuario in User.query.all():
            ids[usuario.username] = usuario.id
    return ids


def test_los_ocho_usuarios_actuales_siguen_entrando_con_sus_claves(app_seguridad):
    app = app_seguridad
    _montar_usuarios_actuales(app)
    for nombre, _rol_actual, activo, cambio in USUARIOS_ACTUALES:
        respuesta = _login(app.test_client(), nombre, f"PROBE-{nombre}-no-real")
        if nombre == "test_user":
            assert MENSAJE_LOGIN in respuesta.get_data(as_text=True), nombre
        elif cambio:
            assert respuesta.status_code == 302 and _ruta(respuesta) == "/cambiar-clave", nombre
        else:
            assert respuesta.status_code == 302 and _ruta(respuesta) not in ("/cambiar-clave", "/"), nombre


def test_huella_con_version_cero_es_la_de_antes_de_c3_y_las_sesiones_previas_siguen(app_seguridad):
    app = app_seguridad
    ids = _montar_usuarios_actuales(app)
    secreto = app.secret_key.encode("utf-8")
    with app.app_context():
        for usuario in User.query.all():
            if usuario.password_hash:
                anterior = hmac.new(secreto, usuario.password_hash.encode("utf-8"), hashlib.sha256).hexdigest()
                assert huella_sesion(usuario) == anterior, usuario.username
    # Sesión abierta antes de C3 (huella con token_version 0): sigue válida tras el cambio de código.
    cliente = app.test_client()
    with app.app_context():
        ventas = db.session.get(User, ids["ventas"])
        previa = hmac.new(secreto, ventas.password_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    with cliente.session_transaction() as sesion:
        sesion.update(
            {"user": "ventas", "user_id": ids["ventas"], "role": "sales", SESION_HUELLA_CLAVE: previa}
        )
    assert cliente.get("/api/rrhh/empleados").status_code == 403
    admin = _cliente(app, ids["admin"])
    assert admin.get("/api/admin/usuarios").status_code == 200
