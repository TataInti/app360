"""Alta de campañas desde el panel lateral (SIS-2B, corte 3).

Cubre la rama JSON de /campaigns/new (201, 422 por campo, sin sesión, sin permiso, CSRF), el formulario
HTML que sigue con su redirect (302) y su aviso (campo name → 400), el escape de textos con <, & y comillas,
y que la lista incluye el parcial del panel como única alta. Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import re
from decimal import Decimal
from html import escape as html_escape
from pathlib import Path

import pytest

from models import Campaign, db
from models.core.user_permission import UserModulePermission
from services.importes import ImporteInvalido, parse_importe
from sesion_de_prueba import asegurar_usuario, marcar_sesion

RAIZ = Path(__file__).resolve().parents[1]
JSON_ALTA = {"Accept": "application/json"}


def _cliente(app, usuario_id, usuario, rol):
    asegurar_usuario(app, usuario_id, usuario, rol)
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _alta_json(cliente, datos):
    return cliente.post("/campaigns/new", json=datos, headers=JSON_ALTA)


def _campana_valida(**cambios):
    datos = {
        "name": "PROBE campana",
        "channel": "Google Ads",
        "cost_estimate": "1.500,50",
        "start_date": "2026-12-01",
        "end_date": "2026-12-31",
        "active": "on",
    }
    datos.update(cambios)
    return datos


def test_alta_json_guarda_y_responde_201(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, _campana_valida())

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["nombre"] == "PROBE campana"
    assert isinstance(cuerpo["id"], int)
    fila = Campaign.query.one()
    assert fila.id == cuerpo["id"]
    assert fila.channel == "Google Ads"
    assert fila.cost_estimate == Decimal("1500.50")
    assert fila.start_date.isoformat() == "2026-12-01" and fila.end_date.isoformat() == "2026-12-31"
    assert fila.active is True


def test_alta_json_sin_activa_guarda_inactiva(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    datos = _campana_valida()
    datos.pop("active")

    respuesta = _alta_json(cliente, datos)

    assert respuesta.status_code == 201
    assert Campaign.query.one().active is False


def test_alta_json_costo_vacio_queda_sin_costo(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, _campana_valida(cost_estimate=""))

    assert respuesta.status_code == 201
    assert Campaign.query.one().cost_estimate is None


def test_alta_json_costo_invalido_devuelve_422_en_cost_estimate(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, _campana_valida(cost_estimate="abc"))

    assert respuesta.status_code == 422
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is False
    assert set(cuerpo["errors"]) == {"cost_estimate"}
    with pytest.raises(ImporteInvalido) as error:
        parse_importe("abc")
    assert cuerpo["errors"]["cost_estimate"] == error.value.mensaje
    assert Campaign.query.count() == 0


def test_alta_json_costo_fuera_de_rango_devuelve_422_en_cost_estimate(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, _campana_valida(cost_estimate="99999999999999"))

    assert respuesta.status_code == 422
    assert set(respuesta.get_json()["errors"]) == {"cost_estimate"}
    assert Campaign.query.count() == 0


def test_alta_json_sin_nombre_devuelve_422_en_name(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    datos = _campana_valida()
    datos.pop("name")

    respuesta = _alta_json(cliente, datos)

    assert respuesta.status_code == 422
    assert set(respuesta.get_json()["errors"]) == {"name"}
    assert Campaign.query.count() == 0


def test_alta_json_sin_sesion_redirige_al_login_y_no_guarda(app_seguridad):
    anonimo = app_seguridad.test_client()

    respuesta = _alta_json(anonimo, _campana_valida())

    assert respuesta.status_code == 302
    assert Campaign.query.count() == 0


def test_alta_json_con_permiso_de_solo_lectura_no_guarda(app_seguridad):
    # El rol «sales» tiene crm en su mapa de acceso (siempre edita); el permiso de solo lectura se prueba con
    # «operations», que no incluye crm.
    cliente = _cliente(app_seguridad, 3, "PROBE-operaciones-lectura", "operations")
    db.session.add(UserModulePermission(user_id=3, module="crm", access_level="view"))
    db.session.commit()

    respuesta = _alta_json(cliente, _campana_valida())

    assert respuesta.status_code == 403
    assert Campaign.query.count() == 0


def test_alta_json_sin_acceso_al_modulo_no_guarda(app_seguridad):
    cliente = _cliente(app_seguridad, 4, "PROBE-operaciones-sin-modulo", "operations")

    respuesta = _alta_json(cliente, _campana_valida())

    assert respuesta.status_code == 302
    assert Campaign.query.count() == 0


def test_alta_json_sin_token_csrf_se_rechaza(app_seguridad, monkeypatch):
    monkeypatch.setitem(app_seguridad.config, "WTF_CSRF_CHECK_DEFAULT", True)
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, _campana_valida())

    assert respuesta.status_code == 400
    assert Campaign.query.count() == 0


def test_formulario_html_sigue_con_redirect_a_la_lista(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post(
        "/campaigns/new",
        data={"name": "PROBE html", "channel": "Mail", "cost_estimate": "12,5", "active": "on"},
    )

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/campaigns")
    fila = Campaign.query.one()
    assert fila.name == "PROBE html" and fila.cost_estimate == Decimal("12.50") and fila.active is True


def test_formulario_html_costo_invalido_avisa_y_vuelve_a_la_lista(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    with pytest.raises(ImporteInvalido) as error:
        parse_importe("abc")

    respuesta = cliente.post("/campaigns/new", data={"name": "PROBE costo", "cost_estimate": "abc"})

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/campaigns")
    assert Campaign.query.count() == 0
    pagina = cliente.get("/campaigns").get_data(as_text=True)
    assert html_escape(error.value.mensaje) in pagina


def test_formulario_html_sin_nombre_responde_400(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post("/campaigns/new", data={"channel": "Mail"})

    assert respuesta.status_code == 400
    assert Campaign.query.count() == 0


def test_lista_muestra_el_panel_como_unica_alta(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/campaigns").get_data(as_text=True)

    assert 'id="campanaPanel"' in lista
    assert 'data-drawer-open="campanaPanel"' in lista
    assert lista.count('action="/campaigns/new"') == 1
    assert 'id="campana-nombre" name="name"' in lista
    assert 'id="campana-costo" name="cost_estimate"' in lista
    assert re.search(r'name="active"\s+checked', lista)
    assert 'data-accion="agregar"' in lista
    plantilla = (RAIZ / "templates" / "campaigns_list.html").read_text(encoding="utf-8")
    assert '"_campaign_form_campos.html"' in plantilla
    assert (RAIZ / "templates" / "_campaign_form_campos.html").is_file()


def test_estado_vacio_y_boton_primario_de_cabecera(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    vacia = cliente.get("/campaigns").get_data(as_text=True)
    db.session.add(Campaign(name="PROBE con filas", active=True))
    db.session.commit()
    con_filas = cliente.get("/campaigns").get_data(as_text=True)

    assert "Todavía no hay campañas" in vacia
    assert vacia.count('data-drawer-open="campanaPanel"') == 2
    assert "Todavía no hay campañas" not in con_filas
    assert con_filas.count('data-drawer-open="campanaPanel"') == 1
    assert 'data-campaign-id="' in con_filas


def test_nombre_con_marcado_y_comillas_se_escapa_en_lista(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    nombre = 'PROBE <b>Serie & "Otoño"</b>'
    cliente.post("/campaigns/new", json=_campana_valida(name=nombre, channel="<i>Mail & \"X\"</i>"), headers=JSON_ALTA)

    lista = cliente.get("/campaigns").get_data(as_text=True)

    assert "PROBE <b>" not in lista
    assert "PROBE &lt;b&gt;Serie &amp; " in lista
    assert re.search(r"Otoño&(quot|#34);", lista)
    assert "<i>Mail" not in lista
    assert "&lt;i&gt;Mail &amp; " in lista


def test_plantilla_de_campanas_no_interpola_html_ni_usa_innerhtml():
    for nombre in ("campaigns_list.html", "_campaign_form_campos.html"):
        plantilla = (RAIZ / "templates" / nombre).read_text(encoding="utf-8")
        assert "innerHTML" not in plantilla
        assert "outerHTML" not in plantilla
