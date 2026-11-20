"""Resiliencia del login de C4: el acierto no depende de los contadores; orden de bloqueos; esquema en health.

Datos sintéticos rotulados PROBE. Las pruebas SQLite corren en CI. Las de PostgreSQL (carrera con barrera)
corren solo si APP360_PRUEBAS_PG_URL apunta a una base de prueba cuyo nombre contenga «carrera»; en CI quedan
omitidas y se declaran en el PR.
"""

import os
import threading
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

import security
from config import Config
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from models.core.user_login_attempt import UserLoginAttempt
from services import acceso_login as al
from services import usuarios_admin as ua

CLAVE = "PROBE-clave-resiliencia-2026"
PG_URL_ENV = "APP360_PRUEBAS_PG_URL"
INSTANTE = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def reloj(monkeypatch):
    """Reloj controlado: security.ahora() devuelve el instante fijado (igual que en test_usuarios_c4)."""
    instante = {"ahora": INSTANTE}
    monkeypatch.setattr(security, "ahora", lambda: instante["ahora"])
    return instante


def _crear(app, usuario, rol="sales", *, clave=CLAVE, activo=True):
    with app.app_context():
        cuenta = User(username=usuario, role=rol, active=activo)
        db.session.add(cuenta)
        cuenta.set_password(clave)
        cuenta.must_change_password = False
        db.session.commit()
        return cuenta.id


@pytest.fixture
def eventos(monkeypatch):
    """Captura los eventos de seguridad sin cambiar su comportamiento."""
    registro = []
    original = security.log_security_event

    def capturar(event_type, message, *args, **kwargs):
        registro.append({"tipo": event_type, "extra": kwargs.get("extra") or {}})
        return original(event_type, message, *args, **kwargs)

    monkeypatch.setattr(security, "log_security_event", capturar)
    return registro


def _auten(app, usuario, clave, ip="10.1.1.1"):
    with app.app_context():
        try:
            return al.autenticar(usuario, clave, canal="api", ip=ip).ok
        finally:
            db.session.remove()


def test_acierto_sin_tabla_de_pares_entra_y_deja_el_estado_registrado(app_seguridad, reloj, eventos):
    app = app_seguridad
    _crear(app, "probe.res.tabla")
    with app.app_context():
        UserLoginAttempt.__table__.drop(db.engine)
    assert _auten(app, "probe.res.tabla", CLAVE) is True
    assert _auten(app, "probe.res.tabla", "PROBE-mal") is False
    assert _auten(app, "probe.res.inexistente", "PROBE-mal") is False
    estados = [e for e in eventos if e["tipo"] == "LOGIN_ESTADO_NO_ACTUALIZADO"]
    etapas = {e["extra"].get("etapa") for e in estados}
    assert {"limpieza_pares", "lectura_par"} <= etapas
    assert all(e["extra"].get("excepcion") for e in estados)


def test_fallo_al_reiniciar_contadores_no_bloquea_el_acierto(app_seguridad, reloj, eventos, monkeypatch):
    app = app_seguridad
    _crear(app, "probe.res.reinicio")

    def fallar(*_args, **_kwargs):
        raise RuntimeError("fallo simulado al reiniciar contadores")

    monkeypatch.setattr(al, "_reiniciar_contadores", fallar)
    assert _auten(app, "probe.res.reinicio", CLAVE) is True
    etapas = [e["extra"].get("etapa") for e in eventos if e["tipo"] == "LOGIN_ESTADO_NO_ACTUALIZADO"]
    assert "reinicio_contadores" in etapas


def test_fallo_en_limpieza_de_pares_no_bloquea_el_acierto(app_seguridad, reloj, eventos, monkeypatch):
    app = app_seguridad
    _crear(app, "probe.res.limpieza")

    def fallar(*_args, **_kwargs):
        raise RuntimeError("fallo simulado en la limpieza")

    monkeypatch.setattr(al, "_limpiar_pares_vencidos", fallar)
    assert _auten(app, "probe.res.limpieza", CLAVE) is True


def test_cuenta_bloqueada_a_nivel_usuario_rechaza_el_acierto(app_seguridad, reloj, eventos):
    """Un bloqueo de cuenta (users.locked_until) sigue cerrando el acierto: el best-effort no lo ignora."""
    app = app_seguridad
    cuenta = _crear(app, "probe.res.bloqueo")
    with app.app_context():
        usuario = db.session.get(User, cuenta)
        usuario.locked_until = security.ahora().replace(tzinfo=timezone.utc) + al.DURACION_BLOQUEO
        db.session.commit()
    assert _auten(app, "probe.res.bloqueo", CLAVE) is False


def test_sin_cuenta_bloquea_al_usuario_antes_de_limpiar_pares(app_seguridad, reloj):
    """Orden de bloqueos: la fila del usuario se toma antes que la limpieza de pares (sin ciclo)."""
    app = app_seguridad
    _crear(app, "probe.res.orden")
    sentencias = []

    def registrar(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(statement)

    with app.app_context():
        sa.event.listen(db.engine, "before_cursor_execute", registrar)
        try:
            al.autenticar("probe.res.nadie", "PROBE-mal", canal="api", ip="10.1.1.2")
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", registrar)
            db.session.remove()
    bloqueo_usuario = [i for i, s in enumerate(sentencias) if "WHERE users.id" in s]
    limpieza = [i for i, s in enumerate(sentencias) if s.startswith("DELETE FROM user_login_attempts")]
    assert bloqueo_usuario and limpieza
    assert bloqueo_usuario[0] < limpieza[0]


def test_health_informa_esquema_incompleto_con_503(app_seguridad, reloj):
    app = app_seguridad
    cliente = app.test_client()
    assert cliente.get("/api/health").status_code == 200
    with app.app_context():
        UserLoginAttempt.__table__.drop(db.engine)
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 503
    datos = respuesta.get_json()
    assert datos["codigo"] == "ESQUEMA_INCOMPLETO"
    assert "tabla user_login_attempts" in datos["faltantes"]


# -----------------------------------------------------------------------------
# PostgreSQL: carrera con barrera (solo base de prueba con «carrera» en el nombre)
# -----------------------------------------------------------------------------
def _app_pg(monkeypatch):
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
        for nombre in ("probe.carrera.ventas", "probe.carrera.admin"):
            cuenta = User(username=nombre, role="sales" if "ventas" in nombre else "admin", active=True)
            cuenta.set_password(CLAVE)
            db.session.add(cuenta)
        db.session.commit()
    return app


@pytest.mark.skipif(PG_URL_ENV not in os.environ or "carrera" not in os.environ.get(PG_URL_ENV, ""),
                    reason="requiere APP360_PRUEBAS_PG_URL a una base cuyo nombre contenga «carrera»")
def test_carrera_pg_aciertos_y_fallos_simultaneos_no_fallan_los_aciertos(monkeypatch):
    app = _app_pg(monkeypatch)
    barrera = threading.Barrier(20)
    aciertos, fallos, errores = [], [], []
    candado = threading.Lock()

    def intento(clave, ip, lista):
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                resultado = al.autenticar("probe.carrera.ventas", clave, canal="api", ip=ip)
                with candado:
                    lista.append(resultado.ok)
            except Exception as error:  # un error no controlado es un fallo de la prueba
                with candado:
                    errores.append(repr(error))
            finally:
                db.session.remove()

    hilos = [threading.Thread(target=intento, args=(CLAVE, f"10.5.0.{i}", aciertos)) for i in range(10)]
    hilos += [threading.Thread(target=intento, args=("PROBE-mal", "10.6.0.9", fallos)) for i in range(10)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=120)
    with app.app_context():
        pares_bloqueados = UserLoginAttempt.query.filter(UserLoginAttempt.locked_until.isnot(None)).count()
        db.drop_all()
        db.engine.dispose()
    assert errores == []
    assert aciertos == [True] * 10
    assert fallos == [False] * 10
    assert pares_bloqueados <= 1


@pytest.mark.skipif(PG_URL_ENV not in os.environ or "carrera" not in os.environ.get(PG_URL_ENV, ""),
                    reason="requiere APP360_PRUEBAS_PG_URL a una base cuyo nombre contenga «carrera»")
def test_carrera_pg_desbloqueo_y_fallos_simultaneos_quedan_coherentes(monkeypatch):
    app = _app_pg(monkeypatch)
    with app.app_context():
        cuenta = User.query.filter_by(username="probe.carrera.ventas").one()
        cuenta.failed_login_count = 40
        cuenta.failed_login_window_start = security.ahora().replace(tzinfo=timezone.utc)
        cuenta.locked_until = security.ahora().replace(tzinfo=timezone.utc) + al.DURACION_BLOQUEO
        db.session.commit()
    barrera = threading.Barrier(9)
    respuestas, errores = [], []
    candado = threading.Lock()

    def desbloquear():
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                actor = User.query.filter_by(username="probe.carrera.admin").one()
                objetivo = User.query.filter_by(username="probe.carrera.ventas").one()
                ua.desbloquear_usuario(actor, objetivo)
                db.session.commit()
                with candado:
                    respuestas.append("desbloqueado")
            except ua.ErrorUsuarios as error:
                db.session.rollback()
                with candado:
                    respuestas.append(error.codigo if hasattr(error, "codigo") else "error_usuarios")
            except Exception as error:
                db.session.rollback()
                with candado:
                    errores.append(repr(error))
            finally:
                db.session.remove()

    def fallo(indice):
        with app.app_context():
            try:
                barrera.wait(timeout=60)
                al.autenticar("probe.carrera.ventas", "PROBE-mal", canal="api", ip=f"10.7.0.{indice}")
            except Exception as error:
                with candado:
                    errores.append(repr(error))
            finally:
                db.session.remove()

    hilos = [threading.Thread(target=desbloquear)] + [threading.Thread(target=fallo, args=(i,)) for i in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=120)
    with app.app_context():
        estado = User.query.populate_existing().filter_by(username="probe.carrera.ventas").one()
        contador, bloqueo = estado.failed_login_count, estado.locked_until
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    assert errores == []
    assert len(respuestas) == 1
    # Coherencia: o el desbloqueo ocurrió antes de los fallos (bloqueo vencido o reiniciado) o después
    # (la cuenta vuelve a acumular fallos). En ningún caso queda un bloqueo sin contador.
    assert bloqueo is None or contador >= al.UMBRAL_FALLOS_GLOBALES
