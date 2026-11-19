"""Stock: cantidades válidas y par producto×ubicación sin duplicar (corte D1, D-6). Datos PROBE."""

import pytest

from models import BusinessUnit, Location, Product, StockLevel, db
from sesion_de_prueba import asegurar_usuario, marcar_sesion


def _cliente_admin(app):
    asegurar_usuario(app, 1, "PROBE-admin", "admin")
    cliente = app.test_client()
    marcar_sesion(cliente, 1)
    return cliente


@pytest.fixture
def par(app_seguridad):
    unidad = BusinessUnit(name="PROBE-unidad-stock")
    db.session.add(unidad)
    db.session.flush()
    producto = Product(name="PROBE producto stock", sku="PROBE-STOCK-1", business_unit_id=unidad.id)
    ubicacion = Location(name="PROBE deposito stock")
    otra = Location(name="PROBE otra ubicacion stock")
    db.session.add_all([producto, ubicacion, otra])
    db.session.flush()
    existente = StockLevel(product_id=producto.id, location_id=ubicacion.id, quantity=10)
    db.session.add(existente)
    db.session.commit()
    return producto, ubicacion, otra, existente


def _alta(cliente, producto, ubicacion, cantidad):
    return cliente.post(
        "/stock/new",
        data={"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": cantidad},
    )


def test_cantidad_negativa_se_rechaza_sin_cambios(app_seguridad, par):
    producto, _ubicacion, otra, _existente = par
    cliente = _cliente_admin(app_seguridad)
    respuesta = _alta(cliente, producto, otra, "-3")
    assert respuesta.status_code == 400
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=otra.id).count() == 0
    assert "no puede ser negativa" in respuesta.get_data(as_text=True)


def test_cantidad_no_numerica_se_rechaza_sin_cambios(app_seguridad, par):
    producto, _ubicacion, otra, _existente = par
    cliente = _cliente_admin(app_seguridad)
    respuesta = _alta(cliente, producto, otra, "abc")
    assert respuesta.status_code == 400
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=otra.id).count() == 0
    assert "tiene que ser un número entero" in respuesta.get_data(as_text=True)


def test_alta_de_un_par_existente_avisa_y_no_lo_pisa(app_seguridad, par):
    producto, ubicacion, _otra, existente = par
    cliente = _cliente_admin(app_seguridad)
    respuesta = _alta(cliente, producto, ubicacion, "25")
    assert respuesta.status_code == 409
    db.session.refresh(existente)
    assert existente.quantity == 10
    esperado = "Ya hay stock de este producto en esa ubicación (10). Editalo o sumá la diferencia."
    assert esperado in respuesta.get_data(as_text=True)


def test_alta_valida_crea_el_par(app_seguridad, par):
    producto, _ubicacion, otra, _existente = par
    cliente = _cliente_admin(app_seguridad)
    assert _alta(cliente, producto, otra, "4").status_code == 302
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=otra.id).one().quantity == 4


def test_editar_a_un_par_existente_no_duplica(app_seguridad, par):
    producto, ubicacion, otra, _existente = par
    cliente = _cliente_admin(app_seguridad)
    otro_registro = StockLevel(product_id=producto.id, location_id=otra.id, quantity=2)
    db.session.add(otro_registro)
    db.session.commit()
    respuesta = cliente.post(
        f"/stock/edit/{otro_registro.id}",
        data={"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "7"},
    )
    assert respuesta.status_code == 409
    assert StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).count() == 1
    db.session.refresh(otro_registro)
    assert otro_registro.location_id == otra.id
    assert otro_registro.quantity == 2


def test_editar_con_cantidad_negativa_no_cambia_el_registro(app_seguridad, par):
    producto, ubicacion, _otra, existente = par
    cliente = _cliente_admin(app_seguridad)
    respuesta = cliente.post(
        f"/stock/edit/{existente.id}",
        data={"product_id": str(producto.id), "location_id": str(ubicacion.id), "quantity": "-1"},
    )
    assert respuesta.status_code == 400
    db.session.refresh(existente)
    assert existente.quantity == 10
