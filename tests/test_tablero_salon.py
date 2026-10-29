from datetime import date

import pytest

from app import create_app
from config import Config
from models import db
from models.comercial import ComercialVendedor, ComercialVendedorAlias
from models.sabiogo.staging import StgSabiogoVentas
from models.time_utils import today_local_date
from services.vendedores_comerciales import normalizar_nombre_origen


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)

    application = create_app()
    application.config["TESTING"] = True
    application.jinja_env.globals["csrf_token"] = lambda: "test-csrf"
    with application.app_context():
        db.create_all()
        salon = ComercialVendedor(nombre_visible="Salón", activo=True)
        db.session.add(salon)
        db.session.flush()
        db.session.add(
            ComercialVendedorAlias(
                vendedor_id=salon.id,
                nombre_origen="SALÓN",
                nombre_normalizado=normalizar_nombre_origen("SALÓN"),
            )
        )
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = "test"
        session["role"] = "admin"
    return client


def agregar_factura(
    *,
    fecha=date(2024, 6, 10),
    vendedor="SALÓN",
    comprobante="FAC",
    cliente: str | None = "Cliente",
    origen="CARNES",
    sucursal: str | None = "01",
    tipo="A",
    numero: str | None = "0001",
    importe=100,
    cajas=1,
    kilos=10,
    estado="procesado",
    codigo=None,
):
    db.session.add(
        StgSabiogoVentas(
            fecha=fecha,
            origen=origen,
            codigo=codigo or f"{origen}-{sucursal}-{tipo}-{numero}-{fecha}-{cliente}",
            comprobante=comprobante,
            nro_comprob=numero,
            vendedor=vendedor,
            cliente=cliente,
            sucursal=sucursal,
            tipo=tipo,
            subtot=importe,
            cajas=cajas,
            kilos=kilos,
            estado=estado,
        )
    )


def consultar(client, desde="2024-06-01", hasta="2024-06-30"):
    return client.get(
        f"/api/comercial/salon?fecha_desde={desde}&fecha_hasta={hasta}"
    )


def test_solo_fac_y_vendedor_salon_con_alias_normalizado(client, app):
    with app.app_context():
        agregar_factura(vendedor="  sAlón   ", numero="fac-salon")
        agregar_factura(vendedor="SALÓN", comprobante="PRE", numero="pre")
        agregar_factura(vendedor="Otro vendedor", numero="otro")
        agregar_factura(vendedor="SALÓN", estado="pendiente", numero="pendiente")
        db.session.commit()

        fila = StgSabiogoVentas.query.filter_by(nro_comprob="fac-salon").one()
        texto_original = fila.vendedor

    response = consultar(client)
    assert response.status_code == 200
    result = response.get_json()
    assert len(result["tickets"]) == 1
    assert result["tickets"][0]["numero"] == "fac-salon"
    assert result["tickets"][0]["vendedor"] == "Salón"
    assert result["kpis"]["tickets"]["actual"] == 1

    with app.app_context():
        assert StgSabiogoVentas.query.filter_by(nro_comprob="fac-salon").one().vendedor == texto_original


def test_ticket_usa_clave_completa_y_suma_lineas_sin_contarlas_como_tickets(client, app):
    with app.app_context():
        agregar_factura(numero="100", importe=40, cajas=1, kilos=4, cliente="Cliente A", codigo="linea-1")
        agregar_factura(numero="100", importe=60, cajas=2, kilos=6, cliente="Cliente A", codigo="linea-2")
        agregar_factura(numero="100", origen="LACTEOS", importe=10, codigo="otro-origen")
        agregar_factura(numero="100", sucursal="02", importe=20, codigo="otra-sucursal")
        agregar_factura(numero="100", tipo="B", importe=30, codigo="otro-tipo")
        agregar_factura(numero="100", fecha=date(2024, 6, 11), importe=50, codigo="otra-fecha")
        agregar_factura(numero="100", sucursal=None, codigo="sin-sucursal")
        agregar_factura(numero=None, codigo="sin-numero")
        db.session.commit()

    result = consultar(client).get_json()
    assert len(result["tickets"]) == 5
    assert {ticket["numero"] for ticket in result["tickets"]} == {"100"}
    assert {
        (ticket["origen"], ticket["sucursal"], ticket["tipo"], ticket["fecha"])
        for ticket in result["tickets"]
    } == {
        ("CARNES", "01", "A", "2024-06-10"),
        ("LACTEOS", "01", "A", "2024-06-10"),
        ("CARNES", "02", "A", "2024-06-10"),
        ("CARNES", "01", "B", "2024-06-10"),
        ("CARNES", "01", "A", "2024-06-11"),
    }
    original = next(
        ticket
        for ticket in result["tickets"]
        if (ticket["origen"], ticket["sucursal"], ticket["tipo"], ticket["fecha"])
        == ("CARNES", "01", "A", "2024-06-10")
    )
    assert original["importe"] == pytest.approx(100)
    assert original["cajas"] == pytest.approx(3)
    assert original["kilos"] == pytest.approx(10)
    assert result["kpis"]["tickets"]["actual"] == 5


def test_cliente_con_nombre_y_consumidor_final_sin_nombre_inventado(client, app):
    with app.app_context():
        agregar_factura(numero="nombre", cliente="Comercio del Centro")
        agregar_factura(numero="final", cliente="CONSUMIDOR FINAL")
        agregar_factura(numero="vacio", cliente=None)
        db.session.commit()

    result = consultar(client).get_json()
    por_numero = {ticket["numero"]: ticket["cliente"] for ticket in result["tickets"]}
    assert por_numero == {
        "nombre": "Comercio del Centro",
        "final": "Consumidor final",
        "vacio": "Consumidor final",
    }


def test_compara_con_ventana_anterior_de_igual_largo(client, app):
    with app.app_context():
        agregar_factura(fecha=date(2024, 6, 7), numero="previo", importe=20, cajas=2, kilos=8)
        agregar_factura(fecha=date(2024, 6, 10), numero="actual", importe=60, cajas=3, kilos=15)
        db.session.commit()

    result = consultar(client, "2024-06-10", "2024-06-12").get_json()
    assert (result["desde_anterior"], result["hasta_anterior"]) == ("2024-06-07", "2024-06-09")
    assert result["kpis"]["importe"]["actual"] == pytest.approx(60)
    assert result["kpis"]["importe"]["anterior"] == pytest.approx(20)
    assert result["kpis"]["importe"]["variacion_pct"] == pytest.approx(200)
    assert [ticket["numero"] for ticket in result["tickets"]] == ["actual"]


def test_periodo_default_es_mes_actual_hasta_hoy(client):
    hoy = today_local_date()
    result = client.get("/api/comercial/salon").get_json()
    assert result["desde"] == hoy.replace(day=1).isoformat()
    assert result["hasta"] == hoy.isoformat()


def test_pantalla_y_acceso_en_paneles_estrategicos(client):
    response = client.get("/comercial/salon")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Tablero Salón" in html
    assert 'href="/comercial/salon"' in html
    assert html.index('href="/dashboard-comercial"') < html.index('href="/comercial/salon"')
    assert "tablero_salon.js" in html
    assert "name=\"fecha_desde\"" in html
    assert "name=\"fecha_hasta\"" in html
