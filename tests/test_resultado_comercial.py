from datetime import date, datetime, timedelta
from decimal import Decimal
import io

import pandas as pd
import pytest

from app import create_app
from config import Config
from models import db
from models.hr.employee import Employee
from models.core.user import User
from models.gastos import CategoriaGasto, CategoriaMovimientoAudit, Proveedor
from models.rrhh import Adelanto, LiquidacionSueldo
from models.sabiogo.staging import StgSabiogoCompras, StgSabiogoVentas
from models.tesoreria import InstrumentoPago, MovimientoCaja
from models.time_utils import today_local_date
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
                StgSabiogoVentas(
                    **{
                        **common_sale,
                        "origen": "LACTEOS",
                        "codigo": "L1",
                        "producto": "Producto Lácteos",
                    },
                    comprobante="FAC",
                    cliente="Cliente Lácteos",
                    subtot=500,
                    neto=500,
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
                StgSabiogoCompras(
                    fecha=date(2026, 7, 15),
                    origen="LACTEOS",
                    codigo="LC1",
                    producto="Mercadería Lácteos",
                    subtot=200,
                    neto=200,
                    iva=0,
                    estado="procesado",
                ),
            ]
        )

        def movement(tipo, amount, concept=None, estado="activo", empresa="CARNES"):
            return MovimientoCaja(
                fecha_hora=datetime(2026, 7, 15, 12),
                empresa=empresa,
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
                movement("ingreso", 60, concepts["iva"], empresa="LACTEOS"),
                movement("egreso", 90, concepts["salary"], empresa="LACTEOS"),
                movement("egreso", 10, concepts["neutral"], empresa="LACTEOS"),
                movement("ingreso", 12, concepts["iva"], empresa=None),
                movement("egreso", 8, concepts["salary"], empresa=None),
            ]
        )
        employees = {
            "carnes": Employee(
                first_name="Ana",
                last_name="Pérez",
                empresa="CARNES",
            ),
            "lacteos": Employee(
                first_name="Luis",
                last_name="Gómez",
                empresa="LACTEOS",
            ),
            "historico": Employee(
                first_name="Hugo",
                last_name="Histórico",
                empresa=None,
            ),
        }
        db.session.add_all(employees.values())
        db.session.flush()
        db.session.add_all(
            [
                LiquidacionSueldo(
                    empleado_id=employees["carnes"].id,
                    periodo="2026-07",
                    empresa="CARNES",
                    sueldo_base=Decimal("300"),
                    sueldo_neto=Decimal("220"),
                    fecha_liquidacion=datetime(2026, 7, 20, 10),
                ),
                LiquidacionSueldo(
                    empleado_id=employees["lacteos"].id,
                    periodo="2026-07",
                    empresa="LACTEOS",
                    sueldo_base=Decimal("220"),
                    sueldo_neto=Decimal("150"),
                    fecha_liquidacion=datetime(2026, 7, 20, 10),
                ),
                LiquidacionSueldo(
                    empleado_id=employees["historico"].id,
                    periodo="2026-07",
                    empresa=None,
                    sueldo_base=Decimal("100"),
                    sueldo_neto=Decimal("60"),
                    fecha_liquidacion=datetime(2026, 7, 20, 10),
                ),
                Adelanto(
                    empleado_id=employees["carnes"].id,
                    empresa="CARNES",
                    tipo="adelanto_efectivo",
                    monto=Decimal("30"),
                    concepto="Adelanto de sueldo",
                    aprobado=True,
                    pagado=True,
                    fecha_pago=datetime(2026, 7, 18, 10),
                ),
                Adelanto(
                    empleado_id=employees["carnes"].id,
                    empresa="CARNES",
                    tipo="prestamo",
                    monto=Decimal("50"),
                    concepto="Préstamo",
                    aprobado=True,
                    pagado=True,
                    fecha_pago=datetime(2026, 7, 18, 10),
                ),
                Adelanto(
                    empleado_id=employees["carnes"].id,
                    empresa="CARNES",
                    tipo="adelanto_efectivo",
                    monto=Decimal("40"),
                    concepto="Pendiente de pago",
                    aprobado=True,
                    pagado=False,
                ),
                Adelanto(
                    empleado_id=employees["lacteos"].id,
                    empresa="LACTEOS",
                    tipo="adelanto_efectivo",
                    monto=Decimal("25"),
                    concepto="Adelanto de sueldo lácteos",
                    aprobado=True,
                    pagado=True,
                    fecha_pago=datetime(2026, 7, 18, 10),
                ),
                Adelanto(
                    empleado_id=employees["historico"].id,
                    empresa=None,
                    tipo="adelanto_efectivo",
                    monto=Decimal("10"),
                    concepto="Adelanto histórico sin empresa",
                    aprobado=True,
                    pagado=True,
                    fecha_pago=datetime(2026, 7, 18, 10),
                ),
            ]
        )
        db.session.commit()
        return {
            "user_id": user.id,
            "instrument_id": instrument.id,
            "provider_id": provider.id,
            "concept_ids": {key: value.id for key, value in concepts.items()},
            "employee_ids": {key: value.id for key, value in employees.items()},
        }


def login(client, user_id):
    with client.session_transaction() as flask_session:
        flask_session["user"] = "admin"
        flask_session["user_id"] = user_id
        flask_session["role"] = "admin"


def _analysis_for_copy(
    *,
    resultado=0,
    caja_neta=0,
    ingresos_caja=0,
    egresos_caja=0,
    actividad_mensual=None,
    caja_mensual=None,
    participantes=None,
    clientes=None,
):
    return ResultadoComercialService()._analisis_financiero(
        desde=date(2026, 6, 1),
        hasta=date(2026, 7, 31),
        kpis={
            "facturacion": 0,
            "compras": 0,
            "ingresos_incluidos": 0,
            "egresos_incluidos": 0,
            "resultado_gestion": resultado,
            "ingresos_caja": ingresos_caja,
            "egresos_caja": egresos_caja,
            "caja_neta": caja_neta,
        },
        actividad_mensual=actividad_mensual or {},
        caja_mensual=caja_mensual or {},
        participantes=participantes or [],
        clientes=clientes or {"top_5_pct": 0},
    )


def _insight(analysis, code):
    return next(item for item in analysis["insights"] if item["code"] == code)


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
        assert result["sueldos_pagados"] == {
            "tesoreria_sueldos": {"monto": 80.0, "cantidad": 1},
            "liquidaciones_rrhh": {"monto": 220.0, "cantidad": 1},
            "adelantos_rrhh": {"monto": 30.0, "cantidad": 1},
            "total": 330.0,
            "margen_comercial": 700.0,
            "margen_despues_sueldos_pagados": 370.0,
        }
        financial = result["analisis_financiero"]
        assert financial["flujo_caja"]["ingresos"] == 200
        assert financial["flujo_caja"]["egresos"] == 155
        assert financial["flujo_caja"]["neto"] == 45
        assert financial["relacion_resultado_caja"]["brecha_caja_menos_resultado"] == -715
        assert financial["tendencia"]["meses"] == 1
        assert financial["tendencia"]["flujo_mensual"][0]["neto"] == 45
        assert financial["insights"]
        assert result["conceptos"]["conflictos"] == 1
        assert result["conceptos"]["pendientes"] == 1
        assert result["meta"]["warnings"] == []
        assert result["meta"]["data_quality"] == {
            "movimientos_incompatibles": 1,
            "conceptos_pendientes": 1,
        }
        both_rows = [
            row for row in result["conceptos"]["desglose"]
            if row["concepto"] == "FINANCIERA"
        ]
        assert {row["tipo"] for row in both_rows} == {"ingreso", "egreso"}
        participants = {
            row["concepto"]: row
            for row in result["conceptos"]["participantes"]
        }
        assert participants["EFECTIVO IVA"]["suma"] == {"cantidad": 1, "monto": 100.0}
        assert participants["SUELDOS"]["resta"] == {"cantidad": 1, "monto": 80.0}
        assert participants["FINANCIERA"]["suma"] == {"cantidad": 1, "monto": 50.0}
        assert participants["FINANCIERA"]["resta"] == {"cantidad": 1, "monto": 20.0}
        assert participants["HISTORICO"]["activo"] is False


def test_resultado_separa_empresas_y_conserva_historicos_en_todas(app, scenario):
    with app.app_context():
        service = ResultadoComercialService()
        carnes = service.calcular(date(2026, 7, 1), date(2026, 7, 31), "CARNES")
        lacteos = service.calcular(date(2026, 7, 1), date(2026, 7, 31), "LACTEOS")
        todas = service.calcular(date(2026, 7, 1), date(2026, 7, 31), "TODAS")

        assert carnes["kpis"] == {
            "facturacion": 1000.0,
            "compras": 300.0,
            "diferencia_facturacion_compras": 700.0,
            "ingresos_incluidos": 160.0,
            "egresos_incluidos": 100.0,
            "resultado_gestion": 760.0,
            "resultado_sobre_facturacion_pct": 76.0,
            "ingresos_caja": 200.0,
            "egresos_caja": 155.0,
            "caja_neta": 45.0,
            "movimientos_caja": 8,
        }
        assert lacteos["kpis"] == {
            "facturacion": 500.0,
            "compras": 200.0,
            "diferencia_facturacion_compras": 300.0,
            "ingresos_incluidos": 60.0,
            "egresos_incluidos": 90.0,
            "resultado_gestion": 270.0,
            "resultado_sobre_facturacion_pct": 54.0,
            "ingresos_caja": 60.0,
            "egresos_caja": 100.0,
            "caja_neta": -40.0,
            "movimientos_caja": 3,
        }
        assert todas["kpis"] == {
            "facturacion": 1500.0,
            "compras": 500.0,
            "diferencia_facturacion_compras": 1000.0,
            "ingresos_incluidos": 232.0,
            "egresos_incluidos": 198.0,
            "resultado_gestion": 1034.0,
            "resultado_sobre_facturacion_pct": pytest.approx(68.9333333333),
            "ingresos_caja": 272.0,
            "egresos_caja": 263.0,
            "caja_neta": 9.0,
            "movimientos_caja": 13,
        }

        assert lacteos["series"]["actividad_mensual"] == [
            {
                "periodo": "2026-07-01",
                "facturacion": 500.0,
                "compras": 200.0,
                "diferencia": 300.0,
                "ingresos_incluidos": 60.0,
                "egresos_incluidos": 90.0,
                "resultado_gestion": 270.0,
            }
        ]
        assert lacteos["series"]["caja_mensual"] == [
            {
                "periodo": "2026-07-01",
                "ingresos": 60.0,
                "egresos": 100.0,
                "neto": -40.0,
            }
        ]
        assert lacteos["sueldos_pagados"] == {
            "tesoreria_sueldos": {"monto": 90.0, "cantidad": 1},
            "liquidaciones_rrhh": {"monto": 150.0, "cantidad": 1},
            "adelantos_rrhh": {"monto": 25.0, "cantidad": 1},
            "total": 265.0,
            "margen_comercial": 300.0,
            "margen_despues_sueldos_pagados": 35.0,
        }
        assert todas["sueldos_pagados"]["total"] == 673.0
        assert lacteos["analisis_financiero"]["insights"][0]["code"] == (
            "resultado_sin_caja"
        )

        assert carnes["meta"]["treasury_scope"] == "company_filtered"
        assert carnes["meta"]["empresa_scope"] == {
            "selected": "CARNES",
            "is_specific": True,
            "historical_unassigned": {
                "movimientos": 2,
                "adelantos": 1,
                "liquidaciones": 1,
            },
        }
        assert todas["meta"]["treasury_scope"] == "global"
        assert todas["meta"]["empresa_scope"]["selected"] == "TODAS"
        assert todas["meta"]["empresa_scope"]["is_specific"] is False

        # Las liquidaciones y adelantos conservan su empresa emitida aunque el
        # empleado cambie de empresa después.
        empleado_carnes = db.session.get(Employee, scenario["employee_ids"]["carnes"])
        empleado_carnes.empresa = "LACTEOS"
        db.session.commit()
        despues_del_traslado = service.calcular(
            date(2026, 7, 1),
            date(2026, 7, 31),
            "CARNES",
        )
        assert despues_del_traslado["sueldos_pagados"] == carnes["sueldos_pagados"]


def test_participantes_permanecen_visibles_sin_movimientos(app, scenario):
    with app.app_context():
        result = ResultadoComercialService().calcular(
            date(2026, 6, 1),
            date(2026, 6, 30),
            "TODAS",
        )
        participants = {
            row["concepto"]: row
            for row in result["conceptos"]["participantes"]
        }
        assert participants["SUELDOS"]["resta"] == {"cantidad": 0, "monto": 0.0}
        assert participants["EFECTIVO IVA"]["suma"] == {"cantidad": 0, "monto": 0.0}
        assert participants["FINANCIERA"]["suma"] == {"cantidad": 0, "monto": 0.0}
        assert participants["FINANCIERA"]["resta"] == {"cantidad": 0, "monto": 0.0}
        assert result["analisis_financiero"]["insights"][0]["code"] == "sin_movimientos_caja"


def test_insights_usar_lenguaje_de_gestion_claro():
    cases = [
        (
            "sin_movimientos_caja",
            "No se registraron ingresos ni egresos en Tesorería para este período. Revisá si faltan cargar movimientos antes de usar esta lectura.",
            _analysis_for_copy(),
        ),
        (
            "resultado_sin_caja",
            "El resultado del período da positivo, pero salió más dinero del que entró. Revisá cobranzas pendientes, pagos adelantados y fechas de registración.",
            _analysis_for_copy(
                resultado=100,
                caja_neta=-50,
                ingresos_caja=50,
                egresos_caja=100,
                caja_mensual={"2026-06": {"ingresos": 50, "egresos": 100}},
            ),
        ),
        (
            "caja_sin_resultado",
            "Entró más dinero del que salió, aunque el resultado del período da negativo. Revisá si ingresaron cobranzas de ventas anteriores o si las compras todavía no se reflejan en ventas.",
            _analysis_for_copy(
                resultado=-100,
                caja_neta=50,
                ingresos_caja=100,
                egresos_caja=50,
                caja_mensual={"2026-06": {"ingresos": 100, "egresos": 50}},
            ),
        ),
        (
            "flujo_negativo",
            "Salió más dinero del que entró. Revisá los egresos más altos y las cobranzas pendientes del período.",
            _analysis_for_copy(
                resultado=-10,
                caja_neta=-50,
                ingresos_caja=50,
                egresos_caja=100,
                caja_mensual={"2026-06": {"ingresos": 50, "egresos": 100}},
            ),
        ),
        (
            "flujo_positivo",
            "Entró más dinero del que salió. Revisá si esta mejora se sostiene en los próximos períodos.",
            _analysis_for_copy(
                resultado=10,
                caja_neta=50,
                ingresos_caja=100,
                egresos_caja=50,
                caja_mensual={"2026-06": {"ingresos": 100, "egresos": 50}},
            ),
        ),
        (
            "cobertura_insuficiente",
            "Por cada $100 que salieron, ingresaron $ 50.0. Revisá pagos próximos y cobranzas pendientes.",
            _analysis_for_copy(
                resultado=10,
                caja_neta=-50,
                ingresos_caja=50,
                egresos_caja=100,
                caja_mensual={"2026-06": {"ingresos": 50, "egresos": 100}},
            ),
        ),
        (
            "cobertura_suficiente",
            "Por cada $100 que salieron, ingresaron $ 200.0. Los ingresos del período alcanzaron para cubrir los pagos registrados.",
            _analysis_for_copy(
                resultado=10,
                caja_neta=100,
                ingresos_caja=200,
                egresos_caja=100,
                caja_mensual={"2026-06": {"ingresos": 200, "egresos": 100}},
            ),
        ),
        (
            "brecha_caja_resultado",
            "Entre caja y resultado hay una diferencia de $ 200.000. Revisá movimientos cobrados o pagados en fechas distintas a la operación.",
            _analysis_for_copy(resultado=200000),
        ),
        (
            "concentracion_clientes",
            "Los cinco clientes principales concentran el 60.0% de la facturación. Revisá plazos de cobro y dependencia de esas cuentas.",
            _analysis_for_copy(clientes={"top_5_pct": 60}),
        ),
        (
            "principal_egreso_incluido",
            "SUELDOS fue el concepto que más redujo el resultado: $ 125.000. Revisá su composición y evolución.",
            _analysis_for_copy(
                participantes=[{"concepto": "SUELDOS", "resta": {"monto": 125000}}]
            ),
        ),
        (
            "tendencia_resultado",
            "El resultado fue negativo en 2 de 2 meses. Revisá si la facturación está alcanzando para absorber compras y egresos incluidos.",
            _analysis_for_copy(
                actividad_mensual={
                    "2026-06": {"resultado_gestion": -10},
                    "2026-07": {"resultado_gestion": -20},
                }
            ),
        ),
        (
            "tendencia_caja",
            "La caja dio negativa en 2 de 2 meses. Revisá en qué meses se concentraron pagos y cobranzas.",
            _analysis_for_copy(
                caja_neta=-100,
                ingresos_caja=0,
                egresos_caja=100,
                caja_mensual={
                    "2026-06": {"ingresos": 0, "egresos": 50},
                    "2026-07": {"ingresos": 0, "egresos": 50},
                },
            ),
        ),
    ]

    for code, expected_message, analysis in cases:
        assert _insight(analysis, code)["message"] == expected_message

    monitored = _analysis_for_copy(clientes={"top_5_pct": 40})
    assert _insight(monitored, "concentracion_clientes")["message"] == (
        "Los cinco clientes principales representan el 40.0% de la facturación. "
        "Conviene seguir sus plazos de cobro por separado."
    )


def test_rrhh_operativo_exige_empresa_y_conserva_snapshots(client, app, scenario):
    """Los adelantos y liquidaciones no cambian de alcance tras un traslado."""
    login(client, scenario["user_id"])

    sin_empresa = client.post(
        "/api/rrhh/adelantos",
        json={
            "empleado_id": scenario["employee_ids"]["historico"],
            "tipo": "adelanto_efectivo",
            "monto": 15,
            "concepto": "Adelanto sin empresa",
            "mes_aplicacion": "2026-08",
        },
    )
    assert sin_empresa.status_code == 409

    adelanto = client.post(
        "/api/rrhh/adelantos",
        json={
            "empleado_id": scenario["employee_ids"]["carnes"],
            "tipo": "adelanto_efectivo",
            "monto": 15,
            "concepto": "Adelanto con snapshot",
            "mes_aplicacion": "2026-08",
        },
    )
    assert adelanto.status_code == 201
    assert adelanto.get_json()["adelanto"]["empresa"] == "CARNES"

    assert client.get("/api/rrhh/liquidaciones/preview/2026-08").status_code == 400
    preview = client.get(
        "/api/rrhh/liquidaciones/preview/2026-08?empresa=CARNES"
    )
    assert preview.status_code == 200
    assert preview.get_json()["cobertura"] == {"empleados_sin_empresa": 1}

    generated = client.post(
        "/api/rrhh/liquidaciones",
        json={"periodo": "2026-08", "empresa": "CARNES"},
    )
    assert generated.status_code == 201
    assert generated.get_json()["liquidaciones"][0]["empresa"] == "CARNES"

    # Emitimos otro período antes del traslado para comprobar la protección del
    # índice histórico (empleado_id, periodo) aun cuando cambie de empresa.
    assert client.post(
        "/api/rrhh/liquidaciones",
        json={"periodo": "2026-09", "empresa": "CARNES"},
    ).status_code == 201

    with app.app_context():
        employee = db.session.get(Employee, scenario["employee_ids"]["carnes"])
        employee.empresa = "LACTEOS"
        db.session.commit()

    historico_carnes = client.get("/api/rrhh/adelantos?empresa=CARNES")
    assert any(
        item["id"] == adelanto.get_json()["adelanto"]["id"]
        and item["empresa"] == "CARNES"
        for item in historico_carnes.get_json()["adelantos"]
    )
    liquidaciones_carnes = client.get(
        "/api/rrhh/liquidaciones/2026-08?empresa=CARNES"
    )
    assert liquidaciones_carnes.status_code == 200
    assert liquidaciones_carnes.get_json()["liquidaciones"][0]["empresa"] == "CARNES"

    traslado_mismo_periodo = client.post(
        "/api/rrhh/liquidaciones",
        json={"periodo": "2026-09", "empresa": "LACTEOS"},
    )
    assert traslado_mismo_periodo.status_code == 400
    assert "ya tiene una liquidación" in traslado_mismo_periodo.get_json()["error"]


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
    login(client, scenario["user_id"])
    params = "fecha_desde=2026-07-01&fecha_hasta=2026-07-29&empresa=CARNES"
    executive = client.get(f"/api/panel-ejecutivo-v2?{params}").get_json()
    commercial = client.get(f"/api/bi/dashboard?{params}").get_json()
    assert executive["kpis"]["resultado_gestion"] == commercial["kpis"]["resultado_gestion"] == 760
    assert executive["kpis"]["facturacion"] == commercial["kpis"]["facturacion"] == 1000
    assert executive["kpis"]["caja_neta"] == commercial["kpis"]["caja_neta"] == 45
    assert executive["conceptos"]["participantes"] == commercial["conceptos"]["participantes"]
    assert executive["analisis_financiero"] == commercial["analisis_financiero"]
    assert executive["sueldos_pagados"] == commercial["sueldos_pagados"]
    assert executive["alertas"] == commercial["meta"]["warnings"] == []


def test_dashboards_aplican_empresa_y_validan_filtro(client, scenario):
    login(client, scenario["user_id"])
    dates = "fecha_desde=2026-07-01&fecha_hasta=2026-07-29"

    for empresa, expected in (("CARNES", 760.0), ("LACTEOS", 270.0), ("TODAS", 1034.0)):
        executive_response = client.get(
            f"/api/panel-ejecutivo-v2?{dates}&empresa={empresa}"
        )
        commercial_response = client.get(
            f"/api/bi/dashboard?{dates}&empresa={empresa}"
        )
        assert executive_response.status_code == commercial_response.status_code == 200
        executive = executive_response.get_json()
        commercial = commercial_response.get_json()
        assert executive["kpis"]["resultado_gestion"] == expected
        assert commercial["kpis"]["resultado_gestion"] == expected
        assert executive["series"]["actividad_mensual"] == commercial["series"]["actividad_mensual"]
        assert executive["series"]["caja_mensual"] == commercial["series"]["caja_mensual"]
        assert executive["sueldos_pagados"] == commercial["sueldos_pagados"]
        assert executive["analisis_financiero"] == commercial["analisis_financiero"]
        assert executive["meta"]["empresa_scope"] == commercial["meta"]["empresa_scope"]
        assert executive["meta"]["empresa_scope"]["selected"] == empresa
        assert executive["meta"]["empresa_scope"]["is_specific"] is (empresa != "TODAS")

    missing_executive = client.get(f"/api/panel-ejecutivo-v2?{dates}")
    missing_commercial = client.get(f"/api/bi/dashboard?{dates}")
    assert missing_executive.status_code == missing_commercial.status_code == 200
    assert missing_executive.get_json()["meta"]["empresa_scope"]["selected"] == "TODAS"
    assert missing_commercial.get_json()["meta"]["empresa_scope"]["selected"] == "TODAS"

    invalid_executive = client.get(f"/api/panel-ejecutivo-v2?{dates}&empresa=OTRA")
    invalid_commercial = client.get(f"/api/bi/dashboard?{dates}&empresa=OTRA")
    assert invalid_executive.status_code == invalid_commercial.status_code == 400
    assert "Empresa" in invalid_executive.get_json()["error"]
    assert "Empresa" in invalid_commercial.get_json()["error"]


def test_dashboards_rechazan_fechas_futuras(client, scenario):
    future = (today_local_date() + timedelta(days=1)).isoformat()
    today = today_local_date().isoformat()
    executive = client.get(
        f"/api/panel-ejecutivo-v2?fecha_desde={today}&fecha_hasta={future}"
    )
    commercial = client.get(
        f"/api/bi/dashboard?fecha_desde={today}&fecha_hasta={future}"
    )
    assert executive.status_code == 400
    assert commercial.status_code == 400
    assert "futura" in executive.get_json()["error"]
    assert "futura" in commercial.get_json()["error"]


def test_movimientos_filtran_y_exportan_por_concepto(client, scenario):
    login(client, scenario["user_id"])
    salary_id = scenario["concept_ids"]["salary"]
    response = client.get(
        "/api/tesoreria/movimientos"
        f"?fecha_desde=2026-07-01&fecha_hasta=2026-07-29&categoria_gasto_id={salary_id}&empresa=CARNES"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["movimientos"][0]["categoria_gasto_id"] == salary_id
    assert payload["movimientos"][0]["categoria_gasto"] == "SUELDOS"
    assert payload["movimientos"][0]["empresa"] == "CARNES"

    lacteos = client.get(
        "/api/tesoreria/movimientos"
        f"?fecha_desde=2026-07-01&fecha_hasta=2026-07-29&categoria_gasto_id={salary_id}&empresa=LACTEOS"
    )
    assert lacteos.status_code == 200
    assert lacteos.get_json()["total"] == 1
    assert lacteos.get_json()["movimientos"][0]["empresa"] == "LACTEOS"

    todas = client.get(
        "/api/tesoreria/movimientos"
        f"?fecha_desde=2026-07-01&fecha_hasta=2026-07-29&categoria_gasto_id={salary_id}&empresa=TODAS"
    )
    assert todas.status_code == 200
    assert todas.get_json()["total"] == 3
    assert {item["empresa"] for item in todas.get_json()["movimientos"]} == {
        "CARNES",
        "LACTEOS",
        None,
    }

    invalid = client.get("/api/tesoreria/movimientos?categoria_gasto_id=abc")
    missing = client.get("/api/tesoreria/movimientos?categoria_gasto_id=999999")
    invalid_empresa = client.get("/api/tesoreria/movimientos?empresa=OTRA")
    assert invalid.status_code == 400
    assert missing.status_code == 400
    assert invalid_empresa.status_code == 400

    exported = client.get(
        "/api/tesoreria/movimientos/exportar"
        f"?fecha_desde=2026-07-01&fecha_hasta=2026-07-29&categoria_gasto_id={salary_id}&empresa=CARNES"
    )
    assert exported.status_code == 200
    sheet = pd.read_excel(io.BytesIO(exported.data))
    assert sheet["Concepto"].tolist() == ["SUELDOS"]
    assert sheet["Empresa"].tolist() == ["Carnes"]


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
        "empresa": "CARNES",
    }
    missing = client.post("/api/tesoreria/movimientos", json=base)
    assert missing.status_code == 400

    missing_empresa = client.post(
        "/api/tesoreria/movimientos",
        json={
            key: value
            for key, value in {
                **base,
                "categoria_gasto_id": scenario["concept_ids"]["iva"],
            }.items()
            if key != "empresa"
        },
    )
    invalid_empresa = client.post(
        "/api/tesoreria/movimientos",
        json={
            **base,
            "empresa": "OTRA",
            "categoria_gasto_id": scenario["concept_ids"]["iva"],
        },
    )
    assert missing_empresa.status_code == 400
    assert invalid_empresa.status_code == 400

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
    assert derived.get_json()["movimiento"]["empresa"] == "CARNES"

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
        "empresa": "CARNES",
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
        assert created.empresa == "CARNES"

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
    assert salary_payload["movimientos_asociados"] == 3
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
