"""Catálogos (corte D1, D-7): SKU duplicado, selectores vacíos con enlace, dotación y unidades duplicadas.

Datos sintéticos PROBE; SQLite en memoria.
"""

import re

import pytest

from blueprints.admin import _humanize_integrity_error
from models import BusinessUnit, Product, db
from sesion_de_prueba import asegurar_usuario, marcar_sesion

BOTON_GUARDAR_DESHABILITADO = re.compile(r"<button[^>]*disabled[^>]*>\s*Guardar", re.S)


def _cliente_admin(app):
    asegurar_usuario(app, 1, "PROBE-admin", "admin")
    cliente = app.test_client()
    marcar_sesion(cliente, 1)
    return cliente


@pytest.fixture
def unidad(app_seguridad):
    nueva = BusinessUnit(name="PROBE-unidad-catalogo")
    db.session.add(nueva)
    db.session.commit()
    return nueva


def _alta_producto(cliente, unidad, sku, nombre):
    return cliente.post(
        "/products/new",
        data={"name": nombre, "sku": sku, "category": "PROBE", "business_unit_id": str(unidad.id)},
    )


def test_sku_duplicado_al_crear_avisa_sin_500(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    assert _alta_producto(cliente, unidad, "PROBE-SKU-1", "PROBE uno").status_code == 302
    respuesta = _alta_producto(cliente, unidad, "PROBE-SKU-1", "PROBE dos")
    assert respuesta.status_code == 400
    assert "El SKU ya existe." in respuesta.get_data(as_text=True)
    assert Product.query.filter_by(sku="PROBE-SKU-1").count() == 1


def test_sku_duplicado_al_editar_avisa_y_no_cambia_el_producto(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    _alta_producto(cliente, unidad, "PROBE-SKU-A", "PROBE A")
    _alta_producto(cliente, unidad, "PROBE-SKU-B", "PROBE B")
    segundo = Product.query.filter_by(sku="PROBE-SKU-B").one()
    respuesta = cliente.post(
        f"/products/edit/{segundo.id}",
        data={"name": "PROBE B", "sku": "PROBE-SKU-A", "category": "PROBE", "business_unit_id": str(unidad.id)},
    )
    assert respuesta.status_code == 400
    assert "El SKU ya existe." in respuesta.get_data(as_text=True)
    db.session.refresh(segundo)
    assert segundo.sku == "PROBE-SKU-B"


def test_productos_sin_sku_se_guardan_como_nulos(app_seguridad, unidad):
    cliente = _cliente_admin(app_seguridad)
    assert _alta_producto(cliente, unidad, "", "PROBE sin codigo 1").status_code == 302
    assert _alta_producto(cliente, unidad, "", "PROBE sin codigo 2").status_code == 302
    sin_sku = Product.query.filter(Product.name.like("PROBE sin codigo%"), Product.sku.is_(None)).count()
    assert sin_sku == 2


def test_formulario_de_producto_sin_unidades_avisa_y_deshabilita_guardar(app_seguridad):
    cliente = _cliente_admin(app_seguridad)
    html = cliente.get("/products/new").get_data(as_text=True)
    assert "Todavía no hay unidades de negocio" in html
    assert 'href="/admin"' in html
    assert BOTON_GUARDAR_DESHABILITADO.search(html)


def test_formulario_de_lead_sin_unidades_avisa_y_deshabilita_guardar(app_seguridad):
    cliente = _cliente_admin(app_seguridad)
    html = cliente.get("/leads/new").get_data(as_text=True)
    assert "Todavía no hay unidades de negocio" in html
    assert BOTON_GUARDAR_DESHABILITADO.search(html)


def test_formulario_de_stock_sin_productos_ni_ubicaciones_avisa(app_seguridad):
    cliente = _cliente_admin(app_seguridad)
    html = cliente.get("/stock/new").get_data(as_text=True)
    assert "Todavía no hay productos" in html
    assert "Todavía no hay ubicaciones" in html
    assert BOTON_GUARDAR_DESHABILITADO.search(html)


def test_dotacion_redirige_al_panel_de_rrhh_sin_500(app_seguridad):
    cliente = _cliente_admin(app_seguridad)
    respuesta = cliente.get("/rrhh/dotacion")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/rrhh")


def test_unidad_duplicada_en_administracion_tiene_mensaje_claro():
    error = Exception("UNIQUE constraint failed: business_units.name")
    assert _humanize_integrity_error("stock", "unidades", error) == "Ya existe una unidad con ese nombre."


def test_sku_duplicado_en_administracion_tiene_mensaje_claro():
    error = Exception("UNIQUE constraint failed: products.sku")
    assert _humanize_integrity_error("stock", "productos", error) == "El SKU ya existe."
