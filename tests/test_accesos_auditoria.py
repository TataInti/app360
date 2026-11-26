"""Auditoría de los accesos individuales (Administración › Accesos). Datos sintéticos PROBE."""

import pytest

from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from models.core.user_permission import UserModulePermission
from services import usuarios_admin as ua
from sesion_de_prueba import marcar_sesion


def _crear(app, nombre, rol):
    with app.app_context():
        cuenta = User(username=nombre, role=rol, active=True)
        cuenta.set_password("PROBE-clave-accesos-2026")
        db.session.add(cuenta)
        db.session.commit()
        return cuenta.id


def _cliente(app, nombre, rol):
    cliente = app.test_client()
    marcar_sesion(cliente, _crear(app, nombre, rol))
    return cliente


def _filas(app):
    with app.app_context():
        return [
            (f.actor_username, f.target_username, f.detalle)
            for f in UserAuditLog.query.filter_by(accion="user_access_changed").order_by(UserAuditLog.id)
        ]


def _nivel(app, uid, modulo="rrhh"):
    with app.app_context():
        fila = UserModulePermission.query.filter_by(user_id=uid, module=modulo).first()
        return fila.access_level if fila else "none"


def _put(cliente, uid, permisos):
    return cliente.put(f"/api/admin/accesos/{uid}", json={"permissions": permisos})


@pytest.fixture
def escenario(app_seguridad):
    app = app_seguridad
    admin = _cliente(app, "probe-admin", "admin")
    objetivo = _crear(app, "probe-ventas", "sales")
    return app, admin, objetivo


def test_conceder_deja_una_fila_con_niveles(escenario):
    app, admin, uid = escenario
    assert _put(admin, uid, {"rrhh": "view"}).status_code == 200
    assert _nivel(app, uid) == "view"
    assert _filas(app) == [
        ("probe-admin", "probe-ventas", {"modulo": "rrhh", "nivel_anterior": "none", "nivel_nuevo": "view"})
    ]


def test_sin_diferencia_no_audita(escenario):
    app, admin, uid = escenario
    _put(admin, uid, {"rrhh": "view"})
    assert _put(admin, uid, {"rrhh": "view", "tesoreria": "none"}).status_code == 200
    assert len(_filas(app)) == 1


def test_un_registro_por_modulo_modificado(escenario):
    app, admin, uid = escenario
    _put(admin, uid, {"rrhh": "view"})
    _put(admin, uid, {"rrhh": "view", "gastos": "edit", "compras": "view"})
    assert len(_filas(app)) == 3


def test_retiro_registra_nivel_none(escenario):
    app, admin, uid = escenario
    _put(admin, uid, {"rrhh": "edit"})
    assert _put(admin, uid, {"rrhh": "none"}).status_code == 200
    assert _nivel(app, uid) == "none"
    assert _filas(app)[-1][2] == {"modulo": "rrhh", "nivel_anterior": "edit", "nivel_nuevo": "none"}


def test_gerente_no_modifica_a_admin_ni_manager(app_seguridad):
    app = app_seguridad
    gerente = _cliente(app, "probe-gerente", "gerente")
    for nombre, rol in (("probe-admin2", "admin"), ("probe-manager", "manager")):
        uid = _crear(app, nombre, rol)
        resp = _put(gerente, uid, {"rrhh": "view"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == ua.MENSAJE_JERARQUIA_INSUFICIENTE
    assert _filas(app) == []


def test_gerente_si_modifica_a_un_vendedor(app_seguridad):
    app = app_seguridad
    gerente = _cliente(app, "probe-gerente", "gerente")
    uid = _crear(app, "probe-ventas", "sales")
    assert _put(gerente, uid, {"rrhh": "view"}).status_code == 200
    assert _filas(app)[0][0] == "probe-gerente"


def test_si_falla_la_auditoria_no_se_guarda_el_permiso(escenario, monkeypatch):
    app, admin, uid = escenario

    def _falla(*args, **kwargs):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(ua, "registrar_auditoria", _falla)
    assert _put(admin, uid, {"rrhh": "view"}).status_code == 500
    assert _nivel(app, uid) == "none"
    assert _filas(app) == []


def test_etiqueta_filtro_y_detalle_legible(escenario):
    app, admin, uid = escenario
    _put(admin, uid, {"rrhh": "view"})
    assert ("user_access_changed", "Acceso modificado") in ua.ACCIONES_FILTRO
    with app.app_context():
        fila = UserAuditLog.query.filter_by(accion="user_access_changed").one()
        assert ua._texto_detalle(fila) == "RRHH: Sin acceso → Ver"
        eventos = ua.consultar_auditoria(accion="user_access_changed")
    assert "RRHH: Sin acceso → Ver" in str(eventos)
