"""Margen sin datos de costo (hallazgo A-013 del Barrido A).

Sin compras en el período, el margen (facturación − compras) / facturación daba 100 %, y
el resultado sobre facturación y la brecha caja-resultado salían de ese margen. Ahora, con
compras = 0, el margen queda en null con datos_insuficientes = true, y no se calcula la
brecha. Con compras, las cifras no cambian (300 de compras sobre 1.000 de facturación:
margen 70 %). /api/bi/rentabilidad deja los márgenes en null sin ventas o sin gastos.
Datos sintéticos rotulados PROBE; base SQLite en memoria; fechas relativas a hoy.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from models import db
from models.core.product import Product
from models.core.user import User
from models.crm.client import Client
from models.gastos import CategoriaGasto
from models.sabiogo.staging import StgSabiogoCompras, StgSabiogoVentas
from models.sales.venta import Venta
from models.time_utils import today_local_date
from models.tesoreria import InstrumentoPago, MovimientoCaja
from services.resultado_comercial_service import ResultadoComercialService
from sesion_de_prueba import asegurar_usuario, marcar_sesion


def _periodo():
    hoy = today_local_date()
    return hoy - timedelta(days=20), hoy - timedelta(days=5)


@pytest.fixture
def cliente_admin(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    return cliente


def _sembrar(app, con_compras, con_gastos=False):
    """Facturación de 1.000 y caja de 100 ingresos / 80 egresos, con o sin compras de 300."""
    desde, hasta = _periodo()
    fecha = hasta - timedelta(days=2)
    with app.app_context():
        usuario = db.session.get(User, 1) or User(id=1, username="PROBE-admin", role="admin", active=True)
        db.session.add(usuario)
        instrumento = InstrumentoPago(nombre="PROBE-efectivo", activo=True)
        db.session.add(instrumento)
        db.session.add(StgSabiogoVentas(
            fecha=fecha, origen="CARNES", codigo="PROBE-V1", producto="PROBE",
            sucursal="PROBE", cliente="PROBE cliente", vendedor="PROBE", comprobante="FAC",
            nro_comprob="0001-000001", subtot=1000, neto=1000, iva=0, estado="procesado",
        ))
        if con_compras:
            db.session.add(StgSabiogoCompras(
                fecha=fecha, origen="CARNES", codigo="PROBE-C1", producto="PROBE",
                subtot=300, neto=300, iva=0, estado="procesado",
            ))
        db.session.flush()
        for tipo, monto in (("ingreso", "100"), ("egreso", "80")):
            db.session.add(MovimientoCaja(
                fecha_hora=datetime.combine(fecha, datetime.min.time()).replace(hour=12),
                tipo=tipo, monto=Decimal(monto), descripcion="PROBE", estado="activo",
                instrumento_id=instrumento.id, usuario_id=1,
            ))
        if con_gastos:
            db.session.add(CategoriaGasto(nombre="PROBE gasto", naturaleza="egreso",
                                          incluye_resultado=True, activo=True))
        db.session.commit()
    return desde, hasta


# -----------------------------------------------------------------------------
# Servicio: el margen y la brecha dependen de compras
# -----------------------------------------------------------------------------
def test_servicio_sin_compras_no_calcula_margen_ni_brecha(app_seguridad):
    desde, hasta = _sembrar(app_seguridad, con_compras=False)
    resumen = ResultadoComercialService().calcular(desde, hasta)
    kpis = resumen["kpis"]
    assert kpis["compras"] == 0
    assert kpis["datos_insuficientes"] is True
    assert kpis["resultado_sobre_facturacion_pct"] is None
    relacion = resumen["analisis_financiero"]["relacion_resultado_caja"]
    assert relacion["brecha_caja_menos_resultado"] is None
    codigos = {item["code"] for item in resumen["analisis_financiero"]["insights"]}
    assert "brecha_caja_resultado" not in codigos


def test_servicio_con_compras_mantiene_las_cifras(app_seguridad):
    desde, hasta = _sembrar(app_seguridad, con_compras=True)
    resumen = ResultadoComercialService().calcular(desde, hasta)
    kpis = resumen["kpis"]
    assert kpis["datos_insuficientes"] is False
    assert kpis["compras"] == 300
    # Resultado = (1.000 − 300) + 0 − 0 = 700; porcentaje 70 %; brecha = caja neta 20 − 700.
    assert kpis["resultado_gestion"] == 700
    assert kpis["resultado_sobre_facturacion_pct"] == pytest.approx(70.0)
    relacion = resumen["analisis_financiero"]["relacion_resultado_caja"]
    assert relacion["brecha_caja_menos_resultado"] == pytest.approx(20 - 700)


# -----------------------------------------------------------------------------
# Endpoints del Panel ejecutivo y del dashboard de rentabilidad
# -----------------------------------------------------------------------------
def _query_periodo(desde, hasta):
    return {"fecha_desde": desde.isoformat(), "fecha_hasta": hasta.isoformat()}


def test_panel_ejecutivo_sin_compras_devuelve_margen_null(cliente_admin, app_seguridad):
    desde, hasta = _sembrar(app_seguridad, con_compras=False)
    respuesta = cliente_admin.get("/api/panel-ejecutivo-v2", query_string=_query_periodo(desde, hasta))
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:300]
    kpis = respuesta.get_json()["kpis"]
    assert kpis["datos_insuficientes"] is True
    assert kpis["sabiogo_margen_pct"] is None
    assert kpis["resultado_sobre_facturacion_pct"] is None


def test_panel_ejecutivo_con_compras_conserva_el_margen(cliente_admin, app_seguridad):
    desde, hasta = _sembrar(app_seguridad, con_compras=True)
    respuesta = cliente_admin.get("/api/panel-ejecutivo-v2", query_string=_query_periodo(desde, hasta))
    kpis = respuesta.get_json()["kpis"]
    assert kpis["datos_insuficientes"] is False
    assert kpis["sabiogo_margen_pct"] == pytest.approx(70.0)
    assert kpis["resultado_sobre_facturacion_pct"] == pytest.approx(70.0)


def test_dashboard_bi_sin_compras_devuelve_margen_null(cliente_admin, app_seguridad):
    desde, hasta = _sembrar(app_seguridad, con_compras=False)
    respuesta = cliente_admin.get("/api/bi/dashboard", query_string=_query_periodo(desde, hasta))
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:300]
    kpis = respuesta.get_json()["kpis"]
    assert kpis["datos_insuficientes"] is True
    assert kpis["margen_porcentual_sabiogo"] is None
    assert respuesta.get_json()["analisis_financiero"]["relacion_resultado_caja"]["brecha_caja_menos_resultado"] is None


def test_dashboard_bi_con_compras_conserva_el_margen(cliente_admin, app_seguridad):
    desde, hasta = _sembrar(app_seguridad, con_compras=True)
    respuesta = cliente_admin.get("/api/bi/dashboard", query_string=_query_periodo(desde, hasta))
    kpis = respuesta.get_json()["kpis"]
    assert kpis["datos_insuficientes"] is False
    assert kpis["margen_porcentual_sabiogo"] == pytest.approx(70.0)


# -----------------------------------------------------------------------------
# /api/bi/rentabilidad: sin ventas o sin gastos, márgenes en null
# -----------------------------------------------------------------------------
def test_rentabilidad_sin_datos_devuelve_margenes_null(cliente_admin):
    respuesta = cliente_admin.get("/api/bi/rentabilidad", query_string={"range": "6m"})
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)[:300]
    datos = respuesta.get_json()
    assert datos["kpis"]["datos_insuficientes"] is True
    assert datos["kpis"]["gross_margin"] is None
    assert datos["kpis"]["net_margin"] is None
    assert datos["kpis"]["ebitda_margin"] is None
    assert datos["alertas"] == []


def test_rentabilidad_con_ventas_y_sin_gastos_no_muestra_100_por_ciento(cliente_admin, app_seguridad):
    hoy = today_local_date()
    with app_seguridad.app_context():
        cliente = Client(name="PROBE cliente")
        producto = Product(name="PROBE producto", sku="PROBE-SKU-R1")
        db.session.add_all([cliente, producto])
        db.session.flush()
        db.session.add(Venta(
            fecha=hoy - timedelta(days=3), cliente_id=cliente.id, producto_id=producto.id,
            cantidad=2, precio_contrato=Decimal("500"), precio_efectivo=Decimal("500"),
        ))
        db.session.commit()

    datos = cliente_admin.get("/api/bi/rentabilidad", query_string={"range": "6m"}).get_json()
    assert datos["kpis"]["datos_insuficientes"] is True
    assert datos["kpis"]["gross_margin"] is None
    assert datos["margen_serie"]["bruto"] and all(valor is None for valor in datos["margen_serie"]["bruto"])
    assert datos["margen_unidades"]["bruto"] == [] or all(v is None for v in datos["margen_unidades"]["bruto"])
    assert datos["alertas"] == []


def test_rentabilidad_con_ventas_y_gastos_calcula_el_margen(cliente_admin, app_seguridad):
    hoy = today_local_date()
    with app_seguridad.app_context():
        cliente = Client(name="PROBE cliente")
        producto = Product(name="PROBE producto", sku="PROBE-SKU-R2")
        instrumento = InstrumentoPago(nombre="PROBE-caja-r", activo=True)
        categoria = CategoriaGasto(nombre="PROBE gasto r", naturaleza="egreso", incluye_resultado=True, activo=True)
        db.session.add_all([cliente, producto, instrumento, categoria])
        db.session.flush()
        db.session.add(Venta(
            fecha=hoy - timedelta(days=3), cliente_id=cliente.id, producto_id=producto.id,
            cantidad=2, precio_contrato=Decimal("500"), precio_efectivo=Decimal("500"),
        ))
        db.session.add(MovimientoCaja(
            fecha_hora=datetime.combine(hoy - timedelta(days=3), datetime.min.time()).replace(hour=10),
            tipo="egreso", monto=Decimal("250"), descripcion="PROBE gasto", estado="activo",
            instrumento_id=instrumento.id, usuario_id=1, categoria_gasto_id=categoria.id,
        ))
        db.session.commit()

    datos = cliente_admin.get("/api/bi/rentabilidad", query_string={"range": "6m"}).get_json()
    assert datos["kpis"]["datos_insuficientes"] is False
    # Ventas 1.000 y gastos 250: margen bruto (1.000 − 250) / 1.000 = 75 %.
    assert datos["kpis"]["gross_margin"] == pytest.approx(0.75)
