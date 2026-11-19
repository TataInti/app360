"""Leads: alta sin producto ni ubicación, etapa guardada como nombre y IDs validados (corte D1, D-3).

Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import re

import pytest

from models import BusinessUnit, Lead, db
from sesion_de_prueba import asegurar_usuario, marcar_sesion


def _cliente_admin(app):
    asegurar_usuario(app, 1, "PROBE-admin", "admin")
    cliente = app.test_client()
    marcar_sesion(cliente, 1)
    return cliente


@pytest.fixture
def unidad(app_seguridad):
    unidad = BusinessUnit(name="PROBE-unidad-leads")
    db.session.add(unidad)
    db.session.commit()
    return unidad


def _datos(unidad, **cambios):
    datos = {
        "name": "PROBE lead",
        "business_unit_id": str(unidad.id),
        "product_id": "",
        "location_id": "",
        "campaign_id": "",
        "stage": "contactado",
        "source": "PROBE",
        "status": "nuevo",
    }
    datos.update(cambios)
    return datos


def test_alta_sin_producto_ni_ubicacion_guarda_nulos_y_no_da_500(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    respuesta = cliente.post("/leads/new", data=_datos(unidad))
    assert respuesta.status_code == 302
    lead = Lead.query.filter_by(name="PROBE lead").one()
    assert lead.product_id is None
    assert lead.location_id is None
    assert lead.campaign_id is None


def test_la_etapa_se_guarda_con_su_nombre(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    cliente.post("/leads/new", data=_datos(unidad, stage="propuesta"))
    lead = Lead.query.filter_by(name="PROBE lead").one()
    assert lead.stage == "propuesta"


def test_una_etapa_que_no_es_del_pipeline_cae_en_la_primera(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    cliente.post("/leads/new", data=_datos(unidad, stage="{'name': 'nuevo', 'id': 1}"))
    lead = Lead.query.filter_by(name="PROBE lead").one()
    assert lead.stage == "nuevo"
    assert "{" not in lead.stage


def test_un_id_no_numerico_responde_400_sin_guardar(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    respuesta = cliente.post("/leads/new", data=_datos(unidad, product_id="abc"))
    assert respuesta.status_code == 400
    assert Lead.query.filter_by(name="PROBE lead").count() == 0


def test_sin_unidad_de_negocio_responde_400_sin_guardar(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    respuesta = cliente.post("/leads/new", data=_datos(unidad, business_unit_id=""))
    assert respuesta.status_code == 400
    assert Lead.query.filter_by(name="PROBE lead").count() == 0


def test_el_selector_de_etapa_muestra_nombres_y_no_el_repr_del_diccionario(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    html = cliente.get("/leads/new").get_data(as_text=True)
    opciones = re.findall(r'<option value="([^"]*)"', html)
    assert "contactado" in opciones
    assert all("{" not in valor for valor in opciones)
    assert "{&#39;name" not in html and "{'name" not in html
