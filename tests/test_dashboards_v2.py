import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app import create_app
from config import Config
from models import db
from models.core.user import User
from models.tesoreria import (
    InstrumentoPago,
    MovimientoCaja,
    CuentaCorrienteFriar,
    PagoFriar,
)
from models.gastos import Proveedor
from models.hr.employee import Employee
from models.rrhh import Adelanto
from models.sabiogo.staging import StgSabiogoVentas


@pytest.fixture
def app(monkeypatch):
    # Config lee env al importar; forzamos atributos en runtime para tests
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
def seed_minimal(app):
    with app.app_context():
        user = User(username="admin", role="admin", active=True)
        user.set_password("admin")
        db.session.add(user)

        inst = InstrumentoPago(nombre="efectivo", descripcion="", activo=True)
        db.session.add(inst)
        db.session.flush()

        # Movimientos últimos 10 días
        now = datetime.utcnow()
        movs = [
            MovimientoCaja(
                fecha_hora=now - timedelta(days=2),
                tipo="ingreso",
                monto=Decimal("150.00"),
                descripcion="cobro",
                instrumento_id=inst.id,
                usuario_id=user.id,
            ),
            MovimientoCaja(
                fecha_hora=now - timedelta(days=1),
                tipo="egreso",
                monto=Decimal("70.00"),
                descripcion="pago",
                instrumento_id=inst.id,
                usuario_id=user.id,
            ),
        ]
        db.session.add_all(movs)

        # RRHH
        emp = Employee(first_name="Ana", last_name="Pérez")
        db.session.add(emp)
        db.session.flush()
        adel = Adelanto(
            empleado_id=emp.id,
            tipo="prestamo",
            monto=Decimal("100.00"),
            concepto="préstamo",
            aprobado=True,
            liquidado=False,
            cantidad_cuotas=5,
            cuotas_pagadas=1,
            interes_porcentaje=Decimal("0"),
        )
        db.session.add(adel)

        # Friar
        prov = Proveedor(nombre="Friar")
        db.session.add(prov)
        db.session.flush()
        cuenta = CuentaCorrienteFriar(proveedor_id=prov.id, saldo_inicial=Decimal("1000.00"))
        db.session.add(cuenta)
        db.session.flush()
        pago = PagoFriar(
            cuenta_corriente_id=cuenta.id,
            fecha=now,
            monto=Decimal("100.00"),
            instrumento_id=inst.id,
            descripcion="pago friar",
            usuario_id=user.id,
        )
        db.session.add(pago)

        # SabioGo ventas (top clientes)
        venta = StgSabiogoVentas(
            fecha=date.today() - timedelta(days=5),
            origen="LEGACY",
            codigo="X",
            producto="Prod",
            cliente="Cliente A",
            sucursal="Sucursal",
            subtot=120.0,
            neto=100.0,
            iva=20.0,
            estado="procesado",
        )
        db.session.add(venta)

        db.session.commit()


def test_dashboard_financiero_ok(client, seed_minimal):
    resp = client.get("/api/dashboard-financiero?period=7")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kpis" in data and "series" in data
    assert data["kpis"]["period"] == "7"
    assert "pre_acumulado" in data["kpis"]
    assert "fac_acumulado" in data["kpis"]
    assert "pre_fac_saldo" in data["kpis"]
    assert "flujo" in data["series"] and "instrumentos" in data["series"]


def test_dashboard_comercial_v2_ok(client, seed_minimal):
    resp = client.get("/api/dashboard-comercial-v2?period=30")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kpis" in data and "series" in data
    assert "ventas_pre_periodo_total" in data["kpis"]
    assert "ventas_pre_periodo_count" in data["kpis"]
    assert "leads_por_estado" in data["series"]
    assert "pre_detalle" in data["series"]
    assert "pre_por_vendedor" in data["series"]
    assert "pre_por_cliente" in data["series"]
    assert "pre_por_producto" in data["series"]


def test_dashboard_comercial_v2_pre_analytics(client, app):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2024, 1, 1),
                    origen="CARNES",
                    codigo="PRE-001",
                    producto="Producto PRE",
                    cliente="Cliente PRE",
                    vendedor="Vendedor PRE",
                    comprobante="PRE",
                    nro_comprob="PRE-1001",
                    cajas=2.5,
                    kilos=25.0,
                    subtot=100.0,
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 11),
                    origen="CARNES",
                    codigo="PRE-002",
                    producto="Producto PRE",
                    cliente="Cliente PRE",
                    vendedor="Vendedor PRE",
                    comprobante="PRE",
                    nro_comprob="PRE-1002",
                    cajas=3.5,
                    kilos=35.0,
                    subtot=300.0,
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2024, 1, 12),
                    origen="CARNES",
                    codigo="PRE-003",
                    producto="Producto Otro",
                    cliente="Cliente Otro",
                    vendedor="Otro Vendedor",
                    comprobante="PRE",
                    nro_comprob="PRE-1003",
                    cajas=1.0,
                    kilos=10.0,
                    subtot=600.0,
                    estado="procesado",
                ),
            ]
        )
        db.session.commit()

    fechas = "fecha_desde=2024-01-01&fecha_hasta=2024-01-31"
    resp = client.get(f"/api/dashboard-comercial-v2?{fechas}&producto=Producto%20PRE")
    assert resp.status_code == 200
    data = resp.get_json()
    cliente = data["series"]["pre_por_cliente"][0]
    assert isinstance(cliente, dict)
    assert cliente["nombre"] == "Cliente PRE"
    assert cliente["plata"] == 400.0
    assert cliente["cajas"] == 6.0
    assert cliente["kilos"] == 60.0
    assert cliente["compras"] == 2
    assert cliente["pct"] == 100.0

    resp = client.get(
        f"/api/dashboard-comercial-v2?{fechas}&producto=Producto%20PRE&cliente=Cliente%20PRE"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    analisis = data["cliente_analisis"]
    assert analisis["compras"] == 2
    assert analisis["frecuencia_dias"] is not None

    all_vendors = client.get(f"/api/dashboard-comercial-v2?{fechas}").get_json()
    share_company = next(
        row["pct"] for row in all_vendors["series"]["pre_por_producto"]
        if row["nombre"] == "Producto PRE"
    )
    selected_vendor = client.get(
        f"/api/dashboard-comercial-v2?{fechas}&vendedor=Vendedor%20PRE"
    ).get_json()
    share_vendor = next(
        row["pct"] for row in selected_vendor["series"]["pre_por_producto"]
        if row["nombre"] == "Producto PRE"
    )
    assert share_company == 40.0
    assert share_vendor == 100.0


def test_dashboard_comercial_analysis_mix_only_pedidos_pre(client, app):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date(2000, 2, 15),
                    origen="CARNES",
                    codigo="CORTE-PRE",
                    producto="Producto corte PRE",
                    cliente="Cliente corte",
                    cajas=3.0,
                    subtot=150.0,
                    comprobante="PRE",
                    nro_comprob="CORTE-1001",
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date(2000, 2, 15),
                    origen="CARNES",
                    codigo="CORTE-FAC",
                    producto="Producto corte FAC",
                    cliente="Cliente corte",
                    cajas=7.0,
                    subtot=350.0,
                    comprobante="FAC",
                    nro_comprob="CORTE-1002",
                    estado="procesado",
                ),
            ]
        )
        for indice in range(1, 12):
            db.session.add(
                StgSabiogoVentas(
                    fecha=date(2000, 2, 16),
                    origen="CARNES",
                    codigo=f"CORTE-EXTRA-{indice}",
                    producto=f"Producto extra {indice}",
                    cliente="Cliente corte",
                    vendedor="Vendedor corte",
                    cajas=1.0,
                    subtot=10.0,
                    comprobante="PRE",
                    nro_comprob=f"CORTE-EXTRA-{indice}",
                    estado="procesado",
                )
            )
        db.session.commit()

        # La consulta de producción usa PostgreSQL date_trunc; se registra para
        # este rango histórico de SQLite, sin filas en la serie semestral.
        def sqlite_date_trunc(unit, value):
            if unit == "month" and value:
                return f"{str(value)[:7]}-01 00:00:00"
            return None

        connection = db.engine.raw_connection()
        connection.create_function("date_trunc", 2, sqlite_date_trunc)
        connection.close()

    fechas = "fecha_desde=2000-02-01&fecha_hasta=2000-02-29"
    resp = client.get(f"/api/dashboard-comercial/analisis?tipo=producto&{fechas}")
    assert resp.status_code == 200
    analisis_productos = {row["nombre"] for row in resp.get_json()["top15"]}
    assert "Producto corte PRE" in analisis_productos
    assert "Producto corte FAC" not in analisis_productos

    resp = client.get(f"/api/dashboard-comercial/mix?{fechas}")
    assert resp.status_code == 200
    mix_data = resp.get_json()
    assert "clientes_disponibles" not in mix_data
    mix_global = mix_data["mix_global"]
    mix_productos = {row["producto"] for row in mix_global}
    assert "Producto corte PRE" in mix_productos
    assert "Producto corte FAC" not in mix_productos
    producto_pre = next(row for row in mix_global if row["producto"] == "Producto corte PRE")
    otros = next(row for row in mix_global if row["producto"] == "Otros")
    assert producto_pre["pct"] == 21.4
    assert otros["cajas"] == 2.0
    assert otros["pct"] == 14.3


def test_dashboard_comercial_seguimiento_clientes_pre(client, app):
    hoy = datetime.now(ZoneInfo("America/Argentina/Tucuman")).date()

    with app.app_context():
        def agregar_venta(
            fecha, vendedor, cliente, producto, subtot, comprobante, nro_comprob, codigo
        ):
            db.session.add(
                StgSabiogoVentas(
                    fecha=fecha,
                    origen="CARNES",
                    codigo=codigo,
                    producto=producto,
                    cliente=cliente,
                    vendedor=vendedor,
                    subtot=subtot,
                    comprobante=comprobante,
                    nro_comprob=nro_comprob,
                    estado="procesado",
                )
            )

        agregar_venta(
            hoy - timedelta(days=2), "Vendedor A", "Cliente Nuevo", "Producto A", 100.0,
            "PRE", "A-NEW-1", "A-NEW-1A"
        )
        agregar_venta(
            hoy - timedelta(days=2), "Vendedor A", "Cliente Nuevo", "Producto A", 50.0,
            "PRE", "A-NEW-1", "A-NEW-1B"
        )
        agregar_venta(
            hoy - timedelta(days=90), "Vendedor A", "Cliente Viejo", "Producto histórico", 75.0,
            "PRE", "A-OLD-1", "A-OLD-1"
        )
        agregar_venta(
            hoy - timedelta(days=10), "Vendedor A", "Cliente Viejo", "Producto B", 150.0,
            "PRE", "A-OLD-2", "A-OLD-2"
        )
        agregar_venta(
            hoy - timedelta(days=40), "Vendedor A", "Cliente Inactivo", "Producto C", 500.0,
            "PRE", "A-INACTIVE-1", "A-INACTIVE-1"
        )
        agregar_venta(
            hoy - timedelta(days=2), "Vendedor A", "Cliente Solo FAC", "Producto FAC", 9999.0,
            "FAC", "A-FAC-1", "A-FAC-1"
        )
        agregar_venta(
            hoy - timedelta(days=1), "Vendedor B", "Cliente Vendedor B", "Producto B2", 60.0,
            "PRE", "B-PRE-1", "B-PRE-1"
        )
        db.session.commit()

    resp = client.get("/api/dashboard-comercial/seguimiento")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["desde"] == (hoy - timedelta(days=29)).isoformat()
    assert data["hasta"] == hoy.isoformat()
    assert len(data["vendedores"]) == 2

    vendedor = next(item for item in data["vendedores"] if item["nombre"] == "Vendedor A")
    assert vendedor["activos"] == 2
    assert vendedor["total"] == 3
    assert [item["nombre"] for item in vendedor["nuevos"]] == ["Cliente Nuevo"]
    assert "Cliente Solo FAC" not in {item["nombre"] for item in vendedor["lista"]}
    assert "Producto FAC" not in {item["nombre"] for item in vendedor["productos"]}
    producto = next(item for item in vendedor["productos"] if item["nombre"] == "Producto A")
    assert producto["pct"] == 50.0
    cliente_viejo = next(item for item in vendedor["ultimas"] if item["nombre"] == "Cliente Viejo")
    assert cliente_viejo["fecha"] is not None
    assert cliente_viejo["fecha"] == (hoy - timedelta(days=10)).isoformat()
    vendedor_b = next(item for item in data["vendedores"] if item["nombre"] == "Vendedor B")
    assert vendedor_b["activos"] == 1
    assert vendedor_b["canasta_flaca"] == []


def test_dashboard_comercial_seguimiento_oportunidades(client, app):
    hoy = datetime.now(ZoneInfo("America/Argentina/Tucuman")).date()

    with app.app_context():
        def agregar_venta(fecha, cliente, producto, subtot, nro_comprob, codigo, comprobante="PRE"):
            db.session.add(
                StgSabiogoVentas(
                    fecha=fecha,
                    origen="CARNES",
                    codigo=codigo,
                    producto=producto,
                    cliente=cliente,
                    vendedor="Vendedor Oportunidades",
                    subtot=subtot,
                    comprobante=comprobante,
                    nro_comprob=nro_comprob,
                    estado="procesado",
                )
            )

        anterior = hoy - timedelta(days=40)
        reciente = hoy - timedelta(days=10)
        agregar_venta(anterior, "Cliente Caído", "Producto Caído", 240.0, "CAIDO-1", "CAIDO-1")
        agregar_venta(anterior, "Cliente En Baja", "Producto Antiguo", 200.0, "BAJA-ANT", "BAJA-ANT")
        agregar_venta(reciente, "Cliente En Baja", "Producto A", 100.0, "BAJA-ACT-1", "BAJA-ACT-1")
        agregar_venta(reciente, "Cliente En Baja", "Producto B", 50.0, "BAJA-ACT-2", "BAJA-ACT-2")
        agregar_venta(hoy - timedelta(days=1), "Cliente Canasta", "Producto Único", 50.0, "CANASTA-1", "CANASTA-1")
        for indice in range(1, 5):
            agregar_venta(
                hoy - timedelta(days=1),
                "Cliente Promedio",
                f"Producto {indice}",
                20.0,
                "PROMEDIO-1",
                f"PROMEDIO-{indice}",
            )
        agregar_venta(
            hoy - timedelta(days=1),
            "Cliente Caído",
            "Producto FAC",
            5000.0,
            "FAC-CAIDO-1",
            "FAC-CAIDO-1",
            comprobante="FAC",
        )
        agregar_venta(
            hoy - timedelta(days=1),
            "Cliente Solo FAC",
            "Producto FAC",
            7000.0,
            "FAC-SOLO-1",
            "FAC-SOLO-1",
            comprobante="FAC",
        )
        db.session.commit()

    resp = client.get("/api/dashboard-comercial/seguimiento")
    assert resp.status_code == 200
    data = resp.get_json()
    vendedor = next(
        item for item in data["vendedores"] if item["nombre"] == "Vendedor Oportunidades"
    )

    assert len(vendedor["caidos"]) == 1
    assert vendedor["caidos"][0] == {
        "nombre": "Cliente Caído",
        "dias": 40,
        "plata_anterior": 240.0,
    }
    assert len(vendedor["baja"]) == 1
    assert vendedor["baja"][0] == {
        "nombre": "Cliente En Baja",
        "plata_actual": 150.0,
        "plata_anterior": 200.0,
        "variacion_pct": -25.0,
    }
    assert len(vendedor["canasta_flaca"]) == 1
    assert vendedor["canasta_flaca"][0] == {
        "nombre": "Cliente Canasta",
        "productos": 1,
        "promedio": 2.3,
    }
    assert "Cliente Solo FAC" not in {item["nombre"] for item in vendedor["lista"]}


def test_dashboard_comercial_seguimiento_sin_nro_comprob_y_fechas(client, app):
    with app.app_context():
        ventas = [
            (date(2024, 1, 5), "Cliente Existente", "A-1", 10.0),
            (date(2024, 1, 15), "Cliente Existente", "A-2", 20.0),
            (date(2024, 1, 4), "Cliente Antiguo", "B-1", 30.0),
            (date(2023, 12, 15), "Cliente Fuera Ventana", "D-1", 15.0),
            (date(2024, 1, 19), "Cliente Nuevo", "C-1", 40.0),
        ]
        for fecha, cliente, codigo, subtot in ventas:
            db.session.add(
                StgSabiogoVentas(
                    fecha=fecha,
                    origen="CARNES",
                    codigo=codigo,
                    producto="Producto demo",
                    cliente=cliente,
                    vendedor="Vendedor demo",
                    subtot=subtot,
                    comprobante="PRE",
                    nro_comprob=None,
                    estado="procesado",
                )
            )
        db.session.commit()

    resp = client.get(
        "/api/dashboard-comercial/seguimiento?fecha_desde=2024-01-10"
        "&fecha_hasta=2024-01-20&empresa=CARNES&vendedor=Vendedor%20demo"
        "&producto=Producto%20demo"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["desde"] == "2024-01-10"
    assert data["hasta"] == "2024-01-20"
    assert len(data["vendedores"]) == 1
    vendedor = data["vendedores"][0]
    assert vendedor["total"] == 4
    assert vendedor["activos"] == 2
    assert [cliente["nombre"] for cliente in vendedor["nuevos"]] == ["Cliente Nuevo"]
    assert vendedor["caidos"] == [
        {"nombre": "Cliente Antiguo", "dias": 16, "plata_anterior": 30.0}
    ]

    filtrado_cliente = client.get(
        "/api/dashboard-comercial/seguimiento?fecha_desde=2024-01-10"
        "&fecha_hasta=2024-01-20&empresa=CARNES&vendedor=Vendedor%20demo"
        "&cliente=Cliente%20Nuevo&producto=Producto%20demo"
    ).get_json()["vendedores"]
    assert len(filtrado_cliente) == 1
    assert filtrado_cliente[0]["lista"] == [{"nombre": "Cliente Nuevo"}]


def test_dashboard_comercial_seguimiento_sin_clientes_es_vacio(client):
    resp = client.get("/api/dashboard-comercial/seguimiento")

    assert resp.status_code == 200
    assert resp.get_json()["vendedores"] == []


def test_panel_ejecutivo_v2_ok(client, seed_minimal):
    resp = client.get("/api/panel-ejecutivo-v2?period=ytd")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "top_clientes" in data
    assert "instrumentos" in data
    assert "friar" in data
