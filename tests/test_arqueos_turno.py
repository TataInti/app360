"""Arqueo de caja: diferencia del modal = diferencia guardada (hallazgo A-012).

El backend recalcula ingresos y egresos del turno desde los movimientos activos y guarda
diferencia = saldo final − (saldo inicial + ingresos − egresos). La vista previa del modal
usa esos mismos totales (GET /api/tesoreria/arqueos/totales), así que coinciden. Escenario
del informe: saldo inicial 1.000, ingresos 1.500, egresos 500, saldo real 2.025 → 25,00.
Datos sintéticos rotulados PROBE; base SQLite en memoria.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from models import db
from models.core.user import User
from models.tesoreria import ArqueoCaja, InstrumentoPago, MovimientoCaja
from sesion_de_prueba import asegurar_usuario, marcar_sesion

RUTA_TOTALES = "/api/tesoreria/arqueos/totales"
RUTA_ARQUEO = "/api/tesoreria/arqueos"


@pytest.fixture
def caja(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    asegurar_usuario(app_seguridad, 3, "PROBE-ventas", "sales")
    instrumento = InstrumentoPago(nombre="PROBE-efectivo", activo=True)
    db.session.add(instrumento)
    db.session.flush()

    def mov(tipo, monto, hora, estado="activo", fecha="2026-11-18"):
        db.session.add(MovimientoCaja(
            fecha_hora=datetime.fromisoformat(f"{fecha} {hora}"),
            tipo=tipo, monto=Decimal(monto), descripcion="PROBE",
            estado=estado, instrumento_id=instrumento.id, usuario_id=1,
        ))

    mov("ingreso", "1000.00", "09:00")
    mov("ingreso", "500.00", "10:30")                 # turno mañana: 1.500 de ingresos
    mov("egreso", "300.00", "11:00")
    mov("egreso", "200.00", "12:15")                  # 500 de egresos
    mov("ingreso", "9999.00", "11:30", estado="anulado")  # excluido
    mov("ingreso", "7777.00", "15:00")                # turno tarde: fuera de la mañana
    mov("egreso", "888.00", "02:00", fecha="2026-11-19")  # noche del 18: fuera de la mañana
    db.session.commit()
    return app_seguridad


@pytest.fixture
def admin_cliente(caja):
    cliente = caja.test_client()
    marcar_sesion(cliente, 1)
    return cliente


def test_totales_del_turno_usan_movimientos_activos_de_la_ventana(admin_cliente):
    respuesta = admin_cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18", "turno": "mañana"})
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)
    assert respuesta.get_json() == {
        "fecha": "2026-11-18", "turno": "mañana",
        "ingresos_total": 1500.0, "egresos_total": 500.0,
    }


def test_turno_noche_cubre_hasta_las_seis_del_dia_siguiente(admin_cliente):
    respuesta = admin_cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18", "turno": "noche"})
    assert respuesta.get_json()["egresos_total"] == 888.0
    assert respuesta.get_json()["ingresos_total"] == 0.0


def test_totales_validan_fecha_y_turno(admin_cliente):
    assert admin_cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18"}).status_code == 400
    assert admin_cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18", "turno": "x"}).status_code == 400
    assert admin_cliente.get(RUTA_TOTALES, query_string={"fecha": "18/11/2026", "turno": "mañana"}).status_code == 400


def test_totales_siguen_el_modulo_de_tesoreria(caja):
    cliente = caja.test_client()
    assert cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18", "turno": "mañana"}).status_code == 401
    marcar_sesion(cliente, 3)  # sales: sin tesorería
    respuesta = cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18", "turno": "mañana"})
    assert respuesta.status_code == 403
    assert respuesta.get_json() == {"error": "Sin acceso al módulo"}


def test_diferencia_guardada_coincide_con_la_del_modal(admin_cliente, caja):
    totales = admin_cliente.get(RUTA_TOTALES, query_string={"fecha": "2026-11-18", "turno": "mañana"}).get_json()
    saldo_inicial, saldo_final = Decimal("1000.00"), Decimal("2025.00")

    # Lo que muestra el modal antes de guardar (misma fórmula que calcularDiferencia en la plantilla).
    diferencia_modal = saldo_final - (saldo_inicial + Decimal(str(totales["ingresos_total"]))
                                      - Decimal(str(totales["egresos_total"])))
    assert diferencia_modal == Decimal("25.00")

    respuesta = admin_cliente.post(RUTA_ARQUEO, json={
        "fecha": "2026-11-18", "turno": "mañana",
        "saldo_inicial": 1000, "saldo_final": 2025,
        # Ingresos y egresos escritos a mano: el backend los descarta y usa los del sistema.
        "ingresos": 9999, "egresos": 1, "diferencia": 492.5,
        "detalles": [],
    })
    assert respuesta.status_code == 201, respuesta.get_data(as_text=True)
    with caja.app_context():
        arqueo = db.session.get(ArqueoCaja, respuesta.get_json()["arqueo"]["id"])
        assert arqueo.ingresos_total == Decimal("1500.00")
        assert arqueo.egresos_total == Decimal("500.00")
        assert arqueo.diferencia == diferencia_modal


def test_usuario_inactivo_no_guarda_arqueo(caja):
    cliente = caja.test_client()
    marcar_sesion(cliente, 1)
    with caja.app_context():
        db.session.query(User).filter_by(id=1).update({"active": False})
        db.session.commit()
    respuesta = cliente.post(RUTA_ARQUEO, json={"fecha": "2026-11-18", "turno": "mañana", "saldo_final": 1})
    assert respuesta.status_code in (401, 403)
    with caja.app_context():
        assert db.session.query(ArqueoCaja).count() == 0
