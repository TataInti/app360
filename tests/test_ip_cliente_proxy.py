"""IP del cliente detrás del proxy (nginx) y cabeceras de seguridad/caché.

La app confía en exactamente un proxy (ProxyFix x_for=1): toma el ÚLTIMO valor de
X-Forwarded-For, el que agregó nginx, y nunca el primero que pudo mandar el cliente.
Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import pytest
from flask_limiter.util import get_remote_address
from flask import request

from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from models.core.user_login_attempt import UserLoginAttempt
from sesion_de_prueba import ADMIN_PRUEBA_ID, asegurar_usuario, marcar_sesion

PROXY = "127.0.0.1"


@pytest.fixture
def app_ip(app_seguridad):
    @app_seguridad.route("/__probe_ip")
    def _probe_ip():
        return {"remote_addr": request.remote_addr, "limiter": get_remote_address(), "scheme": request.scheme}

    return app_seguridad


def _ip(app, xff=None, **extra):
    headers = {"X-Forwarded-For": xff} if xff is not None else {}
    headers.update(extra)
    resp = app.test_client().get("/__probe_ip", headers=headers, environ_overrides={"REMOTE_ADDR": PROXY})
    assert resp.status_code == 200
    return resp.get_json()


@pytest.mark.parametrize(
    "xff, esperada",
    [
        (None, "127.0.0.1"),  # (a) sin cabecera: la del socket
        ("1.2.3.4", "1.2.3.4"),  # (b) un solo valor: lo que enviará nginx tras el cambio
        ("9.9.9.9, 1.2.3.4", "1.2.3.4"),  # (c) cliente antepone un valor: gana el último (nginx)
        ("9.9.9.9,8.8.8.8,1.2.3.4", "1.2.3.4"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_ip_toma_el_ultimo_valor_del_proxy(app_ip, xff, esperada):
    datos = _ip(app_ip, xff)
    assert datos["remote_addr"] == esperada
    assert datos["limiter"] == esperada  # el límite por IP usa la misma


@pytest.mark.parametrize("xff", ["A" * 500, "9.9.9.9, " + "A" * 500, "basura, <b>x</b>", "1.2.3.4, no-es-ip", "999.1.1.1"])
def test_x_forwarded_for_invalido_o_largo_queda_como_invalida(app_ip, xff):
    # (d) El último valor no es una IP: no se confía en nada anterior ni se propaga el texto.
    assert _ip(app_ip, xff)["remote_addr"] == "invalida"


def test_x_forwarded_proto_conserva_https(app_ip):
    assert _ip(app_ip, "1.2.3.4", **{"X-Forwarded-Proto": "https"})["scheme"] == "https"
    assert _ip(app_ip, "1.2.3.4", **{"X-Forwarded-Proto": "http"})["scheme"] == "http"


def _login_api(app, ip_header, usuario="probe_ip_inexistente"):
    return app.test_client().post(
        "/api/login",
        json={"username": usuario, "password": "PROBE-clave-equivocada"},
        headers={"X-Forwarded-For": ip_header} if "\n" not in ip_header else {},
        environ_overrides=(
            {"REMOTE_ADDR": PROXY, "HTTP_X_FORWARDED_FOR": ip_header}
            if "\n" in ip_header
            else {"REMOTE_ADDR": PROXY}
        ),
    )


def test_auditoria_usa_ip_real_y_trunca_a_45(app_seguridad):
    assert _login_api(app_seguridad, "9.9.9.9, 1.2.3.4").status_code == 401
    assert _login_api(app_seguridad, "9.9.9.9, " + "B" * 300).status_code == 401
    with app_seguridad.app_context():
        ips = [f.ip for f in UserAuditLog.query.filter_by(accion="login_failed").all()]
    assert "1.2.3.4" in ips
    assert "9.9.9.9" not in ips
    assert all(i is None or len(i) <= 45 for i in ips)
    assert "invalida" in ips  # el valor largo no es una IP: queda neutralizado


def test_par_cuenta_ip_usa_ip_real_y_trunca(app_seguridad):
    asegurar_usuario(app_seguridad, 7, "probe_ip_cuenta", "admin")
    assert _login_api(app_seguridad, "9.9.9.9, 1.2.3.4", "probe_ip_cuenta").status_code == 401
    assert _login_api(app_seguridad, "9.9.9.9, " + "C" * 300, "probe_ip_cuenta").status_code == 401
    with app_seguridad.app_context():
        ips = {p.ip for p in UserLoginAttempt.query.filter_by(user_id=7).all()}
    assert ips == {"1.2.3.4", "invalida"}


def test_cabecera_con_caracteres_raros_no_se_cuela_en_la_auditoria_como_salto_de_linea(app_seguridad):
    # Un salto de línea en una cabecera lo rechaza el servidor HTTP real; aquí se prueba el
    # peor caso que llegaría a la app (valores crudos) y se exige que no queden saltos de línea.
    for crudo in ("1.2.3.4\r\nX-Inyectado: 1", "1.2.3.4\nFALSO login_ok", "<script>alert(1)</script>"):
        _login_api(app_seguridad, f"9.9.9.9, {crudo}")
    with app_seguridad.app_context():
        ips = [f.ip for f in UserAuditLog.query.filter_by(accion="login_failed").all()]
    assert ips
    for ip in ips:
        assert ip in ("invalida", "127.0.0.1") or ip.replace(".", "").isdigit()
        assert len(ip) <= 45


def test_normalizacion_de_ip_trunca_a_45_caracteres():
    from services.acceso_login import _ip_normalizada

    assert _ip_normalizada("D" * 100) == "D" * 45
    assert _ip_normalizada("1.2.3.4") == "1.2.3.4"
    assert _ip_normalizada(None) is None
