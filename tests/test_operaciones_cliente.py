"""Operaciones de un cliente en el desplegable de Seguimiento de clientes (20 por vez).

Datos (junio de 2024, empresa CARNES), importes a mano:
  Mixto (AMBOS): PRE 5/6 $100 (P1) · PRE 10/6 $50 (P2) · FCM 20/6 $300 + $40 (F1) · NPF 25/6 -$30 (N1)
                 línea sin código de comprobante 26/6 $7 (S1)
  SoloPre (sin fila): PRE 12/6 $100 (P3) · FCM 13/6 $999 (F2) · NPF 14/6 $20 (N2, guardada en positivo)
  SoloFac (FAC): FCM 12/6 $200 (F3) · PRE 14/6 $777 (P4) · NPF 15/6 -$20 (N3)
"""
from datetime import date, timedelta
from urllib.parse import quote

import pytest

import services.comercial_operaciones as ops
from app import create_app
from config import Config
from models import db
from models.comercial import ComercialClienteCriterio
from models.sabiogo.staging import StgSabiogoVentas
from services.vendedores_comerciales import seed_vendedores_comerciales
from sesion_de_prueba import asegurar_usuario, marcar_sesion

URL = '/api/comercial/seguimiento-clientes/operaciones'
PERIODO = '&fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=CARNES'


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret')
    monkeypatch.setattr(Config, 'ADMIN_PASSWORD', 'admin')
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(Config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(Config, 'RATELIMIT_ENABLED', False)
    application = create_app()
    application.config['TESTING'] = True
    with application.app_context():
        db.create_all()
        seed_vendedores_comerciales()
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()  # conftest.py le inyecta la sesión admin


def linea(fecha, cliente, comprobante, nro, importe, vendedor='KALJA BENJAMIN', producto='P'):
    db.session.add(StgSabiogoVentas(
        fecha=fecha, origen='CARNES', codigo=f'{nro}-{producto}', producto=producto, cliente=cliente,
        vendedor=vendedor, subtot=importe, cajas=1, kilos=1, comprobante=comprobante, nro_comprob=nro,
        estado='procesado'))


@pytest.fixture
def datos(app):
    linea(date(2024, 6, 5), 'Mixto', 'PRE', 'P1', 100)
    linea(date(2024, 6, 10), 'Mixto', 'PRE', 'P2', 50)
    linea(date(2024, 6, 20), 'Mixto', 'FCM', 'F1', 300, producto='A')
    linea(date(2024, 6, 20), 'Mixto', 'FCM', 'F1', 40, producto='B')
    linea(date(2024, 6, 25), 'Mixto', 'NPF', 'N1', -30)
    linea(date(2024, 6, 26), 'Mixto', None, 'S1', 7)
    linea(date(2024, 6, 12), 'SoloPre', 'PRE', 'P3', 100)
    linea(date(2024, 6, 13), 'SoloPre', 'FCM', 'F2', 999)
    linea(date(2024, 6, 14), 'SoloPre', 'NPF', 'N2', 20)
    linea(date(2024, 6, 12), 'SoloFac', 'FCM', 'F3', 200, vendedor='ARIAS ANA')
    linea(date(2024, 6, 14), 'SoloFac', 'PRE', 'P4', 777)
    linea(date(2024, 6, 15), 'SoloFac', 'NPF', 'N3', -20)
    db.session.add(ComercialClienteCriterio(cliente='Mixto', criterio='AMBOS', actualizado_por='t'))
    db.session.add(ComercialClienteCriterio(cliente='SoloFac', criterio='FAC', actualizado_por='t'))
    db.session.commit()


def lista(client, cliente, extra=''):
    r = client.get(f'{URL}?cliente={quote(cliente)}&{extra}')
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def resumen(datos_json):
    return [(o['fecha'], o['tipo'], o['nro'], o['importe'], o['cuenta_en_totales']) for o in datos_json['operaciones']]


def test_modo_criterio_ambos_trae_pre_fac_y_nc_en_orden_descendente(client, datos):
    r = lista(client, 'Mixto', PERIODO.lstrip('&'))
    assert r['criterio'] == 'AMBOS' and r['modo'] == 'criterio' and r['hay_mas'] is False
    assert resumen(r) == [
        ('2024-06-25', 'NC', 'N1', -30.0, False),   # NC: se lista, no suma
        ('2024-06-20', 'FAC', 'F1', 340.0, True),   # dos líneas = una operación
        ('2024-06-10', 'PRE', 'P2', 50.0, True),
        ('2024-06-05', 'PRE', 'P1', 100.0, True),
    ]
    assert r['operaciones'][1]['lineas'] == 2 and r['operaciones'][1]['comprobante'] == 'FCM'


def test_modo_criterio_pre_y_fac_respetan_su_criterio(client, datos):
    pre = lista(client, 'SoloPre', PERIODO.lstrip('&'))
    assert resumen(pre) == [('2024-06-12', 'PRE', 'P3', 100.0, True)]
    fac = lista(client, 'SoloFac', PERIODO.lstrip('&'))
    assert resumen(fac) == [('2024-06-15', 'NC', 'N3', -20.0, True), ('2024-06-12', 'FAC', 'F3', 200.0, True)]


def test_todos_los_comprobantes_incluye_lo_que_el_criterio_excluye(client, datos):
    pre = lista(client, 'SoloPre', PERIODO.lstrip('&') + '&modo=todos')
    assert resumen(pre) == [
        ('2024-06-14', 'NC', 'N2', -20.0, False),   # NPF guardada en positivo: se muestra en negativo
        ('2024-06-13', 'FAC', 'F2', 999.0, False),  # FCM de un cliente PRE: visible, no suma
        ('2024-06-12', 'PRE', 'P3', 100.0, True),
    ]
    mixto = lista(client, 'Mixto', PERIODO.lstrip('&') + '&modo=todos')
    assert ('2024-06-26', 'OTRO', 'S1', 7.0, False) in resumen(mixto)  # sin código de comprobante: tolerado
    assert len(mixto['operaciones']) == 5
    fac = lista(client, 'SoloFac', PERIODO.lstrip('&') + '&modo=todos')
    assert ('2024-06-14', 'PRE', 'P4', 777.0, False) in resumen(fac)


def test_tipo_desconocido_se_tolera(client, app, datos):
    with app.app_context():
        linea(date(2024, 6, 27), 'SoloPre', 'ZZZ', 'Z1', 5)
        db.session.commit()
    r = lista(client, 'SoloPre', PERIODO.lstrip('&') + '&modo=todos')
    assert r['operaciones'][0]['nro'] == 'Z1' and r['operaciones'][0]['comprobante'] == 'ZZZ'


def test_paginacion_de_a_20_sin_repetidos(client, app):
    with app.app_context():
        for i in range(45):
            linea(date(2024, 6, 1) + timedelta(days=i % 28), 'Grande', 'PRE', f'G{i:02}', 10 + i)
        db.session.commit()
    p1 = lista(client, 'Grande', PERIODO.lstrip('&'))
    assert len(p1['operaciones']) == 20 and p1['hay_mas'] and p1['siguiente'] == 20
    p2 = lista(client, 'Grande', PERIODO.lstrip('&') + '&desplazamiento=20')
    p3 = lista(client, 'Grande', PERIODO.lstrip('&') + '&desplazamiento=40')
    assert [len(p2['operaciones']), len(p3['operaciones'])] == [20, 5] and p2['hay_mas'] and not p3['hay_mas']
    todos = p1['operaciones'] + p2['operaciones'] + p3['operaciones']
    assert len({o['nro'] for o in todos}) == 45
    assert [o['fecha'] for o in todos] == sorted((o['fecha'] for o in todos), reverse=True)
    assert abs(sum(o['importe'] for o in todos) - sum(10 + i for i in range(45))) < 1e-9


def test_rango_de_fechas_y_vendedor_y_empresa(client, datos):
    r = lista(client, 'Mixto', 'fecha_desde=2024-06-06&fecha_hasta=2024-06-20&empresa=CARNES')
    assert [o['nro'] for o in r['operaciones']] == ['F1', 'P2']
    assert lista(client, 'Mixto', 'fecha_desde=2024-07-01&fecha_hasta=2024-07-31')['operaciones'] == []
    ana = lista(client, 'SoloFac', PERIODO.lstrip('&') + '&vendedor=ARIAS ANA&modo=todos')
    assert [o['nro'] for o in ana['operaciones']] == ['F3']  # el filtro de vendedor del panel se respeta
    assert lista(client, 'Mixto', 'fecha_desde=2024-06-01&fecha_hasta=2024-06-30&empresa=LACTEOS')['operaciones'] == []


def test_cliente_inexistente_devuelve_lista_vacia(client, datos):
    r = lista(client, 'No existe', PERIODO.lstrip('&'))
    assert r['operaciones'] == [] and r['hay_mas'] is False


@pytest.mark.parametrize('query', [
    'cliente=', 'modo=otro', 'limite=0', 'limite=51', 'limite=x', 'desplazamiento=-1', 'desplazamiento=x',
    'desplazamiento=999999999', 'fecha_desde=2024-06-30&fecha_hasta=2024-06-01', 'fecha_desde=nope',
    'empresa=OTRA', 'cliente=' + 'x' * 201,
])
def test_parametros_invalidos_dan_400_json(client, datos, query):
    base = '' if query.startswith('cliente=') else 'cliente=Mixto&'
    r = client.get(f'{URL}?{base}{query}')
    assert r.status_code == 400 and r.is_json and 'error' in r.get_json()


def test_sin_cliente_da_400(client):
    assert client.get(URL).status_code == 400


NOMBRES = ["O'Brien & Hijos", 'Ñandú 100%_x', '50% "off" ; DROP TABLE x;--', '<img src=x onerror=alert(1)>',
           'Cliente\\barra', 'Zürich 北京']


@pytest.mark.parametrize('nombre', NOMBRES)
def test_nombres_raros_se_parametrizan_y_viajan_como_dato(client, app, nombre):
    with app.app_context():
        linea(date(2024, 6, 10), '  ' + nombre + ' ', 'PRE', 'R1', 11)   # el panel agrupa por TRIM(cliente)
        linea(date(2024, 6, 10), 'Otro cliente', 'PRE', 'R2', 99)
        db.session.commit()
    r = client.get(URL, query_string={'cliente': nombre, 'fecha_desde': '2024-06-01', 'fecha_hasta': '2024-06-30'})
    assert r.status_code == 200
    assert [o['nro'] for o in r.get_json()['operaciones']] == ['R1']
    assert r.get_json()['cliente'] == nombre
    # LIKE no es comodín: «%» y «_» se comparan literalmente
    assert client.get(URL, query_string={'cliente': '%', 'fecha_desde': '2024-06-01',
                                         'fecha_hasta': '2024-06-30'}).get_json()['operaciones'] == []


def test_la_lista_se_arma_con_textContent_sin_innerHTML():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / 'static' / 'js' / 'comercial_paneles.js').read_text(encoding='utf-8')
    bloque = js[js.index('function renderOperaciones'):js.index('function closeDetail')]
    assert 'innerHTML' not in bloque and 'insertAdjacentHTML' not in bloque
    assert 'Ver todos los comprobantes' in bloque and 'Ver más' in bloque
    assert 'Este cliente no tiene operaciones en el período.' in bloque
    assert 'Muestra ventas, presupuestos, facturas y notas de crédito tal como están en SabioGo.' in bloque
    assert 'Los totales del panel cuentan según el criterio del cliente.' in bloque


# --- Permisos ----------------------------------------------------------------------------

def test_anonimo_recibe_401_json(app, datos):
    r = app.test_client().get(f'{URL}?cliente=Mixto')
    assert r.status_code == 401 and r.is_json


def test_rol_sin_acceso_al_panel_recibe_403_json(app, datos):
    asegurar_usuario(app, 2, 'rrhh1', 'rrhh')
    cli = app.test_client()
    marcar_sesion(cli, 2)
    r = cli.get(f'{URL}?cliente=Mixto')
    assert r.status_code == 403 and r.is_json


@pytest.mark.parametrize('rol', ['sales', 'admin', 'gerente', 'direccion'])
def test_roles_con_acceso_al_panel_ven_operaciones(app, datos, rol):
    asegurar_usuario(app, 3, f'u_{rol}', rol)
    cli = app.test_client()
    marcar_sesion(cli, 3)
    r = cli.get(f'{URL}?cliente=Mixto' + PERIODO)
    assert r.status_code == 200 and len(r.get_json()['operaciones']) == 4


def test_alcance_por_vendedor_se_aplica_en_el_servidor(client, app, datos, monkeypatch):
    """Punto de enforcement: cuando haya vínculo usuario-vendedor, el filtro del servidor anula el query string."""
    monkeypatch.setattr(ops, 'vendedor_restringido_actual', lambda: 'ARIAS ANA')
    ajeno = lista(client, 'Mixto', PERIODO.lstrip('&') + '&vendedor=KALJA BENJAMIN&modo=todos')
    inexistente = lista(client, 'No existe', PERIODO.lstrip('&'))
    assert ajeno['operaciones'] == inexistente['operaciones'] == []   # mismo resultado: no revela si existe
    propio = lista(client, 'SoloFac', PERIODO.lstrip('&') + '&vendedor=KALJA BENJAMIN&modo=todos')
    assert [o['nro'] for o in propio['operaciones']] == ['F3']       # el vendedor del query string se ignora
