"""Criterio de clientes PRE / FAC / AMBOS y etiqueta de origen en Seguimiento de clientes.

Conjunto de datos conocido (junio de 2024, empresa CARNES; período anterior 2/5 al 31/5).
Los importes esperados están calculados a mano:

  Mixto (AMBOS)   PRE 5/6 $100 (P1) · PRE 10/6 $50 (P2) · FCM 20/6 $300 + $40 (F1, dos líneas)
                  NPF 25/6 -$30 (N1)
                  -> PRE: 2 op. $150 · FAC: 1 op. $340 · total que suma $490 · NC listada, no suma
                  -> última compra 20/6 (FAC); la NC del 25/6 no cuenta como compra
  SoloPre (sin fila) PRE 12/6 $100 · FCM 13/6 $999 (se ignora)            -> $100
  SoloFac (FAC)   FCM 12/6 $200 · PRE 14/6 $777 (se ignora) · NPF 15/6 -$20  -> $180 (como hoy)
  Transicion (AMBOS) PRE 30/5 $60 (período anterior) · FCM 3/6 $500       -> actual $500, anterior $60
"""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from config import Config
from models import db
from models.comercial import ComercialClienteCriterio
from models.sabiogo.staging import StgSabiogoVentas
from services.comercial_criterios import (
    CRITERIOS_VALIDOS,
    filtro_comprobante_panel_ventas,
    normalizar_criterio,
    tipo_origen,
)
from services.comercial_paneles import seguimiento_clientes
from services.comercial_pre import calcular_resumen_pre
from services.vendedores_comerciales import seed_vendedores_comerciales
from sesion_de_prueba import cambiar_usuario

BASE = '/api/comercial/seguimiento-clientes'
QUERY = '?fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=CARNES&vista=todos'


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret')
    monkeypatch.setattr(Config, 'ADMIN_PASSWORD', 'admin')
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
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
def cliente_http(app):
    cli = app.test_client()
    with cli.session_transaction() as sesion:
        sesion['user'] = 'test'
        sesion['role'] = 'admin'
    return cli


def linea(fecha, cliente, comprobante, numero, importe, producto='Producto'):
    db.session.add(StgSabiogoVentas(
        fecha=fecha, origen='CARNES', codigo=f'{numero}-{producto}', producto=producto,
        cliente=cliente, vendedor='Ana', subtot=importe, cajas=1, kilos=10,
        comprobante=comprobante, nro_comprob=numero, estado='procesado'))


def sembrar_datos(criterios):
    linea(date(2024, 6, 5), 'Mixto', 'PRE', 'P1', 100)
    linea(date(2024, 6, 10), 'Mixto', 'PRE', 'P2', 50)
    linea(date(2024, 6, 20), 'Mixto', 'FCM', 'F1', 300, 'Producto A')
    linea(date(2024, 6, 20), 'Mixto', 'FCM', 'F1', 40, 'Producto B')
    linea(date(2024, 6, 25), 'Mixto', 'NPF', 'N1', -30)
    linea(date(2024, 6, 12), 'SoloPre', 'PRE', 'P3', 100)
    linea(date(2024, 6, 13), 'SoloPre', 'FCM', 'F2', 999)
    linea(date(2024, 6, 12), 'SoloFac', 'FCM', 'F3', 200)
    linea(date(2024, 6, 14), 'SoloFac', 'PRE', 'P4', 777)
    linea(date(2024, 6, 15), 'SoloFac', 'NPF', 'N2', -20)
    linea(date(2024, 5, 30), 'Transicion', 'PRE', 'P5', 60)
    linea(date(2024, 6, 3), 'Transicion', 'FCM', 'F4', 500)
    for nombre, criterio in criterios.items():
        db.session.add(ComercialClienteCriterio(cliente=nombre, criterio=criterio, actualizado_por='test'))
    db.session.commit()


CRITERIOS = {'Mixto': 'AMBOS', 'SoloFac': 'FAC', 'Transicion': 'AMBOS'}


def por_cliente(cli, extra=''):
    datos = cli.get(BASE + QUERY + extra).get_json()
    return {fila['cliente']: fila for fila in datos['clientes']}


# --- Seguimiento: los tres modos --------------------------------------------------------

def test_ambos_suma_pre_y_fac_por_separado_y_lista_la_nc(app, cliente_http):
    with app.app_context():
        sembrar_datos(CRITERIOS)
    mixto = por_cliente(cliente_http)['Mixto']
    assert mixto['criterio'] == 'AMBOS' and mixto['mostrar_origen'] is True
    assert mixto['por_tipo'] == {'PRE': {'n': 2, 'importe': 150.0}, 'FAC': {'n': 1, 'importe': 340.0}}
    assert mixto['importe'] == 490.0  # la NC (-30) no entra en el total
    assert mixto['ultima_compra'] == '2024-06-20'
    assert mixto['ultima_compra_tipos'] == ['FAC']

    detalle = cliente_http.get('/api/comercial/seguimiento-clientes/detalle'
                               '?fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=CARNES&cliente=Mixto').get_json()
    ops = detalle['cliente']['operaciones']
    assert [(o['fecha'], o['tipo'], o['nro'], o['importe']) for o in ops] == [
        ('2024-06-25', 'NC', 'N1', -30.0),
        ('2024-06-20', 'FAC', 'F1', 340.0),
        ('2024-06-10', 'PRE', 'P2', 50.0),
        ('2024-06-05', 'PRE', 'P1', 100.0),
    ]
    assert detalle['cliente']['operaciones_total'] == 4
    assert sum(o['importe'] for o in ops if o['tipo'] != 'NC') == mixto['importe']


def test_ultima_compra_mas_reciente_entre_ambos_tipos(app, cliente_http):
    with app.app_context():
        sembrar_datos({'Mixto': 'AMBOS'})
        linea(date(2024, 6, 28), 'Mixto', 'PRE', 'P9', 10)
        db.session.commit()
    mixto = por_cliente(cliente_http)['Mixto']
    assert mixto['ultima_compra'] == '2024-06-28' and mixto['ultima_compra_tipos'] == ['PRE']
    with app.app_context():
        linea(date(2024, 6, 28), 'Mixto', 'FCM', 'F9', 5)
        db.session.commit()
    mixto = por_cliente(cliente_http)['Mixto']
    assert mixto['ultima_compra_tipos'] == ['PRE', 'FAC']  # mismo día: se muestran ambas


def test_cliente_que_pasa_de_pre_a_factura(app, cliente_http):
    with app.app_context():
        sembrar_datos(CRITERIOS)
    fila = por_cliente(cliente_http)['Transicion']
    assert fila['importe'] == 500.0
    assert fila['comparacion']['anterior'] == 60.0
    assert fila['por_tipo'] == {'PRE': {'n': 0, 'importe': 0.0}, 'FAC': {'n': 1, 'importe': 500.0}}
    assert fila['ultima_compra'] == '2024-06-03' and fila['ultima_compra_tipos'] == ['FAC']


def test_pre_y_fac_conservan_sus_numeros_y_no_muestran_origen(app, cliente_http):
    with app.app_context():
        sembrar_datos(CRITERIOS)
    filas = por_cliente(cliente_http)
    # Sin fila = PRE: solo cuenta PRE (la FCM de $999 se ignora)
    assert filas['SoloPre']['importe'] == 100.0
    assert filas['SoloPre']['criterio'] == 'PRE' and filas['SoloPre']['mostrar_origen'] is False
    assert filas['SoloPre']['ultima_compra'] == '2024-06-12'
    # FAC: igual que antes, la NPF resta (200 - 20) y no se cuenta el PRE de $777
    assert filas['SoloFac']['importe'] == 180.0
    assert filas['SoloFac']['criterio'] == 'FAC' and filas['SoloFac']['mostrar_origen'] is False
    assert filas['SoloFac']['ultima_compra'] == '2024-06-15'


def test_cambiar_el_modo_cambia_lo_que_se_ve(app, cliente_http):
    with app.app_context():
        sembrar_datos({})
        modo = {}
        for criterio in ('PRE', 'FAC', 'AMBOS'):
            ComercialClienteCriterio.query.filter_by(cliente='Mixto').delete()
            if criterio != 'PRE':
                db.session.add(ComercialClienteCriterio(cliente='Mixto', criterio=criterio, actualizado_por='t'))
            db.session.commit()
            modo[criterio] = por_cliente(cliente_http)['Mixto']['importe']
    # PRE: 100+50 · FAC (todo lo no PRE, con la NPF como siempre): 340-30 · AMBOS: 150+340
    assert modo == {'PRE': 150.0, 'FAC': 310.0, 'AMBOS': 490.0}


def test_nc_de_cliente_ambos_sin_otras_compras_no_crea_cliente(app, cliente_http):
    with app.app_context():
        linea(date(2024, 6, 10), 'Solo NC', 'NPF', 'N9', -50)
        db.session.add(ComercialClienteCriterio(cliente='Solo NC', criterio='AMBOS', actualizado_por='t'))
        db.session.commit()
    assert 'Solo NC' not in por_cliente(cliente_http)


def test_nombre_de_cliente_con_html_llega_como_dato(app, cliente_http):
    nombre = '<img src=x onerror=alert(1)>'
    with app.app_context():
        linea(date(2024, 6, 10), nombre, 'PRE', 'X1', 10)
        db.session.add(ComercialClienteCriterio(cliente=nombre, criterio='AMBOS', actualizado_por='t'))
        db.session.commit()
    assert nombre in por_cliente(cliente_http)
    html = cliente_http.get('/ventas/criterio-clientes').get_data(as_text=True)
    assert nombre not in html  # nunca se incrusta en el HTML del servidor
    datos = cliente_http.get('/ventas/criterio-clientes/datos').get_json()['clientes']
    assert {'cliente': nombre, 'criterio': 'AMBOS'}.items() <= next(f for f in datos if f['cliente'] == nombre).items()


def test_pantallas_escapan_el_nombre_y_usan_etiquetas_en_texto():
    # Las plantillas arman filas con escapeHtml / textContent: sin innerHTML de datos de cliente.
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    criterio = (raiz / 'templates' / 'criterio_clientes.html').read_text(encoding='utf-8')
    assert 'escapeHtml(row.cliente)' in criterio and 'value="AMBOS"' in criterio
    js = (raiz / 'static' / 'js' / 'comercial_paneles.js').read_text(encoding='utf-8')
    assert "const origen = tipo => { const b = badge(tipo," in js and "innerHTML" not in js[js.index('const origen'):js.index('const origen') + 400]


# --- Otros consumidores: PRE y FAC iguales; AMBOS = PRE + no PRE sin NPF -----------------

def test_filtro_por_modo_en_resumen_y_panel_de_ventas(app, cliente_http):
    with app.app_context():
        sembrar_datos(CRITERIOS)
        resumen = calcular_resumen_pre(date(2024, 6, 1), date(2024, 6, 30), empresa='CARNES',
                                       criterio_clientes=True, limite=100)
        por = {f['nombre']: f for f in resumen['por_cliente']}
        assert por['Mixto']['plata'] == 490.0       # AMBOS: 150 + 340, sin la NPF
        assert por['SoloPre']['plata'] == 100.0     # PRE: igual que antes
        assert por['SoloFac']['plata'] == 180.0     # FAC: igual que antes (con NPF)
        assert por['Transicion']['plata'] == 500.0
        # Sin criterio_clientes (comisiones y objetivos) sigue siendo solo PRE
        solo_pre = calcular_resumen_pre(date(2024, 6, 1), date(2024, 6, 30), empresa='CARNES', limite=100)
        pre = {f['nombre']: f['plata'] for f in solo_pre['por_cliente']}
        assert pre['Mixto'] == 150.0 and pre['SoloFac'] == 777.0 and pre['SoloPre'] == 100.0
    kpis = cliente_http.get('/api/dashboard-comercial/resumen-estrategico'
                            '?fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=CARNES&cliente=Mixto').get_json()['kpis']
    assert kpis['importe']['actual'] == 490.0


def test_filtro_sin_nc_para_ambos_y_con_nc_para_listar(app):
    with app.app_context():
        sembrar_datos(CRITERIOS)
        sin_nc = {f.nro_comprob for f in StgSabiogoVentas.query.filter(filtro_comprobante_panel_ventas()).all()
                  if f.cliente == 'Mixto'}
        con_nc = {f.nro_comprob for f in StgSabiogoVentas.query.filter(
            filtro_comprobante_panel_ventas(incluir_nc_ambos=True)).all() if f.cliente == 'Mixto'}
        assert sin_nc == {'P1', 'P2', 'F1'} and con_nc == {'P1', 'P2', 'F1', 'N1'}


def test_clasificacion_y_validacion_de_valores():
    assert CRITERIOS_VALIDOS == ('PRE', 'FAC', 'AMBOS')
    assert [normalizar_criterio(v) for v in ('pre', ' Fac ', 'AMBOS', 'ambos')] == ['PRE', 'FAC', 'AMBOS', 'AMBOS']
    assert [normalizar_criterio(v) for v in (None, '', 'XYZ', 'PRE,FAC', ['PRE'], 'TODOS')] == [None] * 6
    assert [tipo_origen(v) for v in ('PRE', ' pre ', 'FCM', 'npf', '', None)] == ['PRE', 'PRE', 'FAC', 'NC', None, None]


# --- Pantalla «Criterio de clientes»: guardado, validación, permisos, CSRF -------------

def test_guardar_ambos_y_rechazar_valores_invalidos(app, cliente_http):
    with app.app_context():
        sembrar_datos({})
    ok = cliente_http.post('/ventas/criterio-clientes/guardar', json={'clientes': ['Mixto', 'SoloPre'], 'criterio': 'ambos'})
    assert ok.status_code == 200 and ok.get_json()['criterio'] == 'AMBOS'
    datos = {f['cliente']: f['criterio'] for f in cliente_http.get('/ventas/criterio-clientes/datos').get_json()['clientes']}
    assert datos['Mixto'] == datos['SoloPre'] == 'AMBOS'
    assert datos['SoloFac'] == 'PRE'  # sin fila = PRE
    for malo in ('XYZ', 'PRE,FAC', '', None, 5, ['AMBOS']):
        r = cliente_http.post('/ventas/criterio-clientes/guardar', json={'clientes': ['Mixto'], 'criterio': malo})
        assert r.status_code == 400, malo
    with app.app_context():
        assert ComercialClienteCriterio.query.filter_by(cliente='Mixto').one().criterio == 'AMBOS'


def test_la_base_rechaza_un_valor_fuera_de_lista(app):
    with app.app_context():
        db.session.add(ComercialClienteCriterio(cliente='X', criterio='AMBOS', actualizado_por='t'))
        db.session.commit()
        db.session.add(ComercialClienteCriterio(cliente='Y', criterio='TODOS', actualizado_por='t'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_pantalla_ofrece_las_tres_opciones(cliente_http):
    html = cliente_http.get('/ventas/criterio-clientes').get_data(as_text=True)
    for texto in ('value="PRE"', 'value="FAC"', 'value="AMBOS"', 'Usar presupuesto', 'Usar facturación', 'Usar ambos'):
        assert texto in html


def test_permisos_anonimo_y_rol_sin_acceso(app):
    anonimo = app.test_client()
    assert anonimo.get('/ventas/criterio-clientes').status_code in (301, 302, 401, 403)
    r = anonimo.post('/ventas/criterio-clientes/guardar', json={'clientes': ['Mixto'], 'criterio': 'AMBOS'})
    assert r.status_code in (301, 302, 401, 403)
    cli = app.test_client()
    cambiar_usuario(cli, 1, username='sin_acceso', role='rrhh')
    assert cli.post('/ventas/criterio-clientes/guardar',
                    json={'clientes': ['Mixto'], 'criterio': 'AMBOS'}).status_code in (302, 401, 403)
    with app.app_context():
        assert ComercialClienteCriterio.query.count() == 0


def test_csrf_se_exige_al_guardar(monkeypatch):
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret')
    monkeypatch.setattr(Config, 'ADMIN_PASSWORD', 'admin')
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(Config, 'WTF_CSRF_ENABLED', True)
    monkeypatch.setattr(Config, 'RATELIMIT_ENABLED', False)
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=True, WTF_CSRF_SSL_STRICT=False)
    with application.app_context():
        db.create_all()
        cli = application.test_client()
        cambiar_usuario(cli, 1, username='Ciro', role='sales')
        r = cli.post('/ventas/criterio-clientes/guardar', json={'clientes': ['Mixto'], 'criterio': 'AMBOS'})
        assert r.status_code == 400
        assert ComercialClienteCriterio.query.count() == 0
        db.session.remove()
        db.drop_all()
