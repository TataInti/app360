"""Compras: secuencia del navegador con recarga entre recepciones (corte D1, D-5).

Reproduce lo que hace el E2E en un navegador: recibir parcial, reintentar un sobrante, y completar
con el formulario recargado. Datos sintéticos PROBE; SQLite en memoria.
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
    unidad = BusinessUnit(name="PROBE-unidad-secuencia")
    db.session.add(unidad)
    db.session.flush()
    producto = Product(name="PROBE producto secuencia", sku="PROBE-SEC-1", business_unit_id=unidad.id)
    ubicacion = Location(name="PROBE deposito secuencia")
    db.session.add_all([producto, ubicacion])
    db.session.commit()
    return producto, ubicacion


def _formulario(cliente, orden):
    """GET del detalle, como lo hace el navegador: devuelve el token que trae el formulario."""
    html = cliente.get(f"/compras/{orden.id}").get_data(as_text=True)
    coincidencia = PATRON_TOKEN.search(html)
    assert coincidencia, "el detalle no trae recepcion_token"
    return coincidencia.group(1), html


def _enviar(cliente, orden, producto, cantidad, token):
    return cliente.post(
        f"/compras/{orden.id}/recepciones",
        data={"product_id": str(producto.id), "quantity": str(cantidad), "recepcion_token": token},
    )


def test_parcial_sobrante_y_completa_con_el_formulario_recargado(app_seguridad, catalogo):
    producto, ubicacion = catalogo
    cliente = _cliente_admin(app_seguridad)
    cliente.post(
        "/compras/orden-nueva",
        data={
            "supplier_text": "PROBE Proveedor",
            "product_id": str(producto.id),
            "location_id": str(ubicacion.id),
            "quantity": "5",
        },
    )
    orden = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first()

    token, _ = _formulario(cliente, orden)
    respuesta = _enviar(cliente, orden, producto, 2, token)
    assert respuesta.status_code == 302
    cantidad = PurchaseReceipt.query.filter_by(order_id=orden.id).count()
    assert cantidad == 1, f"recepción parcial: {cantidad} registros"

    token, _ = _formulario(cliente, orden)
    _enviar(cliente, orden, producto, 4, token)
    token, html = _formulario(cliente, orden)
    assert "No se puede recibir más de lo pendiente" in html, "falta el aviso del sobrante"

    respuesta = _enviar(cliente, orden, producto, 3, token)
    assert respuesta.status_code == 302
    cantidad = PurchaseReceipt.query.filter_by(order_id=orden.id).count()
    assert cantidad == 2, f"recepción de 3 con 3 pendientes: {cantidad} registros"
    db.session.refresh(orden)
    assert orden.status == "recibida", orden.status
    stock = StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).one()
    assert stock.quantity == 5
