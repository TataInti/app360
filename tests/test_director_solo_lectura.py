"""El rol `director` es solo lectura de verdad: ve sus módulos y no escribe en ninguno.

Cubre tesorería (incluida cta cte Friar), compras, gastos y RRHH, por la pantalla web
(sesión) y por la API REST con Bearer. Los demás roles siguen escribiendo en lo suyo.
Datos sintéticos rotulados PROBE; base SQLite en memoria.
"""

import pytest

from models import db
from models.core.user import User
from models.core.user_permission import UserModulePermission
from security import (
    ACCESS_MAP,
    ROLES_SOLO_LECTURA,
    generate_access_token,
    get_user_module_access,
)
from sesion_de_prueba import asegurar_usuario, marcar_sesion

# Blueprints cuyo guard (protect_blueprint) cubre las pantallas y /api/<modulo> de sesión.
PREFIJOS_ENDPOINT = ("tesoreria.", "cta_cte_friar.", "compras.", "gastos.", "rrhh.")
# api_rest: escrituras con Bearer de compras y rrhh (jwt_modulo).
PREFIJOS_REST = ("/api/compras", "/api/rrhh")

LECTURAS_WEB = [
    "/tesoreria", "/tesoreria/movimientos", "/tesoreria/arqueos", "/tesoreria/cta-cte-friar",
    "/compras", "/compras/listado", "/compras/exportar",
    "/gastos",
    "/rrhh", "/rrhh/empleados", "/rrhh/adelantos", "/rrhh/liquidaciones", "/rrhh/ausentismo",
]

# Una escritura que cada rol hace hoy (la guardia la deja pasar; el cuerpo vacío da 400/404).
ESCRITURAS_PROPIAS = [
    pytest.param("finance", "POST", "/api/tesoreria/movimientos", id="finance-tesoreria"),
    pytest.param("caja", "POST", "/api/tesoreria/arqueos", id="caja-tesoreria"),
    pytest.param("finance", "POST", "/api/gastos/registrar", id="finance-gastos"),
    pytest.param("purchases", "POST", "/api/gastos/registrar", id="purchases-gastos"),
    pytest.param("purchases", "POST", "/compras/orden-nueva", id="purchases-compras"),
    pytest.param("operations", "POST", "/compras/orden-nueva", id="operations-compras"),
    pytest.param("hr", "POST", "/api/rrhh/adelantos", id="hr-rrhh"),
    pytest.param("hr", "POST", "/api/rrhh/liquidaciones", id="hr-liquidaciones"),
]
ESCRITURAS_REST_PROPIAS = [
    pytest.param("purchases", "POST", "/api/compras", id="purchases-api-compras"),
    pytest.param("operations", "POST", "/api/compras", id="operations-api-compras"),
    pytest.param("hr", "POST", "/api/rrhh/empleados", id="hr-api-rrhh"),
]

@pytest.fixture
def usuarios(app_seguridad):
    """Un usuario sintético por rol; devuelve {rol: id}."""
    roles = ("director", "finance", "caja", "purchases", "operations", "hr", "direccion")
    ids = {}
    for numero, rol in enumerate(roles, start=10):
        ids[rol] = asegurar_usuario(app_seguridad, numero, f"PROBE-{rol}", rol)
    return ids


def _web(app, usuario_id):
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _bearer(usuario_id, rol):
    return {"Authorization": f"Bearer {generate_access_token(usuario_id, f'PROBE-{rol}', rol)}"}


def _rutas_de_escritura(app):
    """(método, ruta concreta) de toda escritura de los blueprints del alcance."""
    rutas = []
    for regla in app.url_map.iter_rules():
        if not regla.endpoint.startswith(PREFIJOS_ENDPOINT):
            continue
        ruta = regla.rule
        concreta = _concretar(ruta)
        for metodo in sorted(regla.methods - {"GET", "HEAD", "OPTIONS"}):
            rutas.append((metodo, concreta))
    return rutas


def _concretar(ruta):
    import re

    def reemplazo(m):
        return "99999" if (m.group(1) or "").startswith("int") else "x"

    return re.sub(r"<(?:([^:>]+):)?([^>]+)>", reemplazo, ruta)


def test_director_figura_como_solo_lectura():
    assert "director" in ROLES_SOLO_LECTURA
    assert ROLES_SOLO_LECTURA == {"director"}


def test_nivel_de_acceso_del_director_es_view_y_el_resto_sigue_en_edit(usuarios):
    for modulo in ACCESS_MAP["director"]:
        assert get_user_module_access(modulo, usuarios["director"], "director") == "view", modulo
    # Sin cambios para los demás roles.
    assert get_user_module_access("tesoreria", usuarios["finance"], "finance") == "edit"
    assert get_user_module_access("gastos", usuarios["caja"], "caja") == "edit"
    assert get_user_module_access("compras", usuarios["purchases"], "purchases") == "edit"
    assert get_user_module_access("compras", usuarios["operations"], "operations") == "edit"
    assert get_user_module_access("rrhh", usuarios["hr"], "hr") == "edit"
    assert get_user_module_access("dashboard", usuarios["direccion"], "direccion") == "edit"
    assert get_user_module_access("tesoreria", usuarios["direccion"], "direccion") == "none"


def test_toda_escritura_web_de_los_cuatro_modulos_da_403_al_director(app_seguridad, usuarios):
    cliente = _web(app_seguridad, usuarios["director"])
    rutas = _rutas_de_escritura(app_seguridad)
    assert len(rutas) > 30  # tesorería, cta cte Friar, compras, gastos y RRHH
    fallas = []
    for metodo, ruta in rutas:
        r = cliente.open(ruta, method=metodo, json={}, headers={"Referer": "http://localhost/"})
        if r.status_code != 403:
            fallas.append(f"{metodo} {ruta} -> {r.status_code}")
    assert not fallas, fallas


def test_las_escrituras_api_del_director_responden_403_json_con_el_mismo_mensaje(app_seguridad, usuarios):
    cliente = _web(app_seguridad, usuarios["director"])
    r = cliente.post("/api/tesoreria/movimientos", json={})
    assert r.status_code == 403
    assert r.get_json() == {"error": "Sin permiso de edición en el módulo"}


@pytest.mark.parametrize("ruta", LECTURAS_WEB)
def test_el_director_sigue_viendo_las_pantallas(app_seguridad, usuarios, ruta):
    r = _web(app_seguridad, usuarios["director"]).get(ruta)
    assert r.status_code == 200, ruta


def test_las_escrituras_rest_con_bearer_del_director_dan_403(app_seguridad, usuarios):
    cliente = app_seguridad.test_client()
    cabecera = _bearer(usuarios["director"], "director")
    rutas = [
        ("POST", "/api/compras"), ("PUT", "/api/compras/99999"), ("DELETE", "/api/compras/99999"),
        ("POST", "/api/rrhh/empleados"), ("PUT", "/api/rrhh/empleados/99999"),
        ("DELETE", "/api/rrhh/empleados/99999"),
    ]
    for metodo, ruta in rutas:
        r = cliente.open(ruta, method=metodo, json={}, headers=cabecera)
        assert r.status_code == 403, (metodo, ruta, r.status_code)
        assert r.get_json() == {"error": "Sin permiso de edición en el módulo"}


def test_las_lecturas_rest_con_bearer_del_director_siguen_en_200(app_seguridad, usuarios):
    cliente = app_seguridad.test_client()
    cabecera = _bearer(usuarios["director"], "director")
    for ruta in ("/api/compras", "/api/compras/overview", "/api/rrhh", "/api/rrhh/empleados"):
        assert cliente.get(ruta, headers=cabecera).status_code == 200, ruta


@pytest.mark.parametrize("rol,metodo,ruta", ESCRITURAS_PROPIAS)
def test_los_demas_roles_siguen_escribiendo_en_lo_suyo(app_seguridad, usuarios, rol, metodo, ruta):
    r = _web(app_seguridad, usuarios[rol]).open(ruta, method=metodo, json={})
    assert r.status_code not in (401, 403), (rol, ruta, r.status_code)


@pytest.mark.parametrize("rol,metodo,ruta", ESCRITURAS_REST_PROPIAS)
def test_los_demas_roles_siguen_escribiendo_por_bearer(app_seguridad, usuarios, rol, metodo, ruta):
    r = app_seguridad.test_client().open(
        ruta, method=metodo, json={}, headers=_bearer(usuarios[rol], rol)
    )
    assert r.status_code not in (401, 403), (rol, ruta, r.status_code)


def test_la_excepcion_por_usuario_se_suma_y_no_resta(app_seguridad, usuarios):
    """Un director con excepción de edición en otro módulo edita ahí; los suyos siguen en view."""
    db.session.add(UserModulePermission(user_id=usuarios["director"], module="crm", access_level="edit"))
    db.session.commit()
    assert get_user_module_access("crm", usuarios["director"], "director") == "edit"
    assert get_user_module_access("tesoreria", usuarios["director"], "director") == "view"


def test_las_pantallas_no_muestran_botones_de_accion_al_director(app_seguridad, usuarios):
    director = _web(app_seguridad, usuarios["director"])
    caja = _web(app_seguridad, usuarios["caja"])
    # Botón de alta de tesorería: el director no lo ve, caja sí.
    for ruta, marca in (
        ("/tesoreria/movimientos", 'data-bs-target="#modalNuevoMovimiento"'),
        ("/tesoreria/arqueos", 'data-bs-target="#modalNuevoArqueo"'),
        ("/tesoreria", 'data-bs-target="#modalNuevoMovimiento"'),
        ("/tesoreria/cta-cte-friar", 'data-bs-target="#modalNuevoPago"'),
        ("/gastos", 'data-bs-target="#modalNuevoGasto"'),
    ):
        assert marca not in director.get(ruta).get_data(as_text=True), ruta
        assert marca in caja.get(ruta).get_data(as_text=True), ruta
    compras_director = director.get("/compras").get_data(as_text=True)
    assert "/compras/orden-nueva" not in compras_director
    rrhh = _web(app_seguridad, usuarios["hr"])
    for ruta, marca in (
        ("/rrhh/adelantos", 'data-bs-target="#modalNuevoAdelanto"'),
        ("/rrhh/ausentismo", 'data-bs-target="#modalCargar"'),
        ("/rrhh/liquidaciones", 'id="btn-generar"'),
    ):
        assert marca not in director.get(ruta).get_data(as_text=True), ruta
        assert marca in rrhh.get(ruta).get_data(as_text=True), ruta
    assert "const PUEDE_EDITAR = false;" in director.get("/rrhh/adelantos").get_data(as_text=True)
    assert "const PUEDE_EDITAR = true;" in rrhh.get("/rrhh/adelantos").get_data(as_text=True)
