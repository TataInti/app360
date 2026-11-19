"""Control de acceso sin sesión (hotfix fase 0a, rama fix/auth-endpoints-anonimos).

Recorre app.url_map y, sin sesión, exige que cada regla y método responda
302 (pantallas HTML), 401 (API), 403 o 405. Las excepciones son la lista
EXCEPCIONES. Si aparece una ruta nueva que entrega datos sin sesión, esta
prueba falla.

Notas de montaje:
- Usa un cliente sin sesión. El fixture `client` de tests/conftest.py inyecta
  una sesión admin, por eso aquí se usa `cliente_anonimo`.
- Desactiva la validación CSRF (WTF_CSRF_CHECK_DEFAULT) para que las escrituras
  lleguen a la guardia de sesión. La plantilla de login sigue recibiendo
  csrf_token(). La rate limit queda desactivada, como en el resto de la suite.
- Datos sintéticos rotulados PROBE; ninguna credencial real.
"""
import re
from urllib.parse import urlsplit

import pytest
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import RequestRedirect

from app import create_app
from config import Config
from models import Location, Product, StockLevel, db
from models.core.user import User
from models.core.user_permission import UserModulePermission
from sesion_de_prueba import asegurar_usuario, marcar_sesion
from security import (
    ACCESS_MAP,
    SIN_ACCESO_ROUTE,
    first_allowed_route,
    generate_access_token,
)

# Respuestas que prueban que la ruta no entrega datos sin sesión.
ESTADOS_BLOQUEADOS = {302, 401, 403, 405}

# (endpoint, método) -> motivo. Cada excepción se verifica en
# test_excepciones_existen_y_responden_como_se_declaro.
EXCEPCIONES = {
    ("auth.login", "GET"): "Pantalla de login. La ruta es '/'; no existe '/login'.",
    ("auth.login", "POST"): "Envío del formulario de login (límite 10/min por IP).",
    ("static", "GET"): "Archivos estáticos públicos.",
    ("api_rest.health_check", "GET"): "Health check sin datos (GET /api/health).",
    ("api_rest.login", "POST"): "Login de API con usuario y clave (límite 5/min).",
    ("api_rest.refresh_token", "POST"):
        "Renovación de token con refresh token (límite 10/min).",
    ("sabiogo.sabiogo_db_sync", "POST"): "Sincronización SabioGo; exige X-Sync-Key.",
    ("sabiogo.sabiogo_db_sync_daily", "POST"):
        "Sincronización SabioGo diaria; exige X-Sync-Key.",
    ("sabiogo.sabiogo_db_sync_finalize", "POST"):
        "Cierre de sincronización SabioGo; exige X-Sync-Key.",
    ("sabiogo.sabiogo_db_sync_status", "POST"):
        "Estado de sincronización SabioGo; exige X-Sync-Key.",
}

CLAVE_PRUEBA = "PROBE-clave-no-real"

# GET de api_rest que entregan datos de negocio y deben exigir JWT o sesión con módulo.
RUTAS_API_REST = [
    "/api/products",
    "/api/locations",
    "/api/leads",
    "/api/stock",
    "/api/compras",
    "/api/compras/overview",
    "/api/rrhh",
    "/api/rrhh/dotacion",
    "/api/rrhh/empleados",
    "/api/business-units",
]

# GET de api.py (y pantalla web de Ventas) que se usan como muestra por módulo.
RUTAS_API_MODULO = [
    "/api/dashboard-comercial/analisis",
    "/api/dashboard-comercial/mix",
    "/api/panel-ejecutivo-v2",
    "/api/dashboard-financiero",
]


def _registrar_date_trunc_sqlite():
    """analisis y mix usan date_trunc de PostgreSQL. Se registra una función
    equivalente en SQLite, como en test_dashboards_v2.py. Las pruebas de este
    archivo verifican estado y forma de la respuesta, no sus valores.
    """
    def date_trunc(unidad, valor):
        if not valor:
            return None
        texto = str(valor)
        if unidad == "month":
            return f"{texto[:7]}-01 00:00:00"
        if unidad == "year":
            return f"{texto[:4]}-01-01 00:00:00"
        return f"{texto[:10]} 00:00:00"

    conexion = db.engine.raw_connection()
    conexion.create_function("date_trunc", 2, date_trunc)
    conexion.close()


@pytest.fixture
def app_test(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "test-admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_CHECK_DEFAULT", False, raising=False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)

    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        db.create_all()
        _registrar_date_trunc_sqlite()
        asegurar_usuario(application, 1, "PROBE-admin", "admin")
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def cliente_anonimo(app_test):
    return app_test.test_client()


def _crear_usuario(app, username, role, modulos=()):
    with app.app_context():
        usuario = User(username=username, role=role, active=True)
        usuario.set_password(CLAVE_PRUEBA)
        db.session.add(usuario)
        db.session.flush()
        for modulo in modulos:
            db.session.add(
                UserModulePermission(user_id=usuario.id, module=modulo, access_level="view")
            )
        db.session.commit()
        return usuario.id


def _cliente_con_sesion(app, role):
    """Sesión de un usuario real con ese rol: la revalidación lo exige activo en la base."""
    with app.app_context():
        usuario = User.query.filter_by(username=f"PROBE-{role}").first()
        usuario_id = usuario.id if usuario else _crear_usuario(app, f"PROBE-{role}", role)
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def _ruta(location):
    return urlsplit(location).path


def _token_admin(app):
    with app.app_context():
        return generate_access_token(1, "PROBE-admin", "admin")


def _ruta_de_prueba(regla):
    """Reemplaza cada conversor (<int:id>, <path:archivo>, <nombre>) por un valor fijo."""
    return re.sub(r"<[^>]+>", "1", regla.rule)


def _casos_del_mapa(app):
    """Triples (endpoint, método, ruta) que Werkzeug resuelve al propio endpoint.

    HEAD usa el handler de GET y OPTIONS solo devuelve el encabezado Allow,
    por eso no se prueban por separado.
    """
    adaptador = app.url_map.bind("localhost")
    casos = []
    for regla in app.url_map.iter_rules():
        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            ruta = _ruta_de_prueba(regla)
            try:
                endpoint, _ = adaptador.match(ruta, method=metodo)
            except (NotFound, MethodNotAllowed, RequestRedirect):
                endpoint = None
            # Una regla sombreada por otra con la misma ruta no es alcanzable;
            # la que sí lo es se prueba con su propio endpoint.
            if endpoint == regla.endpoint:
                casos.append((regla.endpoint, metodo, ruta))
    return casos


# -----------------------------------------------------------------------------
# Matriz completa sin sesión
# -----------------------------------------------------------------------------
def test_sin_sesion_ninguna_ruta_entrega_datos(app_test, cliente_anonimo):
    casos = _casos_del_mapa(app_test)
    assert len(casos) >= 200, "la matriz debe recorrer el mapa completo de rutas"

    abiertas = []
    for endpoint, metodo, ruta in casos:
        if (endpoint, metodo) in EXCEPCIONES:
            continue
        respuesta = cliente_anonimo.open(ruta, method=metodo)
        if respuesta.status_code not in ESTADOS_BLOQUEADOS:
            abiertas.append(f"{metodo} {ruta} ({endpoint}) -> {respuesta.status_code}")
    assert not abiertas, "Rutas que responden sin sesión:\n" + "\n".join(abiertas)


def test_excepciones_existen_y_responden_como_se_declaro(app_test, cliente_anonimo):
    existentes = {
        (regla.endpoint, metodo)
        for regla in app_test.url_map.iter_rules()
        for metodo in regla.methods
    }
    faltantes = sorted(clave for clave in EXCEPCIONES if clave not in existentes)
    assert not faltantes, f"Excepciones que ya no existen en el mapa: {faltantes}"

    assert cliente_anonimo.get("/").status_code == 200
    assert cliente_anonimo.get("/api/health").status_code == 200
    assert cliente_anonimo.get("/static/css/comercial_paneles.css").status_code == 200
    # Sin cuerpo, los login de API no emiten tokens.
    assert cliente_anonimo.post("/api/login", json={}).status_code == 400
    assert cliente_anonimo.post("/api/refresh", json={}).status_code == 400
    # La sincronización SabioGo nunca responde 200 sin X-Sync-Key.
    reglas = {regla.endpoint: regla for regla in app_test.url_map.iter_rules()}
    for endpoint in (
        "sabiogo.sabiogo_db_sync",
        "sabiogo.sabiogo_db_sync_daily",
        "sabiogo.sabiogo_db_sync_finalize",
        "sabiogo.sabiogo_db_sync_status",
    ):
        ruta = _ruta_de_prueba(reglas[endpoint])
        assert cliente_anonimo.post(ruta).status_code in {401, 503}


# -----------------------------------------------------------------------------
# api.py: JSON 401 sin sesión, 403 sin módulo, 200 con módulo
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("ruta", RUTAS_API_MODULO)
def test_api_sin_sesion_responde_401_json(cliente_anonimo, ruta):
    respuesta = cliente_anonimo.get(ruta)
    assert respuesta.status_code == 401
    assert respuesta.is_json


@pytest.mark.parametrize("ruta", RUTAS_API_MODULO)
def test_api_con_sesion_sin_modulo_responde_403_json(app_test, ruta):
    respuesta = _cliente_con_sesion(app_test, "hr").get(ruta)
    assert respuesta.status_code == 403
    assert respuesta.is_json


@pytest.mark.parametrize(
    "rol, ruta",
    [
        # Panel de Ventas: cantidades, mix y resumen
        ("sales", "/api/dashboard-comercial/analisis?tipo=producto&medida=kilos"),
        ("sales", "/api/dashboard-comercial/mix"),
        ("sales", "/api/dashboard-comercial/resumen-estrategico"),
        # Panel ejecutivo y Tesorería (financiero)
        ("finance", "/api/panel-ejecutivo-v2?period=ytd"),
        ("direccion", "/api/dashboard-financiero?period=30"),
    ],
)
def test_api_con_modulo_responde_200(app_test, rol, ruta):
    respuesta = _cliente_con_sesion(app_test, rol).get(ruta)
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]
    assert respuesta.is_json


def test_panel_de_ventas_carga_con_sesion_autorizada(app_test):
    respuesta = _cliente_con_sesion(app_test, "sales").get("/dashboard-comercial")
    assert respuesta.status_code == 200


# -----------------------------------------------------------------------------
# Respuesta uniforme de /api/: 401 JSON sin sesión; 403 JSON sin módulo.
# Las pantallas HTML siguen redirigiendo (ver test_sin_sesion_ninguna_ruta_entrega_datos).
# -----------------------------------------------------------------------------
def test_api_sin_sesion_responde_401_json_en_todo_el_mapa(app_test, cliente_anonimo):
    casos = [
        (endpoint, metodo, ruta)
        for endpoint, metodo, ruta in _casos_del_mapa(app_test)
        if "/api/" in ruta and (endpoint, metodo) not in EXCEPCIONES
    ]
    assert len(casos) >= 100, "la matriz de /api/ debe recorrer todas las rutas de API"

    no_uniformes = []
    for endpoint, metodo, ruta in casos:
        respuesta = cliente_anonimo.open(ruta, method=metodo)
        if respuesta.status_code != 401 or not respuesta.is_json:
            no_uniformes.append(f"{metodo} {ruta} ({endpoint}) -> {respuesta.status_code}")
    assert not no_uniformes, "Rutas /api/ sin sesión sin respuesta 401 JSON:\n" + "\n".join(
        no_uniformes
    )


@pytest.mark.parametrize(
    "ruta",
    ["/api/admin/accesos", "/api/admin/tesoreria/instrumentos/1/portadores"],
)
def test_api_admin_sin_sesion_responde_401_json(cliente_anonimo, ruta):
    respuesta = cliente_anonimo.get(ruta)
    assert respuesta.status_code == 401
    assert respuesta.is_json
    assert respuesta.get_json() == {"error": "Sesión requerida"}


@pytest.mark.parametrize(
    "ruta",
    ["/api/admin/accesos", "/api/admin/tesoreria/instrumentos/1/portadores"],
)
def test_api_admin_con_rol_sin_admin_responde_403_json(app_test, ruta):
    respuesta = _cliente_con_sesion(app_test, "sales").get(ruta)
    assert respuesta.status_code == 403
    assert respuesta.is_json
    assert respuesta.get_json() == {"error": "Sin acceso al módulo"}


@pytest.mark.parametrize("ruta", RUTAS_API_REST)
def test_api_rest_sin_credencial_responde_401(cliente_anonimo, ruta):
    respuesta = cliente_anonimo.get(ruta)
    assert respuesta.status_code == 401
    assert respuesta.is_json


@pytest.mark.parametrize("ruta", RUTAS_API_REST)
def test_api_rest_con_jwt_valido_responde_200(app_test, cliente_anonimo, ruta):
    cabeceras = {"Authorization": f"Bearer {_token_admin(app_test)}"}
    respuesta = cliente_anonimo.get(ruta, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]


@pytest.mark.parametrize(
    "rol, ruta",
    [
        ("hr", "/api/rrhh"),
        ("hr", "/api/rrhh/empleados?per_page=200"),
        ("operations", "/api/compras?per_page=10"),
        ("operations", "/api/compras/overview?period=2026-11"),
    ],
)
def test_api_rest_pantallas_con_sesion_y_modulo_responden_200(app_test, rol, ruta):
    respuesta = _cliente_con_sesion(app_test, rol).get(ruta)
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:200]
    assert respuesta.is_json


@pytest.mark.parametrize(
    "rol, ruta",
    [
        ("sales", "/api/rrhh/empleados"),
        ("hr", "/api/compras"),
    ],
)
def test_api_rest_sesion_sin_modulo_responde_403(app_test, rol, ruta):
    respuesta = _cliente_con_sesion(app_test, rol).get(ruta)
    assert respuesta.status_code == 403
    assert respuesta.is_json


def test_bearer_invalido_no_cae_a_la_sesion(app_test):
    cliente = _cliente_con_sesion(app_test, "hr")
    respuesta = cliente.get(
        "/api/rrhh/empleados", headers={"Authorization": "Bearer no-es-un-token"}
    )
    assert respuesta.status_code == 401


# -----------------------------------------------------------------------------
# Maestros web: products, locations y stock, incluidas las rutas de BaseCRUD
# -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ruta",
    [
        "/products", "/products/new", "/products/edit/1", "/new", "/edit/1",
        "/locations", "/locations/new", "/locations/edit/1",
        "/stock", "/stock/new", "/stock/edit/1",
    ],
)
def test_maestros_web_sin_sesion_redirigen_al_login(cliente_anonimo, ruta):
    respuesta = cliente_anonimo.get(ruta)
    assert respuesta.status_code == 302
    assert _ruta(respuesta.headers["Location"]) == "/"


def test_escrituras_web_anonimas_no_crean_registros(app_test, cliente_anonimo):
    with app_test.app_context():
        antes = (Location.query.count(), Product.query.count(), StockLevel.query.count())

    datos = {"name": "PROBE-maestro", "type": "PROBE"}
    for ruta in ("/locations/new", "/products/new", "/new", "/stock/new"):
        respuesta = cliente_anonimo.post(ruta, data=datos)
        assert respuesta.status_code == 302, ruta

    with app_test.app_context():
        assert (Location.query.count(), Product.query.count(), StockLevel.query.count()) == antes


@pytest.mark.parametrize("ruta", ["/products", "/locations", "/stock"])
def test_maestros_web_con_modulo_responden_200(app_test, ruta):
    respuesta = _cliente_con_sesion(app_test, "operations").get(ruta)
    assert respuesta.status_code == 200


# -----------------------------------------------------------------------------
# Login sin bucle: roles sin módulos y permisos individuales
# -----------------------------------------------------------------------------
def test_rol_sin_modulos_no_entra_en_bucle(app_test, cliente_anonimo):
    _crear_usuario(app_test, "PROBE-sin-modulos", "comercial")

    login = cliente_anonimo.post(
        "/", data={"username": "PROBE-sin-modulos", "password": CLAVE_PRUEBA}
    )
    assert login.status_code == 302
    assert _ruta(login.headers["Location"]) == SIN_ACCESO_ROUTE

    # Con sesión iniciada, el login y una pantalla bloqueada llevan a "Sin acceso", no a "/".
    assert _ruta(cliente_anonimo.get("/").headers["Location"]) == SIN_ACCESO_ROUTE
    assert _ruta(cliente_anonimo.get("/products").headers["Location"]) == SIN_ACCESO_ROUTE

    pagina = cliente_anonimo.get(SIN_ACCESO_ROUTE)
    assert pagina.status_code == 200
    html = pagina.get_data(as_text=True)
    assert "Sin acceso" in html
    assert 'action="/logout"' in html and 'method="post"' in html


def test_sin_sesion_sin_acceso_redirige_al_login(cliente_anonimo):
    respuesta = cliente_anonimo.get(SIN_ACCESO_ROUTE)
    assert respuesta.status_code == 302
    assert _ruta(respuesta.headers["Location"]) == "/"


def test_permiso_individual_define_la_pantalla_de_entrada(app_test, cliente_anonimo):
    _crear_usuario(app_test, "PROBE-permiso", "comercial", modulos=("products",))

    login = cliente_anonimo.post(
        "/", data={"username": "PROBE-permiso", "password": CLAVE_PRUEBA}
    )
    assert _ruta(login.headers["Location"]) == "/products"


def test_permiso_bi_sin_permiso_panel_no_hace_bucle(app_test, cliente_anonimo):
    # /bi exige el módulo panel (bi.py): con solo el permiso individual bi, la guardia
    # niega la pantalla. Debe llevar a "Sin acceso", no volver a /bi.
    _crear_usuario(app_test, "PROBE-bi", "comercial", modulos=("bi",))

    login = cliente_anonimo.post("/", data={"username": "PROBE-bi", "password": CLAVE_PRUEBA})
    assert _ruta(login.headers["Location"]) == "/bi"

    entrada = cliente_anonimo.get("/bi")
    assert _ruta(entrada.headers["Location"]) == SIN_ACCESO_ROUTE


@pytest.mark.parametrize(
    "rol, destino",
    [
        ("admin", "/dashboard"),
        ("hr", "/rrhh"),
        ("sales", "/leads"),
        ("operations", "/compras"),
        ("finance", "/tesoreria"),
        ("direccion", "/dashboard"),
        ("comercial", SIN_ACCESO_ROUTE),
    ],
)
def test_first_allowed_route_por_rol(app_test, rol, destino):
    with app_test.test_request_context():
        assert first_allowed_route(rol) == destino


@pytest.mark.parametrize("rol", sorted(ACCESS_MAP))
def test_first_allowed_route_nunca_es_el_login(app_test, rol):
    with app_test.test_request_context():
        destino = first_allowed_route(rol)
    assert destino != "/"
    # La ruta de destino debe existir en el mapa; si no, match() lanza NotFound.
    app_test.url_map.bind("localhost").match(destino)
