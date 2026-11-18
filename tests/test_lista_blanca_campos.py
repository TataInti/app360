"""Lista blanca de campos (hallazgo R-03).

Los formularios de productos, ubicaciones y stock deben seguir guardando sus campos
reales. Los campos ajenos (id, fechas, relaciones, stock) no se asignan desde un
formulario ni desde un payload. Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import pytest

from models import BusinessUnit, Location, Product, StockLevel, db
from sesion_de_prueba import asegurar_usuario, marcar_sesion
from repositories.base_repository import BaseRepository
from services.product_service import ProductService


def _cliente_admin(app):
    asegurar_usuario(app, 1, "PROBE-admin", "admin")
    cliente = app.test_client()
    marcar_sesion(cliente, 1)
    return cliente


@pytest.fixture
def unidad(app_seguridad):
    unidad = BusinessUnit(name="PROBE-unidad")
    db.session.add(unidad)
    db.session.commit()
    return unidad


def test_lista_blanca_de_producto_cubre_el_formulario_y_excluye_lo_protegido():
    campos_formulario = {"sku", "name", "business_unit_id", "category"}
    protegidos = {"id", "created_at", "updated_at", "business_unit", "location", "stock_quantity"}
    assert campos_formulario <= ProductService.ALLOWED_FIELDS
    assert not (protegidos & ProductService.ALLOWED_FIELDS)


# -----------------------------------------------------------------------------
# Formularios reales: los campos que envían se guardan
# -----------------------------------------------------------------------------
def test_formulario_de_producto_guarda_sus_campos(app_seguridad, unidad):
    respuesta = _cliente_admin(app_seguridad).post("/products/new", data={
        "csrf_token": "PROBE",
        "sku": "PROBE-SKU-100",
        "name": "PROBE producto",
        "business_unit_id": str(unidad.id),
        "category": "PROBE",
    })
    assert respuesta.status_code == 302
    producto = Product.query.filter_by(sku="PROBE-SKU-100").first()
    assert producto.name == "PROBE producto"
    assert producto.business_unit_id == unidad.id
    assert producto.category == "PROBE"


def test_ruta_base_crud_de_producto_guarda_sus_campos(app_seguridad, unidad):
    respuesta = _cliente_admin(app_seguridad).post("/new", data={
        "csrf_token": "PROBE",
        "sku": "PROBE-SKU-101",
        "name": "PROBE alta base",
        "business_unit_id": str(unidad.id),
        "category": "",
    })
    assert respuesta.status_code == 302
    assert Product.query.filter_by(sku="PROBE-SKU-101").first().name == "PROBE alta base"


def test_edicion_de_producto_guarda_campos_y_ignora_los_ajenos(app_seguridad, unidad):
    producto = Product(name="PROBE original", sku="PROBE-SKU-200",
                       business_unit_id=unidad.id, stock_quantity=5)
    db.session.add(producto)
    db.session.commit()
    original_id, original_creado = producto.id, producto.created_at

    respuesta = _cliente_admin(app_seguridad).post(f"/products/edit/{original_id}", data={
        "csrf_token": "PROBE",
        "sku": "PROBE-SKU-200",
        "name": "PROBE editado",
        "business_unit_id": str(unidad.id),
        "category": "PROBE",
        # Campos que el formulario no envía y que no deben asignarse:
        "id": "999",
        "created_at": "2000-01-01T00:00:00",
        "stock_quantity": "500",
        "business_unit": "PROBE",
        "campo_inexistente": "x",
    })
    assert respuesta.status_code == 302
    db.session.expire_all()
    editado = db.session.get(Product, original_id)
    assert editado.name == "PROBE editado"
    assert editado.category == "PROBE"
    assert editado.id == original_id
    assert editado.stock_quantity == 5
    assert editado.created_at == original_creado


def test_formulario_de_ubicacion_guarda_sus_campos(app_seguridad):
    cliente = _cliente_admin(app_seguridad)
    alta = cliente.post("/locations/new", data={
        "csrf_token": "PROBE", "name": "PROBE nave", "type": "nave",
    })
    assert alta.status_code == 302
    ubicacion = Location.query.filter_by(name="PROBE nave").first()
    assert ubicacion.type == "nave"

    edicion = cliente.post(f"/locations/edit/{ubicacion.id}", data={
        "csrf_token": "PROBE", "name": "PROBE nave 2", "type": "sucursal",
    })
    assert edicion.status_code == 302
    db.session.expire_all()
    editada = db.session.get(Location, ubicacion.id)
    assert editada.name == "PROBE nave 2"
    assert editada.type == "sucursal"


def test_formulario_de_stock_guarda_sus_campos(app_seguridad, unidad):
    producto = Product(name="PROBE stock", sku="PROBE-SKU-500", business_unit_id=unidad.id)
    ubicacion = Location(name="PROBE-ubicacion-stock", type="nave")
    db.session.add_all([producto, ubicacion])
    db.session.commit()
    cliente = _cliente_admin(app_seguridad)

    alta = cliente.post("/stock/new", data={
        "csrf_token": "PROBE",
        "product_id": str(producto.id),
        "location_id": str(ubicacion.id),
        "quantity": "7",
    })
    assert alta.status_code == 302
    fila = StockLevel.query.filter_by(product_id=producto.id, location_id=ubicacion.id).first()
    assert fila.quantity == 7

    edicion = cliente.post(f"/stock/edit/{fila.id}", data={
        "csrf_token": "PROBE",
        "product_id": str(producto.id),
        "location_id": str(ubicacion.id),
        "quantity": "9",
    })
    assert edicion.status_code == 302
    db.session.expire_all()
    assert db.session.get(StockLevel, fila.id).quantity == 9


# -----------------------------------------------------------------------------
# Servicio y repositorio: campos ajenos y protegidos
# -----------------------------------------------------------------------------
def test_servicio_ignora_campos_desconocidos_y_protegidos(app_seguridad, unidad):
    dto = ProductService().create(
        name="PROBE servicio",
        sku="PROBE-SKU-300",
        business_unit_id=unidad.id,
        id=999,
        created_at="2000-01-01T00:00:00",
        business_unit="PROBE",
        stock_quantity=500,
        campo_inexistente="x",
    )
    assert dto.id != 999
    producto = db.session.get(Product, dto.id)
    assert producto.name == "PROBE servicio"
    assert producto.stock_quantity == 0
    assert producto.created_at.year != 2000


def test_servicio_update_no_asigna_id_ni_relaciones(app_seguridad, unidad):
    otra = BusinessUnit(name="PROBE-otra-unidad")
    producto = Product(name="PROBE", sku="PROBE-SKU-400", business_unit_id=unidad.id)
    db.session.add_all([otra, producto])
    db.session.commit()
    id_original, creado_original, unidad_original = (
        producto.id, producto.created_at, producto.business_unit_id,
    )

    ProductService().update(
        id_original, id=777, created_at="2000-01-01T00:00:00",
        business_unit=otra, name="PROBE nuevo",
    )
    db.session.expire_all()
    actual = db.session.get(Product, id_original)
    assert actual.id == id_original
    assert actual.created_at == creado_original
    assert actual.business_unit_id == unidad_original
    assert actual.name == "PROBE nuevo"


def test_campos_con_nombre_de_identificador_no_provocan_error(app_seguridad, unidad):
    # Antes, un campo 'id' o 'product_id' en el formulario chocaba con el parámetro del
    # método y respondía 500. Ahora se descarta como cualquier campo ajeno.
    producto = Product(name="PROBE id", sku="PROBE-SKU-600", business_unit_id=unidad.id)
    db.session.add(producto)
    db.session.commit()
    respuesta = _cliente_admin(app_seguridad).post(f"/products/edit/{producto.id}", data={
        "csrf_token": "PROBE",
        "name": "PROBE id editado",
        "product_id": "12345",
        "id": "12345",
    })
    assert respuesta.status_code == 302
    db.session.expire_all()
    actual = db.session.get(Product, producto.id)
    assert actual.name == "PROBE id editado"
    assert actual.id == producto.id


def test_repositorio_sin_lista_blanca_no_asigna_nada(app_seguridad):
    class RepositorioSinLista(BaseRepository):
        pass

    with pytest.raises(NotImplementedError):
        RepositorioSinLista(Product).create(name="PROBE")
