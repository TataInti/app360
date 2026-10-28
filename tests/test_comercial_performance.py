"""Contratos de lectura de la pestaña Performance de Vendedores."""
from datetime import date

import os
import pytest

from app import create_app
from config import Config
from test_dashboard_equipo import agregar_pre
from services.vendedores_comerciales import seed_vendedores_comerciales
from models import db
from models.comercial import (
    ComercialClienteCriterio,
    ComercialObjetivo,
    ComercialVendedor,
)
from models.sabiogo.staging import StgSabiogoVentas


@pytest.fixture
def app(monkeypatch):
    uri = os.environ.get('COMERCIAL_TEST_DATABASE_URL', 'sqlite:///:memory:')
    if uri != 'sqlite:///:memory:':
        from sqlalchemy.engine import make_url
        url = make_url(uri)
        assert url.host in {'127.0.0.1', 'localhost'}
        assert url.database == 'app360_paneles_test'
        assert url.port == 55439
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret')
    monkeypatch.setattr(Config, 'ADMIN_PASSWORD', 'admin')
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', uri)
    monkeypatch.setattr(Config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(Config, 'RATELIMIT_ENABLED', False)
    application = create_app()
    application.config['TESTING'] = True
    application.jinja_env.globals['csrf_token'] = lambda: 'test-csrf'
    with application.app_context():
        db.create_all()
        seed_vendedores_comerciales()
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session['user'] = 'test'
        session['role'] = 'admin'
    return client


BASE = '/api/comercial/performance'
PAGE = '/comercial/performance-vendedores'
QUERY = '?fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=TODAS'


def test_plantilla_ok_y_permiso(client, app):
    response = client.get(PAGE)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'comercial_performance.js' in html
    # Solo el rol con dashboard_comercial accede; hr no.
    with client.session_transaction() as session:
        session['role'] = 'hr'
    assert client.get(PAGE).status_code == 302
    with client.session_transaction() as session:
        session['role'] = 'direccion'
    assert client.get(PAGE).status_code == 200


def test_kpis_vendedores_y_granularidad(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 3), 'Ana', 'A', importe=100, cajas=1, kilos=10, producto='X', numero='a')
        agregar_pre(date(2024, 6, 10), 'Ana', 'B', importe=50, cajas=2, kilos=20, producto='Y', numero='b')
        agregar_pre(date(2024, 6, 10), 'Luis', 'A', importe=200, cajas=3, kilos=30, producto='X', numero='c')
        db.session.commit()

    data = client.get(BASE + QUERY).get_json()
    assert data['estado_datos'] == 'disponible'
    assert data['kpis']['importe']['actual'] == 350
    assert {v['vendedor']: v['importe'] for v in data['por_vendedor']} == {'Ana': 150, 'Luis': 200}
    ana = next(v for v in data['por_vendedor'] if v['vendedor'] == 'Ana')
    assert ana['pedidos'] == 2 and ana['ticket_promedio'] == 75.0
    assert {r['nombre'] for r in data['mix_empresa']} == {'CARNES', 'LACTEOS'}
    # Sin metas cargadas, la UI debe ocultar objetivos.
    assert data['tienen_meta'] is False

    mes = client.get(BASE + QUERY + '&granularidad=mes').get_json()
    assert mes['granularidad'] == 'mes'
    assert [p['fecha'] for p in mes['evolucion']['actual']] == ['2024-06']
    assert mes['evolucion']['actual'][0]['importe'] == 350

    semana = client.get(BASE + QUERY + '&granularidad=semana').get_json()
    assert semana['granularidad'] == 'semana'
    assert sum(p['importe'] for p in semana['evolucion']['actual']) == 350


def test_endpoint_compatibilidad_conserva_el_contrato(client):
    actual = client.get(BASE + QUERY)
    compatibilidad = client.get('/api/comercial/performance-vendedores' + QUERY)

    assert actual.status_code == 200
    assert compatibilidad.status_code == 200
    assert compatibilidad.get_json() == actual.get_json()


def test_vendedor_individual_recalcula(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 3), 'Ana', 'A', importe=100, cajas=1, kilos=10, producto='X', numero='a')
        agregar_pre(date(2024, 6, 10), 'Luis', 'B', importe=200, cajas=3, kilos=30, producto='Y', numero='b')
        db.session.commit()

    data = client.get(BASE + QUERY + '&vendedor=Ana').get_json()
    assert data['kpis']['importe']['actual'] == 100
    assert len(data['por_vendedor']) == 1
    assert data['por_vendedor'][0]['vendedor'] == 'Ana'
    assert data['por_vendedor'][0]['importe'] == 100


def test_objetivos_con_meta(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 3), 'Ana', 'A', importe=100, numero='a')
        vendedor = ComercialVendedor.query.filter_by(nombre_visible='Ana').first()
        if vendedor is None:
            vendedor = ComercialVendedor(nombre_visible='Ana', activo=True)
            db.session.add(vendedor)
            db.session.flush()
        db.session.add(ComercialObjetivo(vendedor_id=vendedor.id, empresa='CARNES', mes='2024-06',
                                         medida='importe', meta=200, descripcion='meta jun'))
        db.session.commit()

    # Con una sola empresa con meta, TODAS queda con cobertura incompleta.
    todas = client.get(BASE + QUERY).get_json()
    assert todas['tienen_meta'] is True
    incompleta = next(o for o in todas['objetivos'] if o['nombre_visible'] == 'Ana')
    assert incompleta['cobertura'] == 'incompleta'
    assert incompleta['cumplimiento'] is None

    # Con la empresa puntual, el cumplimiento se calcula.
    data = client.get(BASE + '?fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=CARNES').get_json()
    objetivo = next(o for o in data['objetivos'] if o['nombre_visible'] == 'Ana')
    assert objetivo['realizado'] == 100
    assert objetivo['meta'] == 200
    assert objetivo['cumplimiento'] == 0.5


def test_criterio_fac_por_cliente(client, app):
    with app.app_context():
        db.session.add(ComercialClienteCriterio(cliente='Factura', criterio='FAC', actualizado_por='test'))
        agregar_pre(date(2024, 6, 10), 'Ana', 'Factura', importe=999, numero='ignorar')
        agregar_pre(date(2024, 6, 10), 'Ana', 'Factura', importe=80, numero='fac')
        StgSabiogoVentas.query.filter_by(nro_comprob='fac').one().comprobante = 'FAC'
        db.session.commit()

    data = client.get(BASE + QUERY).get_json()
    assert data['kpis']['importe']['actual'] == 80


@pytest.mark.parametrize('suffix', ['&medida=x', '&granularidad=x'])
def test_validacion(client, suffix):
    assert client.get(BASE + QUERY + suffix).status_code == 400


@pytest.mark.parametrize('query', ['?fecha_desde=mal', '?fecha_desde=2024-07-01&fecha_hasta=2024-06-01', '?empresa=INVALIDA'])
def test_fechas_y_empresa_invalidas(client, query):
    assert client.get(BASE + query).status_code == 400


def test_error_no_devuelve_ceros(client, monkeypatch):
    import services.comercial_performance as service
    monkeypatch.setattr(service, 'calcular_cartera_comercial', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('fallo')))
    response = client.get(BASE + QUERY)
    assert response.status_code == 500
    assert 'kpis' not in response.get_json()
