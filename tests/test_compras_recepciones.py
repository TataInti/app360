"""Compras: recepciones sin exceso, sin doble envío y con stock coherente (corte D1, D-4 y D-5).

El mapeo de order_id está en tests/test_compras_mapeo_order_id.py. Datos sintéticos PROBE; SQLite en memoria.
"""

import re

import pytest

from models import BusinessUnit, Location, Product, PurchaseOrder, PurchaseReceipt, StockLevel, db
from sesion_de_prueba import asegurar_usuario, marcar_sesion

PATRON_TOKEN = re.compile(r'name="recepcion_token" value="([0-9a-f]+)"')


def _cliente_admin(app):
    asegurar_usuario(app, 1, "PROBE-admin", "admin")
    cliente = app.test_client()
    marcar_sesion(cliente, 1)
    return cliente


@pytest.fixture
def catalogo(app_seguridad):
    unidad = BusinessUnit(name="PROBE-unidad-compras")
    db.session.add(unidad)
    db.session.flush()
    producto = Product(name="PROBE producto compras", sku="PROBE-COMPRA-1", business_unit_id=unidad.id)
    ubicacion = Location(name="PROBE deposito compras")
    db.session.add_all([producto, ubicacion])
    db.session.commit()
    return producto, ubicacion


def _orden_con(cliente, producto, ubicacion, cantidad):
    cliente.post(
        "/compras/orden-nueva",
        data={
            "supplier_text": "PROBE Proveedor",
            "product_id": str(producto.id),
            "location_id": str(ubicacion.id),
            "quantity": str(cantidad),
        },
    )
    return PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first()


def _token_del_detalle(cliente, orden):
    html = cliente.get(f"/compras/{orden.id}").get_data(as_text=True)
    coincidencia = PATRON_TOKEN.search(html)
    assert coincidencia, "el detalle de la orden no trae recepcion_token"
    return coincidencia.group(1)


def _recibir(cliente, orden, producto, cantidad, token=None):
    token = token or _token_del_detalle(cliente, orden)
    return cliente.post(
        f"/compras/{orden.id}/recepciones",
        data={"product_id": str(producto.id), "quantity": str(cantidad), "recepcion_token": token},
    )


def _cantidad_de_recepciones(orden):
    return PurchaseReceipt.query.filter_by(order_id=orden.id).count()


def _stock(producto, ubicacion):
    return StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).one().quantity


def test_crear_orden_abrir_detalle_recibir_y_volver_a_abrir(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    assert orden is not None
    assert cliente.get(f"/compras/{orden.id}").status_code == 200
    assert _recibir(cliente, orden, producto, 2).status_code == 302
    assert _cantidad_de_recepciones(orden) == 1
    assert cliente.get(f"/compras/{orden.id}").status_code == 200


def test_cinco_pedidas_de_una_vez_y_la_sexta_se_rechaza(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    assert _recibir(cliente, orden, producto, 5).status_code == 302
    assert _recibir(cliente, orden, producto, 1).status_code == 302
    assert _cantidad_de_recepciones(orden) == 1
    assert _stock(producto, ubicacion) == 5
    html = cliente.get(f"/compras/{orden.id}").get_data(as_text=True)
    assert "No se puede recibir más de lo pendiente" in html


def test_cinco_recepciones_de_una_y_la_sexta_no_registra(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    for _ in range(5):
        token = _token_del_detalle(cliente, orden)
        assert _recibir(cliente, orden, producto, 1, token=token).status_code == 302
    assert _cantidad_de_recepciones(orden) == 5
    assert _stock(producto, ubicacion) == 5
    assert _recibir(cliente, orden, producto, 1, token=token).status_code == 302
    assert _cantidad_de_recepciones(orden) == 5
    assert _stock(producto, ubicacion) == 5


def test_doble_envio_registra_una_sola_recepcion(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    token = _token_del_detalle(cliente, orden)
    _recibir(cliente, orden, producto, 1, token=token)
    assert _recibir(cliente, orden, producto, 1, token=token).status_code == 302
    assert _cantidad_de_recepciones(orden) == 1
    assert _stock(producto, ubicacion) == 1


def test_un_formulario_viejo_no_registra_despues_de_otra_recepcion(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    formulario_viejo = _token_del_detalle(cliente, orden)
    formulario_nuevo = _token_del_detalle(cliente, orden)
    _recibir(cliente, orden, producto, 1, token=formulario_nuevo)
    assert _recibir(cliente, orden, producto, 1, token=formulario_viejo).status_code == 302
    assert _cantidad_de_recepciones(orden) == 1
    assert _stock(producto, ubicacion) == 1
    html = cliente.get(f"/compras/{orden.id}").get_data(as_text=True)
    assert "La orden cambió desde que abriste el formulario" in html


def test_una_cantidad_invalida_no_gasta_el_token(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    token = _token_del_detalle(cliente, orden)
    assert _recibir(cliente, orden, producto, "abc", token=token).status_code == 302
    assert _cantidad_de_recepciones(orden) == 0
    assert _recibir(cliente, orden, producto, 2, token=token).status_code == 302
    assert _cantidad_de_recepciones(orden) == 1


def test_recepcion_completa_marca_la_orden_recibida_y_el_stock_suma_las_recepciones(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    _recibir(cliente, orden, producto, 2)
    db.session.refresh(orden)
    assert orden.status != "recibida"
    _recibir(cliente, orden, producto, 3)
    db.session.refresh(orden)
    assert orden.status == "recibida"
    assert _stock(producto, ubicacion) == 5


def test_recibir_sin_token_no_registra_nada(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    orden = _orden_con(cliente, producto, ubicacion, 5)
    cliente.post(f"/compras/{orden.id}/recepciones", data={"product_id": str(producto.id), "quantity": "2"})
    assert _cantidad_de_recepciones(orden) == 0
