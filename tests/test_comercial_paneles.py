"""Contratos de lectura de las pantallas comerciales separadas."""
from datetime import date

import pytest

import os
from app import create_app
from config import Config
from test_dashboard_equipo import agregar_pre
from services.vendedores_comerciales import seed_vendedores_comerciales
from models import db
from models.comercial import ComercialClienteCriterio
from models.sabiogo.staging import StgSabiogoVentas


@pytest.fixture
def app(monkeypatch):
    # Only an explicitly isolated local test database may be recreated.
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


BASE = '/api/comercial/seguimiento-clientes'
QUERY = '?fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=CARNES'


def test_actividad_limites_y_primera_global(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 1), 'Ana', '29 días', numero='a')
        agregar_pre(date(2024, 5, 31), 'Ana', '30 días', numero='b')
        agregar_pre(date(2024, 5, 1), 'Otro', 'Cambio vendedor', numero='c')
        agregar_pre(date(2024, 6, 29), 'Ana', 'Cambio vendedor', numero='d')
        agregar_pre(date(2024, 7, 1), 'Ana', 'Futuro', numero='e')
        db.session.commit()
    result = client.get(BASE + QUERY + '&vista=todos&vendedor=Ana').get_json()
    assert result['resumen']['total'] == 3
    assert result['resumen']['activos'] == 2
    assert result['resumen']['sin_compra'] == 1
    assert result['resumen']['nuevos'] == 1
    assert result['resumen']['tasa_actividad'] == pytest.approx(200 / 3)
    assert {f['cliente']: f['dias'] for f in result['clientes']} == {'29 días': 29, '30 días': 30, 'Cambio vendedor': 1}


def test_global_consolida_vendedores_y_senales(client, app):
    with app.app_context():
        agregar_pre(date(2024, 5, 10), 'Ana', 'Compartido', importe=100, producto='A', numero='a')
        agregar_pre(date(2024, 5, 11), 'Ana', 'Compartido', importe=100, producto='B', numero='b')
        agregar_pre(date(2024, 6, 10), 'Luis', 'Compartido', importe=100, producto='A', numero='c')
        db.session.commit()
    result = client.get(BASE + QUERY).get_json()
    assert result['total'] == result['resumen']['atencion'] == 1
    row = result['clientes'][0]
    assert row['vendedores'] == ['Ana', 'Luis']
    assert row['senales'] == ['Compra en baja', 'Menor variedad']
    assert row['activo'] is True
    assert row['comparacion']['diferencia'] == -100
    detail = client.get(BASE + '/detalle' + QUERY + '&cliente=Compartido').get_json()['cliente']
    assert detail['comparacion'] == row['comparacion']
    assert detail['variedad'] == {'actual': 1, 'anterior': 2}
    assert detail['serie'] == [{'fecha': '2024-06-10', 'importe': 100}]


def test_mover_vendedor_no_crea_sin_recompra_global(client, app):
    with app.app_context():
        agregar_pre(date(2024, 5, 10), 'Ana', 'Compartido', numero='a')
        agregar_pre(date(2024, 6, 10), 'Luis', 'Compartido', numero='b')
        db.session.commit()
    assert client.get(BASE + QUERY).get_json()['total'] == 0
    assert client.get(BASE + QUERY + '&vendedor=Ana').get_json()['total'] == 1


def test_opciones_clientes_y_productos_respetan_periodo_y_empresa(client, app):
    with app.app_context():
        agregar_pre(
            date(2024, 6, 10),
            'Ana',
            'Cliente del período',
            producto='Producto del período',
            numero='opcion-junio',
        )
        agregar_pre(
            date(2024, 5, 31),
            'Ana',
            'Cliente anterior',
            producto='Producto anterior',
            numero='opcion-mayo',
        )
        agregar_pre(
            date(2024, 6, 12),
            'Ana',
            'Cliente otra empresa',
            producto='Producto otra empresa',
            numero='opcion-lacteos',
        )
        StgSabiogoVentas.query.filter_by(nro_comprob='opcion-lacteos').one().origen = 'LACTEOS'
        db.session.commit()

    response = client.get(
        '/api/comercial/paneles/opciones',
        query_string={
            'fecha_desde': '2024-06-01',
            'fecha_hasta': '2024-06-30',
            'empresa': 'CARNES',
        },
    )

    assert response.status_code == 200
    opciones = response.get_json()
    assert opciones['clientes'] == ['Cliente del período']
    assert opciones['productos'] == ['Producto del período']


def test_criterios_empresas_y_aliases_fac(client, app):
    with app.app_context():
        db.session.add(ComercialClienteCriterio(cliente='Factura', criterio='FAC', actualizado_por='test'))
        agregar_pre(date(2024, 6, 10), 'BENJAMIN KALJA', 'Factura', importe=999, numero='ignorar')
        agregar_pre(date(2024, 6, 10), 'BENJAMIN KALJA', 'Factura', importe=80, numero='fac')
        fila = StgSabiogoVentas.query.filter_by(nro_comprob='fac').one()
        fila.comprobante = 'FAC'
        agregar_pre(date(2024, 6, 10), 'KALJA BENJAMIN', 'Pedido', importe=20, numero='pre')
        agregar_pre(date(2024, 6, 10), 'Otro', 'Lacteo', numero='lac')
        StgSabiogoVentas.query.filter_by(nro_comprob='lac').one().origen = 'LACTEOS'
        db.session.commit()
    result = client.get(BASE + QUERY + '&vista=todos&vendedor=Benjamín%20Kalja').get_json()
    assert result['resumen']['total'] == 2
    assert sum(f['importe'] for f in result['clientes']) == 100
    sales = client.get('/api/dashboard-comercial/resumen-estrategico' + QUERY + '&vendedor=Benjamín%20Kalja').get_json()
    assert sales['kpis']['importe']['actual'] == 100
    assert sales['kpis']['importe']['variacion_pct'] is None
    assert sales['kpis']['importe']['variacion_texto'] == 'Sin base comparable'


def test_paginacion_busqueda_orden_y_totales(client, app):
    with app.app_context():
        for i in range(57):
            agregar_pre(date(2024, 5, 10), 'Ana', f'Cliente {i:02}', importe=i + 1, numero=str(i))
        db.session.commit()
    first = client.get(BASE + QUERY).get_json()
    second = client.get(BASE + QUERY + '&pagina=2').get_json()
    third = client.get(BASE + QUERY + '&pagina=3').get_json()
    assert [len(r['clientes']) for r in (first, second, third)] == [25, 25, 7]
    assert len({f['cliente'] for r in (first, second, third) for f in r['clientes']}) == 57
    assert first['resumen'] == second['resumen'] == third['resumen']
    assert first['clientes'][0]['cliente'] == 'Cliente 56'
    assert len(client.get(BASE + QUERY + '&por_pagina=50').get_json()['clientes']) == 50
    assert client.get(BASE + QUERY + '&orden=cliente').get_json()['clientes'][0]['cliente'] == 'Cliente 00'
    search = client.get(BASE + QUERY + '&q=cliente%200').get_json()
    assert search['total'] == search['resumen']['total'] == 10
    empty = client.get(BASE + QUERY + '&vista=activos').get_json()
    assert empty['total'] == 0 and empty['resumen'] == first['resumen']


def test_nuevo_no_depende_de_empresa(client, app):
    with app.app_context():
        agregar_pre(date(2024, 3, 1), 'Ana', 'Existente', numero='a')
        StgSabiogoVentas.query.filter_by(nro_comprob='a').one().origen = 'LACTEOS'
        agregar_pre(date(2024, 6, 10), 'Ana', 'Existente', numero='b')
        db.session.commit()
    assert client.get(BASE + QUERY).get_json()['resumen']['nuevos'] == 0


def test_sin_base_y_sin_meta_y_filtros_estrategicos(client, app):
    with app.app_context():
        agregar_pre(date(2024, 6, 10), 'Fuera catalogo', 'Uno', importe=100, numero='a')
        agregar_pre(date(2024, 6, 12), 'Fuera catalogo', 'Dos', importe=200, numero='b')
        db.session.commit()
    result = client.get('/api/dashboard-comercial/resumen-estrategico' + QUERY + '&cliente=Uno').get_json()
    assert result['kpis']['importe']['actual'] == 100
    objetivo = next(o for o in result['objetivos'] if o['nombre_visible'] == 'Fuera catalogo')
    assert objetivo['realizado'] == 300
    assert objetivo['meta'] is objetivo['cumplimiento'] is objetivo['diferencia_meta'] is None
    assert 'cartera' not in result and 'clientes_atencion' not in result
    assert result['composicion']['cliente'][0]['nombre'] == 'Uno'


def test_ranking_incluye_otros(client, app):
    with app.app_context():
        for i in range(12):
            agregar_pre(date(2024, 6, 10), 'Ana', str(i), producto=str(i), numero=str(i))
        db.session.commit()
    result = client.get('/api/dashboard-comercial/resumen-estrategico' + QUERY).get_json()
    rows = result['composicion']['cliente']
    assert len(rows) == 9 and rows[-1]['nombre'] == 'Otros'
    assert sum(r['plata'] for r in rows) == result['kpis']['importe']['actual']
    detail_rows = result['composicion_detalle']['cliente']
    assert len(detail_rows) == 12
    assert all(row['nombre'] != 'Otros' for row in detail_rows)


def test_tabla_composicion_acepta_limites_y_default_de_10(client):
    script = client.get('/static/js/comercial_paneles.js').get_data(as_text=True)
    assert 'const COMPOSITION_ROW_LIMITS = [10, 20, 50, 100];' in script
    assert 'COMPOSITION_ROW_LIMITS.forEach(limit => {' in script
    assert 'select.add(new Option(String(limit), String(limit)))' in script
    assert "select.value = String(COMPOSITION_ROW_LIMITS[0]);" in script
    assert 'rows.slice(0, Number(select.value))' in script


@pytest.mark.parametrize('suffix', ['&por_pagina=0', '&por_pagina=100', '&pagina=-1', '&pagina=x', '&orden=otro', '&vista=otro'])
def test_validacion(client, suffix):
    assert client.get(BASE + QUERY + suffix).status_code == 400


@pytest.mark.parametrize('query', ['?fecha_desde=mal', '?fecha_desde=2024-07-01&fecha_hasta=2024-06-01', '?empresa=INVALIDA'])
def test_fechas_y_empresa_invalidas(client, query):
    assert client.get(BASE + query).status_code == 400


def test_vacio_y_detalle_inexistente(client):
    result = client.get(BASE + QUERY).get_json()
    assert result['resumen']['total'] == 0
    assert result['resumen']['tasa_actividad'] is None
    assert result['clientes'] == []
    assert client.get(BASE + '/detalle' + QUERY + '&cliente=Inexistente').get_json()['cliente'] is None


def test_error_no_devuelve_ceros(client, monkeypatch):
    import services.comercial_paneles as service
    monkeypatch.setattr(service, '_historial', lambda *args: (_ for _ in ()).throw(RuntimeError('fallo')))
    response = client.get(BASE + QUERY)
    assert response.status_code == 500
    assert 'resumen' not in response.get_json()


@pytest.mark.parametrize('path', ['/comercial/seguimiento-clientes', BASE, BASE + '/detalle?cliente=X', '/api/dashboard-comercial/resumen-estrategico', '/api/comercial/paneles/opciones'])
def test_permiso_existente_y_sin_ampliacion(client, path):
    with client.session_transaction() as session:
        session['role'] = 'hr'
    denied = client.get(path)
    assert denied.status_code == 302
    with client.session_transaction() as session:
        session['role'] = 'direccion'
    allowed = client.get(path)
    assert allowed.status_code == 200


def test_plantillas_y_navegacion(client):
    for path in ['/dashboard-comercial', '/comercial/seguimiento-clientes']:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert html.index('>Comercial</div>') < html.index('href="/ventas/criterio-clientes"')
        assert 'comercial_paneles.js' in html


def test_postgres_fechas_con_hora_incluyen_dia_de_corte(client, app):
    from sqlalchemy import text
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('Compatibilidad con esquema timestamp de PostgreSQL')
        db.session.execute(text('ALTER TABLE stg_sabiogo_ventas ALTER COLUMN fecha TYPE timestamp USING fecha::timestamp'))
        agregar_pre(date(2024, 6, 30), 'Ana', 'Compra tarde', numero='tarde')
        db.session.flush()
        db.session.execute(text("UPDATE stg_sabiogo_ventas SET fecha = '2024-06-30 23:59:00' WHERE nro_comprob = 'tarde'"))
        db.session.commit()
    result = client.get(BASE + QUERY + '&vista=todos')
    assert result.status_code == 200
    assert result.get_json()['clientes'][0]['dias'] == 0
    assert result.get_json()['resumen']['nuevos'] == 1
    sales = client.get('/api/dashboard-comercial/resumen-estrategico' + QUERY)
    assert sales.status_code == 200
    assert sales.get_json()['kpis']['importe']['actual'] == 100
    assert sales.get_json()['serie'][0]['fecha'] == '2024-06-30'
