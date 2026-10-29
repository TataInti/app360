from datetime import date, datetime

import pytest

from app import create_app
from config import Config
from models import db
from models.comercial import ComercialClienteCriterio, ComercialObjetivo, ComercialVendedor
from models.sabiogo.staging import StgSabiogoVentas
from services.comercial_pre import calcular_resumen_pre
from services.vendedores_comerciales import seed_vendedores_comerciales


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
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def pre_aliases(app):
    with app.app_context():
        seed_vendedores_comerciales()
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="PRE-001",
                    producto="Producto A",
                    cliente="Cliente compartido",
                    vendedor="KALJA BENJAMIN",
                    comprobante="PRE",
                    nro_comprob="100",
                    cajas=1.0,
                    kilos=10.0,
                    subtot=100.0,
                    fecha_import=datetime(2026, 10, 18, 9, 0),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="PRE-002",
                    producto="Producto A",
                    cliente="Cliente compartido",
                    vendedor="BENJAMIN KALJA",
                    comprobante="PRE",
                    nro_comprob="100",
                    cajas=0.5,
                    kilos=5.0,
                    subtot=50.0,
                    fecha_import=datetime(2026, 10, 18, 10, 0),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="PRE-003",
                    producto="Producto A",
                    cliente="Cliente compartido",
                    vendedor="KALJA BENJAMIN",
                    comprobante="PRE",
                    nro_comprob="100",
                    cajas=0.25,
                    kilos=2.5,
                    subtot=25.0,
                    fecha_import=datetime(2026, 10, 18, 11, 0),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen="CARNES",
                    sucursal="Norte",
                    tipo="A",
                    codigo="PRE-004",
                    producto="Producto B",
                    cliente="Cliente compartido",
                    vendedor="BENJAMIN KALJA",
                    comprobante="PRE",
                    nro_comprob="100",
                    cajas=0.5,
                    kilos=5.0,
                    subtot=25.0,
                    fecha_import=datetime(2026, 10, 18, 12, 0),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="PRE-005",
                    producto="Producto A",
                    cliente="Cliente compartido",
                    vendedor="BENJAMIN KALJA",
                    comprobante="PRE",
                    nro_comprob=None,
                    cajas=2.0,
                    kilos=20.0,
                    subtot=40.0,
                    fecha_import=datetime(2026, 10, 18, 13, 0),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 10),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="PRE-006",
                    producto="Producto B",
                    cliente="Cliente compartido",
                    vendedor="KALJA BENJAMIN",
                    comprobante="PRE",
                    nro_comprob="102",
                    cajas=1.0,
                    kilos=10.0,
                    subtot=-10.0,
                    fecha_import=datetime(2026, 10, 19, 15, 30),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 31),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="FAC-001",
                    producto="Producto excluido",
                    cliente="Cliente compartido",
                    vendedor="KALJA BENJAMIN",
                    comprobante="FAC",
                    nro_comprob="901",
                    subtot=999.0,
                    fecha_import=datetime(2027, 1, 1, 0, 0),
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 31),
                    origen="CARNES",
                    sucursal="Central",
                    tipo="A",
                    codigo="PENDING-001",
                    producto="Producto excluido",
                    cliente="Cliente compartido",
                    vendedor="KALJA BENJAMIN",
                    comprobante="PRE",
                    nro_comprob="902",
                    subtot=888.0,
                    fecha_import=datetime(2027, 1, 2, 0, 0),
                    estado="pendiente",
                ),
            ]
        )
        db.session.commit()
    return app


def test_aliases_de_benjamin_se_suman_en_un_vendedor_y_cliente(app, pre_aliases):
    with app.app_context():
        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        assert len(resumen["por_vendedor"]) == 1
        vendedor = resumen["por_vendedor"][0]
        assert vendedor["nombre"] == "Benjamín Kalja"
        assert vendedor["plata"] == 230.0
        assert vendedor["cajas"] == 5.25
        assert vendedor["kilos"] == 52.5
        assert resumen["clientes_compradores"] == 1
        assert vendedor["clientes"] == 1

        originales = {
            fila.vendedor
            for fila in db.session.query(StgSabiogoVentas).all()
        }
        assert originales == {"KALJA BENJAMIN", "BENJAMIN KALJA"}


def test_pedidos_usan_origen_sucursal_tipo_numero_y_fecha(app, pre_aliases):
    with app.app_context():
        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        assert resumen["pedidos_identificados"] == 3
        assert resumen["por_vendedor"][0]["compras"] == 3
        assert resumen["importe_pedidos_identificados"] == 190.0


def test_linea_sin_numero_no_cambia_ticket_y_se_cuenta_aparte(app, pre_aliases):
    with app.app_context():
        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        assert resumen["lineas_sin_numero"] == 1
        assert resumen["por_vendedor"][0]["lineas_sin_numero"] == 1
        assert resumen["ticket_promedio"] == pytest.approx(190.0 / 3)


def test_subtotal_negativo_y_fechas_de_venta_e_importacion_separadas(app, pre_aliases):
    with app.app_context():
        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        assert resumen["importe_pre"] == 230.0
        assert resumen["por_fecha"][-1]["monto"] == -10.0
        assert resumen["fecha_maxima_pre"] == "2024-01-10"
        assert resumen["ultima_importacion"] == "2026-10-19T15:30:00"


def test_ambas_series_api_agrupan_por_nombre_resuelto(client, app, pre_aliases):
    fecha_desde = "2024-01-01"
    fecha_hasta = "2024-01-31"
    response = client.get(
        "/api/dashboard-comercial-v2?fecha_desde="
        f"{fecha_desde}&fecha_hasta={fecha_hasta}"
    )

    assert response.status_code == 200
    data = response.get_json()
    vendedores = data["series"]["pre_por_vendedor"]
    assert len(vendedores) == 1
    assert vendedores[0]["nombre"] == "Benjamín Kalja"
    assert vendedores[0]["plata"] == 230.0
    assert data["kpis"]["ventas_pre_periodo_count"] == 3
    assert data["kpis"]["ventas_pre_ticket_promedio"] == pytest.approx(190.0 / 3)
    assert data["kpis"]["ventas_pre_lineas_sin_numero"] == 1
    assert data["kpis"]["fecha_maxima_pre"] == "2024-01-10"
    assert data["kpis"]["ultima_importacion_pre"] == "2026-10-19T15:30:00"

    filtrado = client.get(
        "/api/dashboard-comercial-v2?fecha_desde=2024-01-01"
        "&fecha_hasta=2024-01-31&vendedor=BENJAMIN%20KALJA"
    ).get_json()
    assert filtrado["series"]["pre_por_vendedor"][0]["nombre"] == "Benjamín Kalja"
    assert filtrado["kpis"]["ventas_pre_periodo_total"] == 230.0

    seguimiento = client.get("/api/dashboard-comercial/seguimiento").get_json()
    assert len(seguimiento["vendedores"]) == 1
    vendedor = seguimiento["vendedores"][0]
    assert vendedor["nombre"] == "Benjamín Kalja"
    assert vendedor["lista"] == [{"nombre": "Cliente compartido"}]

    filtro_alias = client.get(
        "/api/dashboard-comercial/seguimiento?vendedor=KALJA%20BENJAMIN"
    ).get_json()
    assert len(filtro_alias["vendedores"]) == 1
    assert filtro_alias["vendedores"][0]["nombre"] == "Benjamín Kalja"


def test_ticket_es_nulo_si_no_hay_pedidos_identificados(app):
    with app.app_context():
        db.session.add(
            StgSabiogoVentas(
                fecha=date(2024, 1, 5),
                origen="CARNES",
                sucursal="Central",
                tipo="A",
                codigo="PRE-SIN-NUMERO",
                producto="Producto A",
                cliente="Cliente sin número",
                vendedor="Vendedor sin alias",
                comprobante="PRE",
                nro_comprob="   ",
                cajas=1.0,
                kilos=10.0,
                subtot=12.5,
                fecha_import=datetime(2026, 10, 19, 9, 0),
                estado="procesado",
            )
        )
        db.session.commit()

        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        assert resumen["importe_pre"] == 12.5
        assert resumen["pedidos_identificados"] == 0
        assert resumen["lineas_sin_numero"] == 1
        assert resumen["ticket_promedio"] is None


def test_criterio_fac_sustituye_pre_solo_para_cliente_marcado(client, app, pre_aliases):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2024, 1, 15), origen="CARNES", sucursal="Central", tipo="A",
                    codigo="PRE-NO-MARCADO", producto="Producto C", cliente="Cliente sin marca",
                    vendedor="KALJA BENJAMIN", comprobante="PRE", nro_comprob="201",
                    cajas=1, kilos=10, subtot=7, estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 15), origen="CARNES", sucursal="Central", tipo="A",
                    codigo="FAC-NO-MARCADO", producto="Producto C", cliente="Cliente sin marca",
                    vendedor="KALJA BENJAMIN", comprobante="FAC", nro_comprob="202",
                    cajas=1, kilos=10, subtot=1000, estado="procesado",
                ),
                ComercialClienteCriterio(
                    cliente="Cliente compartido", criterio="FAC", actualizado_por="admin"
                ),
            ]
        )
        vendedor = ComercialVendedor.query.filter_by(nombre_visible="Benjamín Kalja").one()
        db.session.add(
            ComercialObjetivo(
                vendedor_id=vendedor.id,
                empresa="CARNES",
                mes="2024-01",
                dimension_tipo="empresa",
                dimension_valor="CARNES",
                meta_importe=500,
            )
        )
        db.session.commit()

        default = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))
        panel = calcular_resumen_pre(
            date(2024, 1, 1), date(2024, 1, 31), criterio_clientes=True
        )

        assert default["importe_pre"] == 237.0
        assert panel["importe_pre"] == 1006.0
        por_cliente = {row["nombre"]: row["plata"] for row in panel["por_cliente"]}
        assert por_cliente["Cliente compartido"] == 999.0
        assert por_cliente["Cliente sin marca"] == 7.0

    equipo = client.get(
        "/api/dashboard-comercial/equipo?fecha_desde=2024-01-01"
        "&fecha_hasta=2024-01-31&empresa=CARNES"
    )
    assert equipo.status_code == 200
    assert equipo.get_json()["kpis"]["importe_pre"]["actual"] == 1006.0
    assert equipo.get_json()["cartera"]["importe_pre"] == 1006.0
    objetivo = next(
        row for row in equipo.get_json()["equipo"] if row["vendedor"] == "Benjamín Kalja"
    )
    assert objetivo["meta"] == 500.0
    assert objetivo["realizado"] == 237.0
    assert objetivo["cumplimiento"] == 0.474


def test_pantalla_criterios_guardado_selectivo_y_auditoria(client, app, pre_aliases):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2024, 1, 15), origen="CARNES", sucursal="Central", tipo="A",
                    codigo=f"CRIT-{cliente}", producto="Producto C", cliente=cliente,
                    vendedor="KALJA BENJAMIN", comprobante="PRE", nro_comprob=cliente,
                    cajas=1, kilos=10, subtot=7, estado="procesado",
                )
                for cliente in ("Cliente A", "Cliente B", "Cliente C")
            ]
        )
        db.session.add(
            StgSabiogoVentas(
                fecha=date(2024, 1, 15), origen="CARNES", sucursal="Central", tipo="A",
                codigo="PENDIENTE-CRITERIO", producto="Producto C", cliente="Cliente pendiente",
                vendedor="KALJA BENJAMIN", comprobante="PRE", nro_comprob="pendiente",
                cajas=1, kilos=10, subtot=7, estado="pendiente",
            )
        )
        db.session.add_all(
            [
                ComercialClienteCriterio(cliente="Cliente A", criterio="FAC", actualizado_por="antes"),
                ComercialClienteCriterio(cliente="Cliente C", criterio="FAC", actualizado_por="antes"),
            ]
        )
        db.session.commit()

    with client.session_transaction() as sess:
        sess["user"] = "Ciro"
        sess["user_id"] = 1
        sess["role"] = "sales"
    app.jinja_env.globals["csrf_token"] = lambda: "test-csrf"

    page = client.get("/ventas/criterio-clientes")
    assert page.status_code == 200
    assert "Usar presupuesto" in page.get_data(as_text=True)
    assert "Usar facturación" in page.get_data(as_text=True)

    listado = client.get("/ventas/criterio-clientes/datos").get_json()["clientes"]
    por_nombre = {row["cliente"]: row for row in listado}
    nombres = set(por_nombre)
    assert {"Cliente A", "Cliente B", "Cliente C"} <= nombres
    assert "Cliente pendiente" not in nombres
    assert por_nombre["Cliente B"]["criterio"] == "PRE"
    assert por_nombre["Cliente B"]["actualizado_por"] is None

    guardado = client.post(
        "/ventas/criterio-clientes/guardar",
        json={"clientes": ["Cliente A", "Cliente B"], "criterio": "PRE"},
    )
    assert guardado.status_code == 200
    guardado_uno = client.post(
        "/ventas/criterio-clientes/guardar",
        json={"clientes": ["Cliente B"], "criterio": "FAC"},
    )
    assert guardado_uno.status_code == 200

    with app.app_context():
        criterios = {
            fila.cliente: fila
            for fila in ComercialClienteCriterio.query.filter(
                ComercialClienteCriterio.cliente.in_(["Cliente A", "Cliente B", "Cliente C"])
            ).all()
        }
        assert criterios["Cliente A"].criterio == "PRE"
        assert criterios["Cliente B"].criterio == "FAC"
        assert criterios["Cliente C"].criterio == "FAC"
        assert criterios["Cliente B"].actualizado_por == "Ciro"
        assert criterios["Cliente B"].actualizado_en is not None


def test_alias_resuelto_con_mayusculas_y_espacios(app, pre_aliases):
    with app.app_context():
        db.session.add(
            StgSabiogoVentas(
                fecha=date(2024, 1, 20),
                origen="CARNES",
                sucursal="Central",
                tipo="A",
                codigo="PRE-ALIAS-ESPACIOS",
                producto="Producto C",
                cliente="Cliente alias",
                vendedor="  kalja   benjamin  ",
                comprobante="PRE",
                nro_comprob="301",
                cajas=2,
                kilos=20,
                subtot=55,
                estado="procesado",
            )
        )
        db.session.commit()

        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        vendedor = next(
            row for row in resumen["por_vendedor"] if row["nombre"] == "Benjamín Kalja"
        )
        assert vendedor["plata"] == 285.0
        assert vendedor["cajas"] == 7.25


def test_mismo_numero_en_origenes_distintos_son_tickets_distintos(app):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen=origen,
                    sucursal="Central",
                    tipo="A",
                    codigo=f"PRE-{origen}-MISMO-NUMERO",
                    producto="Producto A",
                    cliente="Cliente A",
                    vendedor="Vendedor sin catálogo",
                    comprobante="PRE",
                    nro_comprob="12345",
                    cajas=1,
                    kilos=10,
                    subtot=importe,
                    estado="procesado",
                )
                for origen, importe in (("CARNES", 10), ("LACTEOS", 20))
            ]
        )
        db.session.commit()

        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31))

        assert resumen["pedidos_identificados"] == 2
        assert resumen["importe_pedidos_identificados"] == 30.0
        assert resumen["ticket_promedio"] == 15.0
        vendedor = next(
            row
            for row in resumen["por_vendedor"]
            if row["nombre"] == "Vendedor sin catálogo"
        )
        assert vendedor["compras"] == 2


def test_limite_uno_recorta_dimensiones_sin_recortar_totales(app):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2024, 1, 5),
                    origen="CARNES",
                    codigo=f"PRE-LIMITE-{vendedor}",
                    producto=f"Producto {vendedor}",
                    cliente=f"Cliente {vendedor}",
                    vendedor=vendedor,
                    comprobante="PRE",
                    nro_comprob=vendedor,
                    cajas=1,
                    kilos=10,
                    subtot=importe,
                    estado="procesado",
                )
                for vendedor, importe in (("Vendedor A", 10), ("Vendedor B", 20))
            ]
        )
        db.session.commit()

        resumen = calcular_resumen_pre(date(2024, 1, 1), date(2024, 1, 31), limite=1)

        assert resumen["importe_pre"] == 30.0
        assert resumen["cajas"] == 2.0
        assert resumen["kilos"] == 20.0
        assert resumen["lineas_pre"] == 2
        assert [row["nombre"] for row in resumen["por_vendedor"]] == ["Vendedor B"]
        assert len(resumen["por_cliente"]) == len(resumen["por_producto"]) == 1