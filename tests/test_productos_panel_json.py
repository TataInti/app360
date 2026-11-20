"""Alta de producto desde el panel lateral (SIS-2B, corte 1).

Cubre la rama JSON de /products/new (201, 422 por campo, sin sesión, sin permiso, CSRF), el
formulario HTML que sigue con su redirect, y el parcial de campos que comparten la página
/products/new y el panel de la lista. Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import html as html_lib
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from models import BusinessUnit, Product, db
from models.core.user_permission import UserModulePermission
from sesion_de_prueba import asegurar_usuario, marcar_sesion

RAIZ = Path(__file__).resolve().parents[1]
JSON_ALTA = {"Accept": "application/json"}


def _cliente(app, usuario_id, usuario, rol):
    asegurar_usuario(app, usuario_id, usuario, rol)
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


@pytest.fixture
def unidad(app_seguridad):
    nueva = BusinessUnit(name="PROBE-unidad-panel")
    db.session.add(nueva)
    db.session.commit()
    return nueva


def _alta_json(cliente, datos):
    return cliente.post("/products/new", json=datos, headers=JSON_ALTA)


def test_alta_json_guarda_y_responde_201(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(
        cliente,
        {"sku": "PROBE-JSON-1", "name": "PROBE uno", "business_unit_id": unidad.id, "category": "PROBE"},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["nombre"] == "PROBE uno"
    assert isinstance(cuerpo["id"], int)
    assert Product.query.filter_by(sku="PROBE-JSON-1").one().id == cuerpo["id"]


def test_alta_json_sin_nombre_ni_unidad_devuelve_422_por_campo(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"sku": "PROBE-JSON-VACIO", "name": "  ", "business_unit_id": ""})

    assert respuesta.status_code == 422
    errores = respuesta.get_json()["errors"]
    assert set(errores) == {"name", "business_unit_id"}
    assert respuesta.get_json()["ok"] is False
    assert Product.query.filter_by(sku="PROBE-JSON-VACIO").count() == 0


def test_alta_json_sku_repetido_devuelve_422_en_sku(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    datos = {"sku": "PROBE-JSON-DUP", "name": "PROBE dup", "business_unit_id": unidad.id}
    assert _alta_json(cliente, datos).status_code == 201

    respuesta = _alta_json(cliente, {**datos, "name": "PROBE dup 2"})

    assert respuesta.status_code == 422
    assert respuesta.get_json()["errors"] == {"sku": "El SKU ya existe."}
    assert Product.query.filter_by(sku="PROBE-JSON-DUP").count() == 1


def test_alta_json_sin_sesion_redirige_al_login_y_no_guarda(app_seguridad, unidad):
    anonimo = app_seguridad.test_client()

    respuesta = _alta_json(anonimo, {"sku": "PROBE-JSON-ANON", "name": "PROBE anon", "business_unit_id": unidad.id})

    assert respuesta.status_code == 302
    assert urlsplit(respuesta.location).path == "/"
    assert Product.query.filter_by(sku="PROBE-JSON-ANON").count() == 0


def test_alta_json_con_permiso_de_solo_lectura_no_guarda(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 3, "PROBE-ventas-lectura", "sales")
    db.session.add(UserModulePermission(user_id=3, module="products", access_level="view"))
    db.session.commit()

    respuesta = _alta_json(cliente, {"sku": "PROBE-JSON-VISTA", "name": "PROBE vista", "business_unit_id": unidad.id})

    assert respuesta.status_code == 403
    assert Product.query.filter_by(sku="PROBE-JSON-VISTA").count() == 0


def test_alta_json_sin_acceso_al_modulo_no_guarda(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 4, "PROBE-ventas-sin-modulo", "sales")

    respuesta = _alta_json(cliente, {"sku": "PROBE-JSON-SIN", "name": "PROBE sin", "business_unit_id": unidad.id})

    assert respuesta.status_code == 302
    assert Product.query.filter_by(sku="PROBE-JSON-SIN").count() == 0


def test_alta_json_sin_token_csrf_se_rechaza(app_seguridad, unidad, monkeypatch):
    monkeypatch.setitem(app_seguridad.config, "WTF_CSRF_CHECK_DEFAULT", True)
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"sku": "PROBE-JSON-CSRF", "name": "PROBE csrf", "business_unit_id": unidad.id})

    assert respuesta.status_code == 400
    assert Product.query.filter_by(sku="PROBE-JSON-CSRF").count() == 0


def test_formulario_html_sigue_con_redirect_a_la_lista(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post(
        "/products/new",
        data={"sku": "PROBE-HTML-1", "name": "PROBE html", "business_unit_id": str(unidad.id), "category": ""},
    )

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/products")
    assert Product.query.filter_by(sku="PROBE-HTML-1").count() == 1


def test_formulario_html_con_sku_repetido_avisa_con_400(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")
    datos = {"sku": "PROBE-HTML-DUP", "name": "PROBE html dup", "business_unit_id": str(unidad.id)}
    cliente.post("/products/new", data=datos)

    respuesta = cliente.post("/products/new", data=datos)

    assert respuesta.status_code == 400
    assert "El SKU ya existe." in respuesta.get_data(as_text=True)
    assert Product.query.filter_by(sku="PROBE-HTML-DUP").count() == 1


def test_get_new_muestra_los_campos_del_parcial(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    html = cliente.get("/products/new").get_data(as_text=True)

    for marcado in (
        'id="producto-sku" name="sku"',
        'id="producto-nombre" name="name"',
        'id="business_unit_id" name="business_unit_id"',
        'id="producto-categoria" name="category"',
    ):
        assert marcado in html


def test_panel_y_pagina_comparten_el_parcial(app_seguridad, unidad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    pagina = cliente.get("/products/new").get_data(as_text=True)
    lista = cliente.get("/products").get_data(as_text=True)

    assert 'id="productoPanel"' in lista
    assert 'id="producto-sku" name="sku"' in lista
    assert 'id="business_unit_id" name="business_unit_id"' in lista
    fragmento = '<input type="text" id="producto-sku" name="sku"'
    assert fragmento in pagina and fragmento in lista

    plantilla_pagina = (RAIZ / "templates" / "product_form.html").read_text(encoding="utf-8")
    plantilla_lista = (RAIZ / "templates" / "products_list.html").read_text(encoding="utf-8")
    assert '"_products_form_campos.html"' in plantilla_pagina
    assert '"_products_form_campos.html"' in plantilla_lista
    assert (RAIZ / "templates" / "_products_form_campos.html").is_file()


def test_nombre_con_marcado_y_comillas_se_escapa_en_pagina_y_lista(app_seguridad, unidad):
    nombre = 'PROBE <b>Tom & "Jerry"</b>'
    producto = Product(sku="PROBE-ESC-1", name=nombre, business_unit_id=unidad.id)
    db.session.add(producto)
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    pagina = cliente.get(f"/products/edit/{producto.id}").get_data(as_text=True)
    lista = cliente.get("/products").get_data(as_text=True)

    valor = re.search(r'id="producto-nombre"[^>]*value="([^"]*)"', pagina)
    assert valor and html_lib.unescape(valor.group(1)) == nombre
    assert "PROBE <b>" not in pagina
    assert "PROBE <b>" not in lista
    assert "PROBE &lt;b&gt;Tom &amp; " in lista


def test_pie_sin_unidades_deshabilita_las_acciones_del_panel(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/products").get_data(as_text=True)

    assert re.search(r'data-accion="agregar"\s+disabled', lista)
    assert re.search(r'data-accion="guardar"\s+disabled', lista)
    assert "Todavía no hay unidades de negocio" in lista


def test_js_del_panel_no_interpola_html_ni_usa_innerhtml():
    js = (RAIZ / "static" / "js" / "app_drawer_form.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js
    assert "outerHTML" not in js
