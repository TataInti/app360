"""Alta de stock desde el panel lateral (SIS-2B, corte 2).

Cubre la rama JSON de /stock/new (201, 422 por campo, sin sesión, sin permiso, CSRF), el formulario
HTML que sigue con su redirect (302), su aviso 400 (cantidad o campos) y su 409 (par repetido), el
escape de textos con <, & y comillas, y el parcial de campos que comparten la página /stock/new,
/stock/edit/<id> y el panel de la lista. Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from models import BusinessUnit, Location, Product, StockLevel, db
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
def catalogo(app_seguridad):
    unidad = BusinessUnit(name="PROBE-unidad-stock-panel")
    db.session.add(unidad)
    db.session.flush()
    producto = Product(name="PROBE producto panel", sku="PROBE-PANEL-P1", business_unit_id=unidad.id)
    otro_producto = Product(name="PROBE producto dos", sku="PROBE-PANEL-P2", business_unit_id=unidad.id)
    ubicacion = Location(name="PROBE ubicacion panel", type="nave")
    otra = Location(name="PROBE ubicacion dos", type="sucursal")
    db.session.add_all([producto, otro_producto, ubicacion, otra])
    db.session.commit()
    return producto, otro_producto, ubicacion, otra


def _alta_json(cliente, datos):
    return cliente.post("/stock/new", json=datos, headers=JSON_ALTA)


def test_alta_json_guarda_y_responde_201(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "4"},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["producto"] == "PROBE producto panel"
    assert cuerpo["ubicacion"] == "PROBE ubicacion panel"
    assert cuerpo["cantidad"] == 4
    assert isinstance(cuerpo["id"], int)
    fila = StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).one()
    assert fila.id == cuerpo["id"] and fila.quantity == 4


def test_alta_json_con_campos_vacios_devuelve_422_por_campo(app_seguridad, catalogo):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(cliente, {"product_id": "", "location_id": "", "quantity": "3"})

    assert respuesta.status_code == 422
    cuerpo = respuesta.get_json()
    assert cuerpo["ok"] is False
    assert set(cuerpo["errors"]) == {"product_id", "location_id"}
    assert StockLevel.query.count() == 0


def test_alta_json_cantidad_negativa_devuelve_422_en_quantity(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "-2"},
    )

    assert respuesta.status_code == 422
    assert respuesta.get_json()["errors"] == {"quantity": "La cantidad no puede ser negativa."}
    assert StockLevel.query.count() == 0


def test_alta_json_cantidad_no_numerica_devuelve_422_en_quantity(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "diez"},
    )

    assert respuesta.status_code == 422
    assert set(respuesta.get_json()["errors"]) == {"quantity"}
    assert "tiene que ser un número entero" in respuesta.get_json()["errors"]["quantity"]


def test_alta_json_par_existente_devuelve_422_en_ubicacion_y_no_pisa(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    existente = StockLevel(product_id=producto.id, location_id=ubicacion.id, quantity=10)
    db.session.add(existente)
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "5"},
    )

    assert respuesta.status_code == 422
    errores = respuesta.get_json()["errors"]
    assert set(errores) == {"location_id"}
    assert "Ya hay stock de este producto en esa ubicación (10)" in errores["location_id"]
    assert existente.quantity == 10
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).count() == 1


def test_alta_json_sin_sesion_redirige_al_login_y_no_guarda(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    anonimo = app_seguridad.test_client()

    respuesta = _alta_json(
        anonimo,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "1"},
    )

    assert respuesta.status_code == 302
    assert urlsplit(respuesta.location).path == "/"
    assert StockLevel.query.count() == 0


def test_alta_json_con_permiso_de_solo_lectura_no_guarda(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 3, "PROBE-ventas-lectura", "sales")
    db.session.add(UserModulePermission(user_id=3, module="stock", access_level="view"))
    db.session.commit()

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "2"},
    )

    assert respuesta.status_code == 403
    assert StockLevel.query.count() == 0


def test_alta_json_sin_acceso_al_modulo_no_guarda(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 4, "PROBE-ventas-sin-modulo", "sales")

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "2"},
    )

    assert respuesta.status_code == 302
    assert StockLevel.query.count() == 0


def test_alta_json_sin_token_csrf_se_rechaza(app_seguridad, catalogo, monkeypatch):
    producto, _otro, ubicacion, _otra = catalogo
    monkeypatch.setitem(app_seguridad.config, "WTF_CSRF_CHECK_DEFAULT", True)
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = _alta_json(
        cliente,
        {"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "1"},
    )

    assert respuesta.status_code == 400
    assert StockLevel.query.count() == 0


def test_formulario_html_sigue_con_redirect_a_la_lista(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post(
        "/stock/new",
        data={"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "7"},
    )

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/stock")
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).one().quantity == 7


def test_formulario_html_con_par_repetido_responde_409_con_aviso(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    db.session.add(StockLevel(product_id=producto.id, location_id=ubicacion.id, quantity=10))
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post(
        "/stock/new",
        data={"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "3"},
    )

    assert respuesta.status_code == 409
    assert "Ya hay stock de este producto en esa ubicación (10)" in respuesta.get_data(as_text=True)
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).one().quantity == 10


def test_formulario_html_cantidad_negativa_responde_400(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post(
        "/stock/new",
        data={"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "-1"},
    )

    assert respuesta.status_code == 400
    assert "no puede ser negativa" in respuesta.get_data(as_text=True)
    assert StockLevel.query.count() == 0


def test_formulario_html_sin_producto_responde_400_con_su_aviso(app_seguridad, catalogo):
    _producto, _otro, ubicacion, _otra = catalogo
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.post(
        "/stock/new",
        data={"location_id": str(ubicacion.id), "quantity": "1"},
    )

    assert respuesta.status_code == 400
    assert "Elegí un producto y una ubicación." in respuesta.get_data(as_text=True)
    assert StockLevel.query.count() == 0


def test_get_new_muestra_los_campos_del_parcial(app_seguridad, catalogo):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    html = cliente.get("/stock/new").get_data(as_text=True)

    for marcado in (
        'id="product_id" name="product_id"',
        'id="location_id" name="location_id"',
        'id="stock-cantidad" name="quantity"',
    ):
        assert marcado in html


def test_panel_y_pagina_comparten_el_parcial(app_seguridad, catalogo):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    pagina = cliente.get("/stock/new").get_data(as_text=True)
    lista = cliente.get("/stock").get_data(as_text=True)

    assert 'id="stockPanel"' in lista
    fragmento = '<select id="product_id" name="product_id"'
    assert fragmento in pagina and fragmento in lista
    assert 'id="stock-cantidad" name="quantity"' in pagina and 'id="stock-cantidad" name="quantity"' in lista

    plantilla_pagina = (RAIZ / "templates" / "stock_form.html").read_text(encoding="utf-8")
    plantilla_lista = (RAIZ / "templates" / "stock_list.html").read_text(encoding="utf-8")
    assert '"_stock_form_campos.html"' in plantilla_pagina
    assert '"_stock_form_campos.html"' in plantilla_lista
    assert (RAIZ / "templates" / "_stock_form_campos.html").is_file()


def test_textos_con_marcado_y_comillas_se_escapan_en_lista_y_alta(app_seguridad, catalogo):
    nombre = 'PROBE <b>Tom & "Jerry"</b>'
    producto = Product(sku="PROBE-ESC-ST", name=nombre, business_unit_id=catalogo[0].business_unit_id)
    ubicacion = Location(name='PROBE <i>Dep & "Norte"</i>', type="nave")
    db.session.add_all([producto, ubicacion])
    db.session.flush()
    db.session.add(StockLevel(product_id=producto.id, location_id=ubicacion.id, quantity=2))
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/stock").get_data(as_text=True)
    alta = cliente.get("/stock/new").get_data(as_text=True)

    for html_publico in (lista, alta):
        assert "PROBE <b>" not in html_publico
        assert "PROBE <i>" not in html_publico
        assert "PROBE &lt;b&gt;Tom &amp; " in html_publico
        assert "PROBE &lt;i&gt;Dep &amp; " in html_publico
        assert re.search(r"Jerry&(quot|#34);", html_publico)


def test_pie_sin_catalogos_deshabilita_las_acciones_del_panel(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/stock").get_data(as_text=True)

    assert re.search(r'data-accion="agregar"\s+disabled', lista)
    assert re.search(r'data-accion="guardar"\s+disabled', lista)
    assert "Todavía no hay productos" in lista
    assert "Todavía no hay ubicaciones" in lista


def test_fila_de_la_lista_expone_el_id_para_resaltar_el_alta(app_seguridad, catalogo):
    producto, _otro, ubicacion, _otra = catalogo
    fila = StockLevel(product_id=producto.id, location_id=ubicacion.id, quantity=1)
    db.session.add(fila)
    db.session.commit()
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/stock").get_data(as_text=True)

    assert f'data-stock-id="{fila.id}"' in lista
    assert "data-stock-region" in lista


def test_plantilla_de_stock_no_interpola_html_ni_usa_innerhtml():
    for nombre in ("stock_list.html", "_stock_form_campos.html", "stock_form.html"):
        plantilla = (RAIZ / "templates" / nombre).read_text(encoding="utf-8")
        assert "innerHTML" not in plantilla
        assert "outerHTML" not in plantilla


def test_panel_stock_primera_opcion_vacia_y_obligatoria(app_seguridad, catalogo):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    lista = cliente.get("/stock").get_data(as_text=True)
    panel = lista[lista.index('id="stockPanel"'):]

    patron = (
        r'<select id="product_id" name="product_id"[^>]*\srequired[^>]*>\s*'
        r'<option value="">Elegí un producto</option>\s*<option value="\d+"'
    )
    assert re.search(patron, panel)
    assert panel.count('<option value="">Elegí un producto</option>') == 1


def test_pagina_stock_new_conserva_su_seleccion_sin_opcion_vacia(app_seguridad, catalogo):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    pagina = cliente.get("/stock/new").get_data(as_text=True)

    assert "Elegí un producto</option>" not in pagina
    assert re.search(r'<select id="product_id" name="product_id"[^>]*\srequired', pagina)

