"""Comisiones sin usuario_id: solo cuentas activas sin administración total (R-10).

El cálculo recorría User.query.all() e incluía inactivos y administradores. Ahora la
respuesta documenta cuántos usuarios se incluyeron y cuántos se excluyeron, por motivo.
Datos sintéticos rotulados PROBE; base SQLite en memoria.
"""

from datetime import date

from blueprints.comercial import ROLES_ADMIN_TOTAL
from models import Client, Comision, Product, User, Venta, db

CALCULAR = "/api/comercial/comisiones/calcular"


def _cliente_admin(app):
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["user"] = "PROBE-admin-sesion"
        sesion["role"] = "admin"
        sesion["user_id"] = 1
    return cliente


def _crear_usuarios():
    cuentas = (
        ("PROBE-vendedor", "sales", True),
        ("PROBE-inactivo", "sales", False),
        ("PROBE-admin", "admin", True),
        ("PROBE-manager", "manager", True),
        ("PROBE-gerente", "gerente", True),
        ("PROBE-admin-inactivo", "admin", False),
    )
    for username, rol, activo in cuentas:
        db.session.add(User(username=username, role=rol, active=activo))
    db.session.commit()
    return {usuario.username: usuario.id for usuario in User.query.all()}


def _crear_venta_en_el_periodo():
    cliente = Client(name="PROBE-cliente")
    producto = Product(name="PROBE-producto", sku="PROBE-SKU-700")
    db.session.add_all([cliente, producto])
    db.session.commit()
    db.session.add(Venta(
        fecha=date(2026, 10, 15), cliente_id=cliente.id, producto_id=producto.id,
        cantidad=2, precio_contrato=100, precio_efectivo=110,
    ))
    db.session.commit()


def test_roles_de_administracion_total_son_admin_manager_y_gerente():
    assert set(ROLES_ADMIN_TOTAL) == {"admin", "manager", "gerente"}


def test_sin_usuario_id_incluye_solo_activos_sin_administracion(app_seguridad):
    ids = _crear_usuarios()
    _crear_venta_en_el_periodo()

    respuesta = _cliente_admin(app_seguridad).post(CALCULAR, json={"periodo": "2026-10"})
    assert respuesta.status_code == 200
    cobertura = respuesta.get_json()["usuarios"]
    assert cobertura["usuarios_total"] == 6
    assert cobertura["incluidos"] == 1
    assert cobertura["excluidos"] == {"inactivos": 2, "administracion_total": 3}
    assert cobertura["incluidos"] + sum(cobertura["excluidos"].values()) == cobertura["usuarios_total"]
    assert [c.usuario_id for c in Comision.query.all()] == [ids["PROBE-vendedor"]]


def test_usuario_id_explicito_conserva_el_calculo_directo(app_seguridad):
    ids = _crear_usuarios()
    _crear_venta_en_el_periodo()

    respuesta = _cliente_admin(app_seguridad).post(
        CALCULAR, json={"periodo": "2026-10", "usuario_id": ids["PROBE-inactivo"]}
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["usuarios"] == {"filtro": "usuario_id explícito", "incluidos": 1}
    assert [c.usuario_id for c in Comision.query.all()] == [ids["PROBE-inactivo"]]
