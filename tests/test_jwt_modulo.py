"""Escrituras de api_rest con JWT y módulo (hallazgo R-06).

Cada alta, modificación y baja exige JWT válido, acceso al módulo y, en escrituras,
edición. Sin el módulo responde 403 JSON. Las escrituras no aceptan la sesión web.
Datos sintéticos rotulados PROBE; base SQLite en memoria.
"""

import pytest

from models import BusinessUnit, Employee, Location, Product, db
from models.core.user import User
from models.core.user_permission import UserModulePermission
from security import generate_access_token, jwt_modulo
from sesion_de_prueba import asegurar_usuario, marcar_sesion

# Las 18 escrituras de api_rest, con el módulo que exige cada una y un cuerpo mínimo.
ESCRITURAS = [
    ("POST", "/api/products", "products", {"name": "PROBE producto"}),
    ("PUT", "/api/products/1", "products", {"name": "PROBE"}),
    ("DELETE", "/api/products/1", "products", None),
    ("POST", "/api/locations", "locations", {"name": "PROBE ubicación"}),
    ("PUT", "/api/locations/1", "locations", {"name": "PROBE"}),
    ("DELETE", "/api/locations/1", "locations", None),
    ("POST", "/api/leads", "crm", {"name": "PROBE lead", "business_unit_id": 1}),
    ("PUT", "/api/leads/1", "crm", {"name": "PROBE"}),
    ("DELETE", "/api/leads/1", "crm", None),
    ("POST", "/api/stock", "stock", {"product_id": 1, "location_id": 1, "quantity": 1}),
    ("PUT", "/api/stock/1", "stock", {"quantity": 2}),
    ("DELETE", "/api/stock/1", "stock", None),
    ("POST", "/api/compras", "compras", {
        "product_id": 1, "quantity": 2, "unit_price": 10,
        "total_amount": 20, "order_date": "2026-11-18",
    }),
    ("PUT", "/api/compras/1", "compras", {"status": "PROBE"}),
    ("DELETE", "/api/compras/1", "compras", None),
    ("POST", "/api/rrhh/empleados", "rrhh", {
        "first_name": "PROBE", "last_name": "Empleado",
        "email": "probe.empleado@example.invalid",
    }),
    ("PUT", "/api/rrhh/empleados/1", "rrhh", {"first_name": "PROBE"}),
    ("DELETE", "/api/rrhh/empleados/1", "rrhh", None),
]

# Rol que NO tiene el módulo de cada escritura (ACCESS_MAP en security.py).
ROL_SIN_MODULO = {
    "products": "hr",
    "locations": "hr",
    "stock": "hr",
    "crm": "hr",
    "compras": "hr",
    "rrhh": "sales",
}

DEFECTO_ALTA_UBICACION = (
    "Defecto preexistente en origin/main: api_rest.create_location pasa 'province', "
    "que Location no define (TypeError, 500). El guardia de módulo sí la deja pasar; "
    "ver test_alta_de_ubicacion_pasa_el_guardia."
)

# Altas con un rol que sí tiene el módulo: una muestra por blueprint.
ALTAS_CON_MODULO = [
    pytest.param(
        "products", "operations", "/api/products",
        lambda m: {"name": "PROBE producto"}, id="products",
    ),
    pytest.param(
        "locations", "operations", "/api/locations",
        lambda m: {"name": "PROBE ubicación"}, id="locations",
        marks=pytest.mark.xfail(strict=True, reason=DEFECTO_ALTA_UBICACION),
    ),
    pytest.param(
        "stock", "operations", "/api/stock",
        lambda m: {"product_id": m["producto"], "location_id": m["ubicacion"], "quantity": 1},
        id="stock",
    ),
    pytest.param(
        "crm", "sales", "/api/leads",
        lambda m: {"name": "PROBE lead", "business_unit_id": m["unidad"]},
        id="crm",
    ),
    pytest.param(
        "compras", "operations", "/api/compras",
        lambda m: {"product_id": m["producto"], "quantity": 2, "unit_price": 10,
                   "total_amount": 20, "order_date": "2026-11-18"},
        id="compras",
    ),
    pytest.param(
        "rrhh", "hr", "/api/rrhh/empleados",
        lambda m: {"first_name": "PROBE", "last_name": "Empleado",
                   "email": "probe.empleado@example.invalid"},
        id="rrhh",
    ),
]


def _cabecera(rol, user_id=2, username="PROBE-usuario"):
    return {"Authorization": f"Bearer {generate_access_token(user_id, username, rol)}"}


def _usuario_con_permiso(access_level, rol="sales", modulo="products"):
    usuario = User(username="PROBE-permiso", role=rol, active=True)
    db.session.add(usuario)
    db.session.flush()
    permiso = UserModulePermission(user_id=usuario.id, module=modulo, access_level=access_level)
    db.session.add(permiso)
    db.session.commit()
    return usuario.id, permiso


@pytest.fixture(autouse=True)
def usuarios_de_los_tokens(app_seguridad):
    """Los tokens de estas pruebas apuntan a los usuarios 1 y 2: la revocación exige que existan y estén activos."""
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    asegurar_usuario(app_seguridad, 2, "PROBE-usuario", "hr")


@pytest.fixture
def maestros(app_seguridad):
    """Unidad, producto y ubicación sintéticos para las altas que referencian maestros."""
    unidad = BusinessUnit(name="PROBE-unidad")
    producto = Product(name="PROBE-producto", sku="PROBE-SKU-1", business_unit=unidad)
    ubicacion = Location(name="PROBE-ubicacion", type="nave")
    db.session.add_all([unidad, producto, ubicacion])
    db.session.commit()
    return {"unidad": unidad.id, "producto": producto.id, "ubicacion": ubicacion.id}


# -----------------------------------------------------------------------------
# JWT sin módulo -> 403 JSON
# -----------------------------------------------------------------------------
def test_escrituras_sin_el_modulo_responden_403_json(app_seguridad):
    cliente = app_seguridad.test_client()
    fallas = []
    for metodo, ruta, modulo, cuerpo in ESCRITURAS:
        respuesta = cliente.open(
            ruta, method=metodo, json=cuerpo, headers=_cabecera(ROL_SIN_MODULO[modulo])
        )
        if respuesta.status_code != 403 or not respuesta.is_json:
            fallas.append(f"{metodo} {ruta} -> {respuesta.status_code}")
    assert len(ESCRITURAS) == 18
    assert not fallas, "\n".join(fallas)


# -----------------------------------------------------------------------------
# JWT con módulo -> éxito
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("modulo, rol, ruta, cuerpo", ALTAS_CON_MODULO)
def test_alta_con_modulo_responde_201(app_seguridad, maestros, modulo, rol, ruta, cuerpo):
    respuesta = app_seguridad.test_client().post(
        ruta, json=cuerpo(maestros), headers=_cabecera(rol)
    )
    assert respuesta.status_code == 201, respuesta.get_data(as_text=True)[:200]
    assert respuesta.is_json


def test_alta_de_ubicacion_pasa_el_guardia(app_seguridad):
    # Independiente del defecto de create_location: el guardia de módulo no la rechaza.
    respuesta = app_seguridad.test_client().post(
        "/api/locations", json={"name": "PROBE ubicación"}, headers=_cabecera("operations")
    )
    assert respuesta.status_code not in (401, 403)


def test_baja_de_ubicacion_con_modulo_responde_200(app_seguridad):
    ubicacion = Location(name="PROBE-ubicacion", type="nave")
    db.session.add(ubicacion)
    db.session.commit()
    respuesta = app_seguridad.test_client().delete(
        f"/api/locations/{ubicacion.id}", headers=_cabecera("operations")
    )
    assert respuesta.status_code == 200


def test_modificar_y_eliminar_con_modulo_responde_200(app_seguridad, maestros):
    cliente = app_seguridad.test_client()
    producto = maestros["producto"]
    editar = cliente.put(
        f"/api/products/{producto}", json={"name": "PROBE editado"}, headers=_cabecera("operations")
    )
    assert editar.status_code == 200
    borrar = cliente.delete(f"/api/products/{producto}", headers=_cabecera("operations"))
    assert borrar.status_code == 200

    empleado = Employee(first_name="PROBE", last_name="Empleado")
    db.session.add(empleado)
    db.session.commit()
    ruta = f"/api/rrhh/empleados/{empleado.id}"
    editar_empleado = cliente.put(ruta, json={"first_name": "PROBE editado"}, headers=_cabecera("hr"))
    assert editar_empleado.status_code == 200
    assert cliente.delete(ruta, headers=_cabecera("hr")).status_code == 200


# -----------------------------------------------------------------------------
# Nivel view no escribe
# -----------------------------------------------------------------------------
def test_permiso_solo_lectura_no_escribe_en_la_api(app_seguridad, maestros):
    uid, permiso = _usuario_con_permiso("view")
    cabecera = _cabecera("sales", user_id=uid, username="PROBE-permiso")
    cliente = app_seguridad.test_client()
    producto = maestros["producto"]

    intentos = (
        ("POST", "/api/products", {"name": "PROBE"}),
        ("PUT", f"/api/products/{producto}", {"name": "PROBE"}),
        ("DELETE", f"/api/products/{producto}", None),
    )
    for metodo, ruta, cuerpo in intentos:
        respuesta = cliente.open(ruta, method=metodo, json=cuerpo, headers=cabecera)
        assert respuesta.status_code == 403, f"{metodo} {ruta}"
        assert respuesta.is_json

    # Con edición concedida, la misma cuenta sí puede dar de alta.
    permiso.access_level = "edit"
    db.session.commit()
    assert cliente.post("/api/products", json={"name": "PROBE"}, headers=cabecera).status_code == 201


def test_nivel_view_en_el_decorador_lee_pero_no_escribe(app_seguridad):
    @app_seguridad.route("/probe/vista", methods=["GET", "POST"])
    @jwt_modulo("products", "view")
    def probe_vista():
        return {"ok": True}, 200

    uid, permiso = _usuario_con_permiso("view")
    cabecera = _cabecera("sales", user_id=uid, username="PROBE-permiso")
    cliente = app_seguridad.test_client()
    assert cliente.get("/probe/vista", headers=cabecera).status_code == 200
    assert cliente.post("/probe/vista", headers=cabecera).status_code == 403

    permiso.access_level = "edit"
    db.session.commit()
    assert cliente.post("/probe/vista", headers=cabecera).status_code == 200


# -----------------------------------------------------------------------------
# Credenciales: sin token, token inválido, sesión web y token sin rol
# -----------------------------------------------------------------------------
def test_escrituras_sin_token_o_con_token_invalido_responden_401(app_seguridad):
    cliente = app_seguridad.test_client()
    assert cliente.post("/api/products", json={"name": "PROBE"}).status_code == 401
    invalido = {"Authorization": "Bearer no-es-un-token"}
    assert cliente.delete("/api/rrhh/empleados/1", headers=invalido).status_code == 401


def test_escrituras_no_aceptan_sesion_web(app_seguridad):
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    assert cliente.post("/api/products", json={"name": "PROBE"}).status_code == 401


def test_token_sin_rol_no_se_completa_con_la_sesion(app_seguridad):
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    cabecera = {"Authorization": f"Bearer {generate_access_token(1, 'PROBE-sin-rol', None)}"}
    assert cliente.post("/api/products", json={"name": "PROBE"}, headers=cabecera).status_code == 403


def test_nivel_debe_ser_view_o_edit():
    with pytest.raises(ValueError):
        jwt_modulo("products", "admin")
