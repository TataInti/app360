from models import Product, db
from models.core.user import User
from security import generate_access_token


def _user_and_token(app, username, role):
    with app.app_context():
        user = User(username=username, role=role, active=True)
        db.session.add(user)
        db.session.commit()
        token = generate_access_token(user.id, user.username, role)
        return user.id, token


def _header(token):
    return {"Authorization": f"Bearer {token}"}


def test_jwt_manager_con_rol_bajado_a_sales_deniega_post_y_put(app_seguridad):
    uid, token = _user_and_token(app_seguridad, "PROBE-D3-manager-bajado", "manager")
    with app_seguridad.app_context():
        user = db.session.get(User, uid)
        user.role = "sales"
        db.session.commit()
    cliente = app_seguridad.test_client()
    headers = _header(token)
    alta = cliente.post("/api/products", json={"name": "PROBE D3 rol bajado"}, headers=headers)
    edicion = cliente.put("/api/products/999999", json={"name": "PROBE D3 rol bajado"}, headers=headers)
    assert alta.status_code == 403
    assert edicion.status_code == 403
    assert alta.is_json and edicion.is_json


def test_jwt_usuario_desactivado_responde_401(app_seguridad):
    uid, token = _user_and_token(app_seguridad, "PROBE-D3-inactivo", "operations")
    with app_seguridad.app_context():
        user = db.session.get(User, uid)
        user.active = False
        db.session.commit()
    respuesta = app_seguridad.test_client().post(
        "/api/products", json={"name": "PROBE D3 usuario inactivo"}, headers=_header(token)
    )
    assert respuesta.status_code == 401
    assert respuesta.is_json


def test_jwt_rol_vigente_con_permiso_sigue_creando_producto(app_seguridad):
    uid, token = _user_and_token(app_seguridad, "PROBE-D3-operations", "operations")
    respuesta = app_seguridad.test_client().post(
        "/api/products",
        json={"name": "PROBE D3 permiso vigente", "sku": "PROBE-D3-PERMISO", "price": 12.5},
        headers=_header(token),
    )
    assert respuesta.status_code == 201, respuesta.get_data(as_text=True)
    with app_seguridad.app_context():
        producto = Product.query.filter_by(sku="PROBE-D3-PERMISO").one()
        assert producto.name == "PROBE D3 permiso vigente"
        assert float(producto.price) == 12.5
