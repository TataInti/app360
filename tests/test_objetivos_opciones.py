from datetime import date

import pytest

from app import create_app
from config import Config
from models import db
from models.core.user import User
from models.sabiogo.staging import StgSabiogoVentas


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)

    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        db.session.add(User(id=1, username="test-admin", role="admin", active=True))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


_contador = {"n": 0}


def _venta(
    origen="CARNES",
    producto="Producto de prueba",
    rubro="Rubro de prueba",
    subrubro="Subrubro de prueba",
    marca="Marca de prueba",
    estado="procesado",
    cajas=0,
    kilos=0,
):
    _contador["n"] += 1
    n = _contador["n"]
    return StgSabiogoVentas(
        fecha=date(2026, 11, 3),
        origen=origen,
        sucursal="Central",
        tipo="A",
        codigo=f"OPC-{n}",
        producto=producto,
        rubro=rubro,
        subrubro=subrubro,
        marca=marca,
        cliente="Cliente de prueba",
        vendedor="DEMO ANA",
        comprobante="PRE",
        nro_comprob=f"0001-{n:06d}",
        subtot=1000.0,
        cajas=cajas,
        kilos=kilos,
        estado=estado,
    )


def _cargar(app, filas):
    with app.app_context():
        db.session.add_all(filas)
        db.session.commit()


def _valores(client, dimension, q=None):
    params = {"dimension": dimension}
    if q is not None:
        params["q"] = q
    respuesta = client.get("/api/objetivos-comerciales/opciones", query_string=params)
    assert respuesta.status_code == 200, respuesta.get_json()
    return [item["value"] for item in respuesta.get_json()["opciones"]]


def test_opciones_por_nivel_devuelven_valores_con_datos_sembrados(app, client):
    _cargar(
        app,
        [
            _venta(
                origen="CARNES",
                producto="Vacío Demo por kilo",
                rubro="Carnes",
                subrubro="Vacuno",
                marca="Frigo Demo",
                cajas=2,
                kilos=3,
            ),
            _venta(
                origen="LACTEOS",
                producto="Queso Demo 1kg",
                rubro="Lácteos",
                subrubro="Quesos duros",
                marca="Campo Demo ",
            ),
        ],
    )

    assert _valores(client, "empresa") == ["CARNES", "LACTEOS"]
    assert "Carnes" in _valores(client, "rubro")
    assert "Lácteos" in _valores(client, "rubro")
    assert "Quesos duros" in _valores(client, "subrubro")
    assert "Vacuno" in _valores(client, "subrubro")
    assert "Frigo Demo" in _valores(client, "marca")
    # El valor llega sin espacios sobrantes: no debe aparecer «Campo Demo » con espacio final.
    assert "Campo Demo" in _valores(client, "marca")
    assert "Campo Demo " not in _valores(client, "marca")
    assert "Queso Demo 1kg" in _valores(client, "producto")


def test_opciones_incluyen_capacidades_para_el_selector(app, client):
    _cargar(
        app,
        [
            _venta(producto="Con cajas", cajas=4, kilos=0),
            _venta(producto="Solo importe", cajas=0, kilos=0),
        ],
    )

    respuesta = client.get(
        "/api/objetivos-comerciales/opciones", query_string={"dimension": "producto"}
    )
    opciones = {item["value"]: item for item in respuesta.get_json()["opciones"]}
    assert set(opciones["Con cajas"]) == {"value", "supports_cajas", "supports_kilos"}
    assert opciones["Con cajas"]["supports_cajas"] is True
    assert opciones["Con cajas"]["supports_kilos"] is False
    assert opciones["Solo importe"]["supports_cajas"] is False
    assert opciones["Solo importe"]["supports_kilos"] is False


def test_opciones_excluyen_origen_no_comercial_y_registros_pendientes(app, client):
    _cargar(
        app,
        [
            _venta(origen="LEGACY", producto="Legacy X"),
            _venta(origen="CARNES", producto="Pendiente X", estado="pendiente"),
            _venta(origen="CARNES", producto="Válido X"),
        ],
    )

    valores = _valores(client, "producto")
    assert "Válido X" in valores
    assert "Legacy X" not in valores
    assert "Pendiente X" not in valores


def test_busqueda_filtra_sin_distinguir_mayusculas(app, client):
    _cargar(
        app,
        [
            _venta(subrubro="Quesos duros"),
            _venta(subrubro="Quesos blandos"),
            _venta(subrubro="Embutidos"),
        ],
    )

    assert _valores(client, "subrubro", q="quesos") == ["Quesos blandos", "Quesos duros"]
    assert _valores(client, "subrubro", q="QUESOS") == ["Quesos blandos", "Quesos duros"]
    assert _valores(client, "subrubro", q="embut") == ["Embutidos"]
    assert _valores(client, "subrubro", q="no-existe") == []


def test_busqueda_sin_texto_devuelve_todas_las_opciones(app, client):
    _cargar(app, [_venta(marca="Marca A"), _venta(marca="Marca B")])

    assert _valores(client, "marca", q="") == ["Marca A", "Marca B"]


def test_opciones_se_limitan_a_cien_valores(app, client):
    _cargar(app, [_venta(producto=f"Producto {n:03d}") for n in range(105)])

    valores = _valores(client, "producto")
    assert len(valores) == 100
    assert valores[0] == "Producto 000"


def test_nivel_invalido_responde_400(client):
    respuesta = client.get(
        "/api/objetivos-comerciales/opciones", query_string={"dimension": "zona"}
    )

    assert respuesta.status_code == 400
    assert "empresa, rubro, subrubro, marca o producto" in respuesta.get_json()["error"]


@pytest.mark.parametrize("nivel", ["empresa", "rubro", "subrubro", "marca", "producto"])
def test_cada_nivel_acepta_consulta_vacia(client, nivel):
    assert _valores(client, nivel) == _valores(client, nivel, q="")
