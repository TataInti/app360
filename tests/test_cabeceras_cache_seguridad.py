"""Cabeceras de caché y de seguridad (S1/S2). Datos sintéticos; SQLite en memoria."""

import pytest

from sesion_de_prueba import ADMIN_PRUEBA_ID, asegurar_usuario, marcar_sesion

PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def anonimo(app_seguridad):
    return app_seguridad.test_client()


@pytest.fixture
def admin(app_seguridad):
    asegurar_usuario(app_seguridad, ADMIN_PRUEBA_ID, "probe_admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, ADMIN_PRUEBA_ID)
    return cliente


def _no_store(resp):
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["Pragma"] == "no-cache"


def test_html_anonimo_y_autenticado_no_store_y_permissions_policy(anonimo, admin):
    for resp in (anonimo.get("/"), admin.get("/compras", follow_redirects=False)):
        _no_store(resp)
    pantalla = anonimo.get("/")
    assert pantalla.mimetype == "text/html" and pantalla.status_code == 200
    assert pantalla.headers["Permissions-Policy"] == PERMISSIONS


def test_json_200_401_404_400_no_store_sin_permissions_policy(anonimo):
    for resp, codigo in (
        (anonimo.get("/api/health"), 200),
        (anonimo.get("/api/me"), 401),
        (anonimo.get("/api/no-existe-probe"), 404),
        (anonimo.post("/api/login", data="no-json", content_type="text/plain"), 400),
    ):
        assert resp.status_code in (codigo, 415), (resp.status_code, codigo)
        _no_store(resp)
        assert "Permissions-Policy" not in resp.headers


def test_redireccion_302_no_store(anonimo):
    resp = anonimo.get("/compras")
    assert resp.status_code == 302
    _no_store(resp)


def test_descarga_excel_no_store_con_nombre_y_tipo(admin):
    resp = admin.get("/compras/exportar")
    assert resp.status_code == 200
    assert resp.mimetype == XLSX
    assert "attachment" in resp.headers["Content-Disposition"]
    assert ".xlsx" in resp.headers["Content-Disposition"]
    assert resp.headers["Cache-Control"] == "no-store"  # no el «no-cache» por omisión de send_file
    assert resp.data[:2] == b"PK"


def test_cache_control_fijado_por_la_ruta_no_se_pisa(app_seguridad):
    @app_seguridad.route("/__probe_cache")
    def _probe():
        from flask import make_response

        r = make_response("ok")
        r.headers["Cache-Control"] = "private, max-age=60"
        return r

    resp = app_seguridad.test_client().get("/__probe_cache")
    assert resp.headers["Cache-Control"] == "private, max-age=60"


def test_estaticos_no_reciben_no_store_y_asset_versiona(app_seguridad, anonimo):
    with app_seguridad.test_request_context():
        from flask import render_template_string

        url = render_template_string("{{ asset('css/app_components.css') }}")
    assert url.startswith("/static/css/app_components.css?v=")
    resp = anonimo.get(url)
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("Cache-Control", "")
    assert "Pragma" not in resp.headers
    assert "Permissions-Policy" not in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "no-store" not in anonimo.get("/static/no-existe-probe.css").headers.get("Cache-Control", "")
