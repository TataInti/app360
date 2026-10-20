import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal

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


def test_dashboard_comercial_v2_filtra_por_cliente(client, app, seed_minimal):
    with app.app_context():
        db.session.add_all(
            [
                StgSabiogoVentas(
                    fecha=date.today() - timedelta(days=5),
                    origen="CARNES",
                    codigo="PRE-A",
                    producto="Prod A",
                    comprobante="PRE",
                    cliente="Cliente Filtro",
                    vendedor="Vendedor A",
                    subtot=250.0,
                    estado="procesado",
                ),
                StgSabiogoVentas(
                    fecha=date.today() - timedelta(days=5),
                    origen="CARNES",
                    codigo="PRE-B",
                    producto="Prod B",
                    comprobante="PRE",
                    cliente="Cliente Otro",
                    vendedor="Vendedor B",
                    subtot=999.0,
                    estado="procesado",
                ),
            ]
        )
        db.session.commit()

    resp = client.get("/api/dashboard-comercial-v2?period=30&cliente=Cliente%20Filtro")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kpis"]["ventas_pre_periodo_count"] == 1
    assert data["kpis"]["ventas_pre_periodo_total"] == 250.0
    assert data["series"]["pre_por_cliente"] == [["Cliente Filtro", 1, 250.0]]

    filtros_resp = client.get("/api/dashboard-comercial/filtros?empresa=CARNES")
    assert filtros_resp.status_code == 200
    filtros = filtros_resp.get_json()
    assert "Cliente Filtro" in filtros["clientes"]
    assert "Cliente Otro" in filtros["clientes"]


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
    mix_productos = {row["producto"] for row in resp.get_json()["mix_global"]}
    assert "Producto corte PRE" in mix_productos
    assert "Producto corte FAC" not in mix_productos


def test_panel_ejecutivo_v2_ok(client, seed_minimal):
    resp = client.get("/api/panel-ejecutivo-v2?period=ytd")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "top_clientes" in data
    assert "instrumentos" in data
    assert "friar" in data
