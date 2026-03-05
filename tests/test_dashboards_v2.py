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
def app():
    # Config lee env al importar; forzamos atributos en runtime para tests
    Config.SECRET_KEY = "test-secret"
    Config.ADMIN_PASSWORD = "admin"
    Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    Config.WTF_CSRF_ENABLED = False
    Config.RATELIMIT_ENABLED = False
    Config.CORS_ORIGINS = ["http://localhost:5173"]

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
    assert "flujo" in data["series"] and "instrumentos" in data["series"]


def test_dashboard_comercial_v2_ok(client, seed_minimal):
    resp = client.get("/api/dashboard-comercial-v2?period=30")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kpis" in data and "series" in data
    assert "leads_por_estado" in data["series"]


def test_panel_ejecutivo_v2_ok(client, seed_minimal):
    resp = client.get("/api/panel-ejecutivo-v2?period=ytd")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "top_clientes" in data
    assert "instrumentos" in data
    assert "friar" in data
