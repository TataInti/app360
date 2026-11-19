import pytest

from models import Product, db
from models.core.user import User
from security import generate_access_token
from sesion_de_prueba import ADMIN_PRUEBA_ID, asegurar_usuario, marcar_sesion


NO_ENCONTRADOS_API_REST = [
    pytest.param("PUT", "/api/products/999999", {"name": "PROBE D3"}, id="products-put"),
    pytest.param("DELETE", "/api/products/999999", None, id="products-delete"),
    pytest.param("PUT", "/api/locations/999999", {"name": "PROBE D3"}, id="locations-put"),
    pytest.param("DELETE", "/api/locations/999999", None, id="locations-delete"),
    pytest.param("PUT", "/api/leads/999999", {"name": "PROBE D3"}, id="leads-put"),
    pytest.param("DELETE", "/api/leads/999999", None, id="leads-delete"),
    pytest.param("PUT", "/api/stock/999999", {"quantity": 1}, id="stock-put"),
    pytest.param("DELETE", "/api/stock/999999", None, id="stock-delete"),
    pytest.param("PUT", "/api/compras/999999", {"status": "PROBE D3"}, id="compras-put"),
    pytest.param("DELETE", "/api/compras/999999", None, id="compras-delete"),
    pytest.param("PUT", "/api/rrhh/empleados/999999", {"first_name": "PROBE D3"}, id="rrhh-put"),
    pytest.param("DELETE", "/api/rrhh/empleados/999999", None, id="rrhh-delete"),
]


def _header(token):
    return {"Authorization": f"Bearer {token}"}


def _admin_client(app):
    asegurar_usuario(app, ADMIN_PRUEBA_ID, "PROBE-D3-admin", "admin")
    cliente = app.test_client()
    marcar_sesion(cliente, ADMIN_PRUEBA_ID)
    return cliente


def _admin_token(app):
    asegurar_usuario(app, ADMIN_PRUEBA_ID, "PROBE-D3-admin", "admin")
    with app.app_context():
        user = db.session.get(User, ADMIN_PRUEBA_ID)
        return generate_access_token(user.id, user.username, user.role)


@pytest.mark.parametrize("metodo,ruta,payload", NO_ENCONTRADOS_API_REST)
def test_put_delete_inexistentes_responden_404_json(app_seguridad, metodo, ruta, payload):
    cliente = app_seguridad.test_client()
    respuesta = cliente.open(ruta, method=metodo, json=payload, headers=_header(_admin_token(app_seguridad)))
    assert respuesta.status_code == 404
    assert respuesta.get_json() == {"error": "No encontrado"}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"name": []}, id="name-lista"),
        pytest.param({"name": "   "}, id="name-vacio"),
        pytest.param({"name": "PROBE D3", "sku": []}, id="sku-no-texto"),
        pytest.param({"name": "PROBE D3", "price": "10"}, id="price-string"),
        pytest.param({"name": "PROBE D3", "price": True}, id="price-bool"),
        pytest.param({"name": "PROBE D3", "location_id": "1"}, id="location-id-string"),
    ],
)
def test_alta_producto_rechaza_tipos_invalidos_sin_escribir(app_seguridad, payload):
    cliente = app_seguridad.test_client()
    token = _admin_token(app_seguridad)
    with app_seguridad.app_context():
        antes = Product.query.count()
    respuesta = cliente.post("/api/products", json=payload, headers=_header(token))
    with app_seguridad.app_context():
        despues = Product.query.count()
    assert respuesta.status_code == 400, respuesta.get_data(as_text=True)
    assert respuesta.is_json
    assert despues == antes


@pytest.mark.parametrize(
    "ruta,expected_error",
    [
        pytest.param(
            "/api/bi/ranking?fecha_desde=no-es-fecha&fecha_hasta=2026-11-19",
            "Fecha inválida; usá el formato AAAA-MM-DD",
            id="bi-ranking-fecha",
        ),
        pytest.param(
            "/api/gastos/listar?fecha_desde=no-es-fecha&fecha_hasta=2026-11-19&categoria_id=1&proveedor_id=1&instrumento_id=1",
            "Fecha inválida; usá el formato AAAA-MM-DD",
            id="gastos-listar-fecha",
        ),
        pytest.param(
            "/api/gastos/resumen?fecha_desde=no-es-fecha&fecha_hasta=2026-11-19",
            "Fecha inválida; usá el formato AAAA-MM-DD",
            id="gastos-resumen-fecha",
        ),
        pytest.param(
            "/api/gastos/exportar?fecha_desde=no-es-fecha&fecha_hasta=2026-11-19&categoria_id=1&proveedor_id=1",
            "Fecha inválida; usá el formato AAAA-MM-DD",
            id="gastos-exportar-fecha",
        ),
        pytest.param(
            "/api/comercial/comisiones?usuario_id=no-es-entero",
            "El parámetro usuario_id debe ser un entero positivo",
            id="comisiones-usuario-id",
        ),
        pytest.param(
            "/sabiogo/api/historial-cargas?limit=no-es-entero",
            "El parámetro limit debe ser un entero positivo",
            id="sabiogo-limit",
        ),
    ],
)
def test_filtros_invalidos_en_rutas_d3_responden_400_json(app_seguridad, ruta, expected_error):
    cliente = _admin_client(app_seguridad)
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 400, respuesta.get_data(as_text=True)[:300]
    assert respuesta.get_json() == {"error": expected_error}


@pytest.mark.parametrize(
    "ruta",
    [
        pytest.param("/api/gastos/listar?fecha_desde=2026-11-01&categoria_id=no-es-entero", id="gastos-listar-id"),
        pytest.param("/api/gastos/exportar?fecha_desde=2026-11-01&categoria_id=no-es-entero", id="gastos-exportar-id"),
    ],
)
def test_filtros_numericos_incompatibles_en_gastos_responden_400(app_seguridad, ruta):
    respuesta = _admin_client(app_seguridad).get(ruta)
    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": "Los filtros numéricos deben ser enteros positivos"}
