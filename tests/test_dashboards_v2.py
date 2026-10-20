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


def test_panel_ejecutivo_v2_ok(client, seed_minimal):
    resp = client.get("/api/panel-ejecutivo-v2?period=ytd")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "top_clientes" in data
    assert "instrumentos" in data
    assert "friar" in data
