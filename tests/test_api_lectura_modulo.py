"""Lecturas de api_rest con JWT y módulo (hallazgo A-002 del Barrido A).

Los GET de productos, ubicaciones, leads, stock, dotación de RRHH, unidades de
negocio, compras y RRHH exigen un JWT válido con el módulo de su pantalla web.
Sin el módulo responden 403 JSON; sin credencial, 401. Un permiso individual de
solo lectura permite GET y bloquea escrituras. Datos sintéticos rotulados PROBE;
base SQLite en memoria.
"""

import pytest
from security import ACCESS_MAP, generate_access_token

from models import Employee, db
from models.core.user_permission import UserModulePermission
from sesion_de_prueba import asegurar_usuario, marcar_sesion

# (GET de api_rest, módulo que protege la pantalla web de ese dato)
LECTURAS = [
    ("/api/products", "products"),
    ("/api/locations", "locations"),
    ("/api/leads", "crm"),
    ("/api/stock", "stock"),
    ("/api/rrhh/dotacion", "rrhh"),
    ("/api/business-units", "stock"),
    ("/api/compras", "compras"),
    ("/api/compras/overview", "compras"),
    ("/api/rrhh", "rrhh"),
    ("/api/rrhh/empleados", "rrhh"),
]
# Las cuatro que también atiende la sesión web (jwt_o_sesion).
LECTURAS_CON_SESION = [
    ("/api/compras", "compras"),
    ("/api/compras/overview", "compras"),
    ("/api/rrhh", "rrhh"),
    ("/api/rrhh/empleados", "rrhh"),
]

# Un usuario sintético por rol de ACCESS_MAP. "consulta" no tiene ningún módulo.
USUARIOS = {
    "admin": (1, "PROBE-admin"),
    "operations": (2, "PROBE-operaciones"),
    "sales": (3, "PROBE-ventas"),
    "hr": (4, "PROBE-rrhh"),
    "finance": (5, "PROBE-finanzas"),
    "consulta": (6, "PROBE-consulta"),
}
SIN_ACCESO = {"error": "Sin acceso al módulo"}


def _tiene_modulo(rol, modulo):
    permitidos = ACCESS_MAP.get(rol, [])
    return "all" in permitidos or modulo in permitidos


def _cabecera(rol):
    usuario_id, nombre = USUARIOS[rol]
    return {"Authorization": f"Bearer {generate_access_token(usuario_id, nombre, rol)}"}


@pytest.fixture(autouse=True)
def usuarios_sinteticos(app_seguridad):
    for rol, (usuario_id, nombre) in USUARIOS.items():
        asegurar_usuario(app_seguridad, usuario_id, nombre, rol)


# -----------------------------------------------------------------------------
# JWT: con módulo -> 200; sin módulo -> 403 JSON (matriz rol x ruta)
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("rol", list(USUARIOS))
@pytest.mark.parametrize("ruta, modulo", LECTURAS)
def test_lectura_jwt_responde_segun_el_modulo(app_seguridad, ruta, modulo, rol):
    respuesta = app_seguridad.test_client().get(ruta, headers=_cabecera(rol))
    if _tiene_modulo(rol, modulo):
        assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]
        assert respuesta.is_json
    else:
        assert respuesta.status_code == 403, f"{rol} {ruta} -> {respuesta.status_code}"
        assert respuesta.is_json
        assert respuesta.get_json() == SIN_ACCESO


def test_dotacion_no_entrega_salarios_a_roles_sin_modulo(app_seguridad):
    db.session.add(Employee(first_name="PROBE", last_name="Dotacion", salary=250000.5))
    db.session.commit()
    cliente = app_seguridad.test_client()

    denegado = cliente.get("/api/rrhh/dotacion", headers=_cabecera("sales"))
    assert denegado.status_code == 403
    assert "salary" not in denegado.get_data(as_text=True)

    permitido = cliente.get("/api/rrhh/dotacion", headers=_cabecera("hr"))
    assert permitido.status_code == 200
    assert permitido.get_json()["items"][0]["salary"] == 250000.5


# -----------------------------------------------------------------------------
# Anónimo y Bearer inválido: nunca caen a la sesión
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("ruta, modulo", LECTURAS)
def test_lectura_anonima_responde_401(app_seguridad, ruta, modulo):
    respuesta = app_seguridad.test_client().get(ruta)
    assert respuesta.status_code == 401
    assert respuesta.is_json


@pytest.mark.parametrize("ruta, modulo", LECTURAS)
def test_bearer_invalido_no_cae_a_la_sesion(app_seguridad, ruta, modulo):
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)  # sesión admin con todos los módulos
    respuesta = cliente.get(ruta, headers={"Authorization": "Bearer no-es-un-token"})
    assert respuesta.status_code == 401


# -----------------------------------------------------------------------------
# jwt_o_sesion: el Bearer también respeta el módulo; la sesión web sigue igual
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("ruta, modulo", LECTURAS_CON_SESION)
def test_bearer_sin_modulo_responde_403_en_jwt_o_sesion(app_seguridad, ruta, modulo):
    # Antes, un Bearer válido pasaba sin mirar el módulo (security.py jwt_o_sesion).
    rol_sin_modulo = "consulta"
    respuesta = app_seguridad.test_client().get(ruta, headers=_cabecera(rol_sin_modulo))
    assert respuesta.status_code == 403
    assert respuesta.get_json() == SIN_ACCESO


@pytest.mark.parametrize("ruta, modulo", LECTURAS_CON_SESION)
def test_bearer_con_modulo_responde_200_en_jwt_o_sesion(app_seguridad, ruta, modulo):
    rol = "admin"
    respuesta = app_seguridad.test_client().get(ruta, headers=_cabecera(rol))
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]


def test_sesion_web_con_modulo_responde_200_y_sin_modulo_403(app_seguridad):
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 4)  # hr: módulo rrhh
    assert cliente.get("/api/rrhh/empleados").status_code == 200

    marcar_sesion(cliente, 3)  # sales: sin rrhh
    denegado = cliente.get("/api/rrhh/empleados")
    assert denegado.status_code == 403
    assert denegado.get_json() == SIN_ACCESO


# -----------------------------------------------------------------------------
# Permiso individual de solo lectura: GET sí, escrituras no
# -----------------------------------------------------------------------------
def test_permiso_solo_lectura_permite_get_y_bloquea_escrituras(app_seguridad):
    cliente = app_seguridad.test_client()
    usuario_id = USUARIOS["consulta"][0]
    for modulo in ("products", "stock", "crm", "rrhh"):
        db.session.add(
            UserModulePermission(user_id=usuario_id, module=modulo, access_level="view")
        )
    db.session.commit()
    cabecera = _cabecera("consulta")

    assert cliente.get("/api/products", headers=cabecera).status_code == 200
    assert cliente.get("/api/stock", headers=cabecera).status_code == 200
    assert cliente.get("/api/leads", headers=cabecera).status_code == 200
    assert cliente.get("/api/rrhh/dotacion", headers=cabecera).status_code == 200

    escrituras = (
        ("POST", "/api/products", {"name": "PROBE"}),
        ("PUT", "/api/products/1", {"name": "PROBE"}),
        ("DELETE", "/api/products/1", None),
        ("POST", "/api/stock", {"product_id": 1, "location_id": 1, "quantity": 1}),
    )
    for metodo, ruta, cuerpo in escrituras:
        respuesta = cliente.open(ruta, method=metodo, json=cuerpo, headers=cabecera)
        assert respuesta.status_code == 403, f"{metodo} {ruta}"
        assert respuesta.is_json
        assert "error" in respuesta.get_json()


def test_me_sigue_disponible_con_cualquier_jwt_valido(app_seguridad):
    # Justificado: devuelve solo la identidad del propio token (sin datos de negocio).
    respuesta = app_seguridad.test_client().get("/api/me", headers=_cabecera("consulta"))
    assert respuesta.status_code == 200
    assert respuesta.get_json()["role"] == "consulta"
