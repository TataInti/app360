"""Previsualización de liquidaciones de un período ya liquidado (hallazgo A-011).

Escenario del brief: salario 250.000,50; dos adelantos en efectivo de 50.000 aprobados
para 2026-11; dos préstamos de 120.000 en 3 cuotas al 10 % (cuota 44.000 c/u). Liquidar
2026-11 da neto 62.000,50. Previsualizar 2026-11 debe mostrar 62.000,50 (no 162.000,50);
2026-12 sin liquidar usa la siguiente cuota. Datos sintéticos rotulados PROBE.
"""

from decimal import Decimal

from models import Employee, db
from models.rrhh import Adelanto, LiquidacionSueldo
from sesion_de_prueba import asegurar_usuario, marcar_sesion


def _adelanto(empleado_id, tipo, monto, **extra):
    return Adelanto(
        empleado_id=empleado_id,
        tipo=tipo,
        monto=Decimal(monto),
        concepto="PROBE",
        aprobado=True,
        liquidado=False,
        **extra,
    )


def test_escenario_aritmetico_del_brief():
    # Verificación en la calculadora: 250.000,50 − 100.000 − 88.000 = 62.000,50
    assert Decimal("250000.50") - Decimal("100000") - Decimal("88000") == Decimal("62000.50")


def test_previsualizacion_de_periodo_liquidado_muestra_lo_guardado(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    empleado = Employee(first_name="PROBE", last_name="Liquidacion", salary=Decimal("250000.50"), is_active=True)
    db.session.add(empleado)
    db.session.flush()
    db.session.add_all([
        _adelanto(empleado.id, "adelanto_efectivo", "50000", mes_aplicacion="2026-11"),
        _adelanto(empleado.id, "adelanto_efectivo", "50000", mes_aplicacion="2026-11"),
        _adelanto(empleado.id, "prestamo", "120000", cantidad_cuotas=3, interes_porcentaje=Decimal("10"), cuotas_pagadas=0),
        _adelanto(empleado.id, "prestamo", "120000", cantidad_cuotas=3, interes_porcentaje=Decimal("10"), cuotas_pagadas=0),
    ])
    db.session.commit()

    liquidada = cliente.post("/api/rrhh/liquidaciones", json={"periodo": "2026-11"})
    assert liquidada.status_code == 201, liquidada.get_data(as_text=True)

    preview = cliente.get("/api/rrhh/liquidaciones/preview/2026-11").get_json()
    assert preview["periodo_liquidado"] is True
    assert preview["empleados_sin_liquidacion"] == 0
    fila = preview["liquidaciones"][0]
    assert fila["ya_liquidado"] is True
    assert fila["sueldo_neto"] == 62000.5
    assert fila["descuento_cuota_prestamo"] == 88000.0
    assert fila["sueldo_neto"] != 162000.5

    # El dato guardado no cambia con la previsualización.
    guardada = LiquidacionSueldo.query.filter_by(periodo="2026-11", empleado_id=empleado.id).one()
    assert guardada.sueldo_neto == Decimal("62000.50")

    # Generar un período ya liquidado sigue rechazado por el servidor.
    otra_vez = cliente.post("/api/rrhh/liquidaciones", json={"periodo": "2026-11"})
    assert otra_vez.status_code == 400


def test_previsualizacion_de_periodo_sin_liquidar_usa_la_siguiente_cuota(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    empleado = Employee(first_name="PROBE", last_name="Liquidacion", salary=Decimal("250000.50"), is_active=True)
    db.session.add(empleado)
    db.session.flush()
    db.session.add_all([
        _adelanto(empleado.id, "adelanto_efectivo", "50000", mes_aplicacion="2026-11"),
        _adelanto(empleado.id, "adelanto_efectivo", "50000", mes_aplicacion="2026-11"),
        _adelanto(empleado.id, "prestamo", "120000", cantidad_cuotas=3, interes_porcentaje=Decimal("10"), cuotas_pagadas=0),
        _adelanto(empleado.id, "prestamo", "120000", cantidad_cuotas=3, interes_porcentaje=Decimal("10"), cuotas_pagadas=0),
    ])
    db.session.commit()
    assert cliente.post("/api/rrhh/liquidaciones", json={"periodo": "2026-11"}).status_code == 201

    preview = cliente.get("/api/rrhh/liquidaciones/preview/2026-12").get_json()
    assert preview["periodo_liquidado"] is False
    assert preview["empleados_sin_liquidacion"] == 0
    fila = preview["liquidaciones"][0]
    assert fila["ya_liquidado"] is False
    # Sin adelantos para 2026-12; las dos cuotas siguientes (44.000 c/u) se descuentan.
    assert fila["descuento_adelanto_efectivo"] == 0.0
    assert fila["descuento_cuota_prestamo"] == 88000.0
    assert fila["sueldo_neto"] == 162000.5


def test_empleado_activo_sin_liquidacion_en_periodo_liquidado_se_informa(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    primero = Employee(first_name="PROBE", last_name="Uno", salary=Decimal("100000"), is_active=True)
    db.session.add(primero)
    db.session.commit()
    assert cliente.post("/api/rrhh/liquidaciones", json={"periodo": "2026-11"}).status_code == 201

    db.session.add(Employee(first_name="PROBE", last_name="Dos", salary=Decimal("90000"), is_active=True))
    db.session.commit()

    preview = cliente.get("/api/rrhh/liquidaciones/preview/2026-11").get_json()
    assert preview["periodo_liquidado"] is True
    assert preview["empleados_sin_liquidacion"] == 1
    assert len(preview["liquidaciones"]) == 1
    assert all(fila["ya_liquidado"] for fila in preview["liquidaciones"])
