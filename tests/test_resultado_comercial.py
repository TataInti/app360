from datetime import date, datetime
from decimal import Decimal

import pytest

from app import create_app
from config import Config
from models import db
from models.core.user import User
from models.gastos import CategoriaGasto, CategoriaMovimientoAudit, Proveedor
from models.sabiogo.staging import StgSabiogoCompras, StgSabiogoVentas
from models.tesoreria import InstrumentoPago, MovimientoCaja
from services.resultado_comercial_service import ResultadoComercialService


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)
    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def scenario(app):
    with app.app_context():
        user = User(username="admin", role="admin", active=True)
        user.set_password("admin")
        instrument = InstrumentoPago(nombre="Efectivo", activo=True)
        provider = Proveedor(nombre="Proveedor", activo=True)
        concepts = {
            "iva": CategoriaGasto(
                nombre="EFECTIVO IVA",
                naturaleza="ingreso",
                incluye_resultado=True,
                activo=True,
            ),
            "salary": CategoriaGasto(
                nombre="SUELDOS",
                naturaleza="egreso",
                incluye_resultado=True,
                activo=True,
            ),
            "both": CategoriaGasto(
                nombre="FINANCIERA",
                naturaleza="ambos",
                incluye_resultado=True,
                activo=True,
            ),
            "neutral": CategoriaGasto(
                nombre="ADELANTO",
                naturaleza="egreso",
                incluye_resultado=False,
                activo=True,
            ),
            "conflict": CategoriaGasto(
                nombre="CONFLICTO",
                naturaleza="egreso",
                incluye_resultado=True,
                activo=True,
            ),
            "inactive": CategoriaGasto(
                nombre="HISTORICO",
                naturaleza="ingreso",
                incluye_resultado=True,
                activo=False,
            ),
            "pending": CategoriaGasto(
                nombre="PENDIENTE",
                naturaleza=None,
                incluye_resultado=False,
                activo=True,
            ),
        }
        db.session.add_all([user, instrument, provider, *concepts.values()])
        db.session.flush()

        common_sale = {
            "fecha": date(2026, 7, 15),
            "origen": "CARNES",
            "codigo": "P1",
            "producto": "Producto",
            "sucursal": "Central",
            "estado": "procesado",
        }
        db.session.add_all(
            [
                StgSabiogoVentas(
                    **common_sale,
                    comprobante="FAC",
                    cliente="Cliente A",
                    subtot=1000,
                    neto=1000,
                    iva=0,
                ),
                StgSabiogoVentas(
                    **{**common_sale, "codigo": "P2"},
                    comprobante="PRE",
                    cliente="Cliente B",
                    subtot=400,
                    neto=400,
                    iva=0,
                ),
                StgSabiogoCompras(
                    fecha=date(2026, 7, 15),
                    origen="CARNES",
                    codigo="C1",
                    producto="Mercadería",
                    subtot=300,
                    neto=300,
                    iva=0,
                    estado="procesado",
                ),
            ]
        )

        def movement(tipo, amount, concept=None, estado="activo"):
            return MovimientoCaja(
                fecha_hora=datetime(2026, 7, 15, 12),
                tipo=tipo,
                monto=Decimal(str(amount)),
                descripcion=f"{tipo} {amount}",
                estado=estado,
                instrumento_id=instrument.id,
                usuario_id=user.id,
                categoria_gasto_id=concept.id if concept else None,
            )

        db.session.add_all(
            [
                movement("ingreso", 100, concepts["iva"]),
                movement("egreso", 80, concepts["salary"]),
                movement("ingreso", 50, concepts["both"]),
                movement("egreso", 20, concepts["both"]),
                movement("egreso", 30, concepts["neutral"]),
                movement("ingreso", 40, concepts["conflict"]),
                movement("ingreso", 10, concepts["inactive"]),
                movement("egreso", 25),
                movement("egreso", 999, concepts["salary"], estado="anulado"),
            ]
        )
        db.session.commit()
        return {
            "user_id": user.id,
            "instrument_id": instrument.id,
            "provider_id": provider.id,
            "concept_ids": {key: value.id for key, value in concepts.items()},
        }


def login(client, user_id):
    with client.session_transaction() as flask_session:
        flask_session["user"] = "admin"
        flask_session["user_id"] = user_id
        flask_session["role"] = "admin"


def test_resultado_excluye_pre_y_aplica_conceptos_compatibles(app, scenario):
    with app.app_context():
        result = ResultadoComercialService().calcular(
            date(2026, 7, 1),
            date(2026, 7, 31),
            "CARNES",
        )
        kpis = result["kpis"]
        assert kpis["facturacion"] == 1000
        assert kpis["compras"] == 300
        assert kpis["ingresos_incluidos"] == 160
        assert kpis["egresos_incluidos"] == 100
        assert kpis["resultado_gestion"] == 760
        assert kpis["caja_neta"] == 45
        assert result["conceptos"]["conflictos"] == 1
        assert result["conceptos"]["pendientes"] == 1
        both_rows = [
            row for row in result["conceptos"]["desglose"]
            if row["concepto"] == "FINANCIERA"
        ]
        assert {row["tipo"] for row in both_rows} == {"ingreso", "egreso"}


def test_resultado_normaliza_fechas_datetime(app, scenario):
    with app.app_context():
        result = ResultadoComercialService().calcular(
            datetime(2026, 7, 1, 9, 30),
            datetime(2026, 7, 31, 18, 0),
            "CARNES",
        )
        assert result["periodo"] == {"desde": "2026-07-01", "hasta": "2026-07-31"}
        assert result["kpis"]["resultado_gestion"] == 760


def test_ejecutivo_y_bi_coinciden(client, scenario):
    params = "fecha_desde=2026-07-01&fecha_hasta=2026-07-31&empresa=CARNES"
    executive = client.get(f"/api/panel-ejecutivo-v2?{params}").get_json()
    commercial = client.get(f"/api/bi/dashboard?{params}").get_json()
    assert executive["kpis"]["resultado_gestion"] == commercial["kpis"]["resultado_gestion"] == 760
    assert executive["kpis"]["facturacion"] == commercial["kpis"]["facturacion"] == 1000
    assert executive["kpis"]["caja_neta"] == commercial["kpis"]["caja_neta"] == 45


def test_tesoreria_adapta_granularidad(client, scenario):
    response = client.get("/api/dashboard-financiero?period=6m")
    assert response.status_code == 200
    assert response.get_json()["series"]["flujo"]["granularidad"] == "semana"


def test_tesoreria_exige_concepto_y_respeta_naturaleza(client, scenario):
    login(client, scenario["user_id"])
    base = {
        "monto": 15,
        "descripcion": "Prueba",
        "instrumento_id": scenario["instrument_id"],
        "usuario_id": scenario["user_id"],
    }
    missing = client.post("/api/tesoreria/movimientos", json=base)
    assert missing.status_code == 400

    incompatible = client.post(
        "/api/tesoreria/movimientos",
        json={
            **base,
            "tipo": "egreso",
            "categoria_gasto_id": scenario["concept_ids"]["iva"],
        },
    )
    assert incompatible.status_code == 422

    derived = client.post(
        "/api/tesoreria/movimientos",
        json={
            **base,
            "categoria_gasto_id": scenario["concept_ids"]["iva"],
        },
    )
    assert derived.status_code == 201
    assert derived.get_json()["movimiento"]["tipo"] == "ingreso"

    both_missing_type = client.post(
        "/api/tesoreria/movimientos",
        json={
            **base,
            "categoria_gasto_id": scenario["concept_ids"]["both"],
        },
    )
    assert both_missing_type.status_code == 400

    both_expense = client.post(
        "/api/tesoreria/movimientos",
        json={
            **base,
            "tipo": "egreso",
            "categoria_gasto_id": scenario["concept_ids"]["both"],
        },
    )
    assert both_expense.status_code == 201
    assert both_expense.get_json()["movimiento"]["tipo"] == "egreso"


def test_gastos_fuerza_egreso_y_admin_audita(client, app, scenario):
    login(client, scenario["user_id"])
    base = {
        "descripcion": "Servicio",
        "monto": 25,
        "proveedor_id": scenario["provider_id"],
        "instrumento_id": scenario["instrument_id"],
        "usuario_id": scenario["user_id"],
    }
    income_concept = client.post(
        "/api/gastos/registrar",
        json={**base, "categoria_gasto_id": scenario["concept_ids"]["iva"]},
    )
    assert income_concept.status_code == 422

    both_concept = client.post(
        "/api/gastos/registrar",
        json={**base, "categoria_gasto_id": scenario["concept_ids"]["both"]},
    )
    assert both_concept.status_code == 201
    with app.app_context():
        created = MovimientoCaja.query.order_by(MovimientoCaja.id.desc()).first()
        assert created.tipo == "egreso"

    redirect = client.get("/admin/gastos")
    assert redirect.status_code == 301
    assert redirect.headers["Location"].endswith("/admin/movimientos")

    concepts = client.get("/api/admin/movimientos/conceptos")
    assert concepts.status_code == 200
    salary_payload = next(
        item for item in concepts.get_json()["items"]
        if item["id"] == scenario["concept_ids"]["salary"]
    )
    assert salary_payload["efecto"] == "resta"
    assert salary_payload["movimientos_asociados"] == 1
    assert salary_payload["conflictos"] == 0

    update = client.put(
        f"/api/admin/movimientos/conceptos/{scenario['concept_ids']['salary']}",
        json={
            "nombre": "SUELDOS",
            "descripcion": "",
            "naturaleza": "egreso",
            "incluye_resultado": False,
            "activo": True,
        },
    )
    assert update.status_code == 200
    with app.app_context():
        audit = CategoriaMovimientoAudit.query.order_by(
            CategoriaMovimientoAudit.id.desc()
        ).first()
        assert audit.accion == "actualizar"
        assert audit.usuario_id == scenario["user_id"]
        assert audit.valores_anteriores["incluye_resultado"] is True
        assert audit.valores_nuevos["incluye_resultado"] is False
