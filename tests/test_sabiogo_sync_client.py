import configparser
import json
import sys
import types
from datetime import date

import pytest

from scripts.sabiogo_sync import sync


def make_config():
    cfg = configparser.ConfigParser()
    cfg.read_dict({
        'firebird': {
            'host': 'localhost',
            'port': '3050',
            'database': 'VYP',
            'user': 'reader',
            'password': 'secret',
            'client_library': '',
        },
        'vps': {
            'url': 'https://app360.example',
            'api_key': 'sync-secret',
            'timeout_seconds': '30',
            'max_retries': '2',
            'backoff_factor': '0',
            'origenes': 'CARNES,LACTEOS',
        },
    })
    return cfg


def success_response(tipo, fecha, total_filas):
    return {
        'success': True,
        'tipo': tipo,
        'fecha': fecha.isoformat(),
        'total_filas': total_filas,
        'resultados': {},
        'errores': None,
        'replace': True,
    }


def daily_success_response(fecha, ventas_total, compras_total):
    return {
        'success': True,
        'fecha': fecha.isoformat(),
        'total_filas': {
            'ventas': ventas_total,
            'compras': compras_total,
            'total': ventas_total + compras_total,
        },
        'resultados': {'ventas': {}, 'compras': {}},
        'errores': None,
        'replace': True,
    }


def test_query_compras_configura_servidor_y_procedimiento(monkeypatch):
    calls = {}

    class Option:
        value = None

    class Cursor:
        description = [('EMPRESA',), ('FECHA',)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            calls['sql'] = sql
            calls['params'] = params

        def fetchall(self):
            return [('VYP', date(2026, 5, 4))]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    driver_module = types.ModuleType('firebird.driver')
    driver_module.driver_config = types.SimpleNamespace(
        fb_client_library=Option(),
        server_defaults=types.SimpleNamespace(host=Option(), port=Option()),
    )

    def connect(database, **kwargs):
        calls['database'] = database
        calls['connect_kwargs'] = kwargs
        return Connection()

    driver_module.connect = connect
    firebird_module = types.ModuleType('firebird')
    firebird_module.driver = driver_module
    monkeypatch.setitem(sys.modules, 'firebird', firebird_module)
    monkeypatch.setitem(sys.modules, 'firebird.driver', driver_module)

    columns, rows = sync.query_compras(
        make_config(),
        date(2026, 5, 4),
        date(2026, 5, 4),
    )

    assert columns == ['EMPRESA', 'FECHA']
    assert rows == [('VYP', date(2026, 5, 4))]
    assert calls['sql'] == 'SELECT * FROM P_COMPRAS_GLOBALES(?, ?)'
    assert calls['params'] == (date(2026, 5, 4), date(2026, 5, 4))
    assert calls['database'] == 'VYP'
    assert calls['connect_kwargs']['charset'] == 'UTF8'
    assert driver_module.driver_config.server_defaults.host.value == 'localhost'
    assert driver_module.driver_config.server_defaults.port.value == '3050'


def test_sync_fecha_envia_ventas_compras_y_lotes_vacios(monkeypatch):
    sent = []
    finalized = []
    reports = []
    target_date = date(2026, 5, 4)

    monkeypatch.setattr(sync, 'query_ventas', lambda *args: (['EMPRESA'], []))
    monkeypatch.setattr(sync, 'query_compras', lambda *args: (['EMPRESA'], []))

    def fake_push(cfg, fecha, ventas_data, compras_data, replace=True):
        sent.append((fecha, ventas_data, compras_data, replace))
        return daily_success_response(fecha, len(ventas_data[1]), len(compras_data[1]))

    monkeypatch.setattr(sync, 'push_daily_to_vps', fake_push)
    monkeypatch.setattr(
        sync,
        'finalize_sync',
        lambda cfg, fecha: finalized.append(fecha) or {'success': True},
    )
    monkeypatch.setattr(
        sync,
        '_report_sync_status_safely',
        lambda *args, **kwargs: reports.append((args, kwargs)) or True,
    )

    assert sync.sync_fecha(make_config(), target_date) is True
    assert sent == [(target_date, (['EMPRESA'], []), (['EMPRESA'], []), True)]
    assert finalized == [target_date]
    assert [report[0][3] for report in reports] == ['iniciada', 'exitosa']
    assert reports[-1][1]['filas_ventas'] == 0
    assert reports[-1][1]['filas_compras'] == 0


def test_sync_fecha_intenta_compras_si_ventas_falla(monkeypatch):
    compras_consultadas = []
    sent = []
    finalized = []
    reports = []
    target_date = date(2026, 5, 4)

    def fail_ventas(*args):
        raise RuntimeError('fallo ventas')

    monkeypatch.setattr(sync, 'query_ventas', fail_ventas)
    monkeypatch.setattr(
        sync,
        'query_compras',
        lambda *args: compras_consultadas.append(True) or (['EMPRESA'], [('VYP',)]),
    )

    monkeypatch.setattr(sync, 'push_daily_to_vps', lambda *args, **kwargs: sent.append(True))
    monkeypatch.setattr(
        sync,
        'finalize_sync',
        lambda cfg, fecha: finalized.append(fecha),
    )
    monkeypatch.setattr(
        sync,
        '_report_sync_status_safely',
        lambda *args, **kwargs: reports.append((args, kwargs)) or True,
    )

    assert sync.sync_fecha(make_config(), target_date) is False
    assert compras_consultadas == [True]
    assert sent == []
    assert finalized == []
    assert [report[0][3] for report in reports] == ['iniciada', 'error']
    assert reports[-1][1]['mensaje'] == 'Falló extracción: ventas.'


def test_push_daily_envia_ambos_tipos_en_un_request(monkeypatch):
    target_date = date(2026, 5, 4)
    session = FakeSession(FakeResponse(daily_success_response(target_date, 1, 1)))
    monkeypatch.setattr(sync, '_build_http_session', lambda *args: session)

    result = sync.push_daily_to_vps(
        make_config(),
        target_date,
        (['EMPRESA', 'FECHA'], [('VYP', target_date)]),
        (['EMPRESA', 'FECHA'], [('LACTEOS_VP', target_date)]),
    )

    url, request_kwargs = session.request
    payload = request_kwargs['data'].decode('utf-8')
    assert url == 'https://app360.example/sabiogo/api/db-sync/daily'
    assert '"ventas": [{"EMPRESA": "VYP", "FECHA": "2026-05-04"}]' in payload
    assert '"compras": [{"EMPRESA": "LACTEOS_VP", "FECHA": "2026-05-04"}]' in payload
    assert result['total_filas']['total'] == 2


class FakeResponse:
    ok = True
    status_code = 200
    text = ''

    def __init__(self, result):
        self.result = result

    def json(self):
        return self.result

    def raise_for_status(self):
        raise AssertionError('raise_for_status no debe ejecutarse')


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self.response


@pytest.mark.parametrize(
    'result, expected_error',
    [
        ({
            'success': False,
            'error': 'fallo total',
            'tipo': 'ventas',
            'fecha': '2026-05-04',
            'total_filas': 0,
        }, 'fallo total'),
        ({
            'success': True,
            'tipo': 'ventas',
            'fecha': '2026-05-04',
            'total_filas': 0,
            'errores': {'LACTEOS': 'fallo parcial'},
        }, 'errores parciales'),
    ],
)
def test_push_rechaza_respuesta_no_exitosa(monkeypatch, result, expected_error):
    session = FakeSession(FakeResponse(result))
    monkeypatch.setattr(sync, '_build_http_session', lambda *args: session)

    with pytest.raises(RuntimeError, match=expected_error):
        sync.push_to_vps(
            make_config(),
            'ventas',
            date(2026, 5, 4),
            ['EMPRESA'],
            [],
        )

    payload = session.request[1]['data'].decode('utf-8')
    assert '"origenes": ["CARNES", "LACTEOS"]' in payload


def test_http_retry_incluye_post_y_errores_transitorios():
    session = sync._build_http_session(max_retries=3, backoff_factor=1)
    try:
        retry = session.get_adapter('https://').max_retries
        assert retry.total == 3
        assert retry.allowed_methods == frozenset({'POST'})
        assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
        assert retry.raise_on_status is False
    finally:
        session.close()


def test_finalize_rechaza_respuesta_no_exitosa(monkeypatch):
    session = FakeSession(FakeResponse({
        'success': False,
        'error': 'fallo de refresh',
        'fecha': '2026-05-04',
    }))
    monkeypatch.setattr(sync, '_build_http_session', lambda *args: session)

    with pytest.raises(RuntimeError, match='fallo de refresh'):
        sync.finalize_sync(make_config(), date(2026, 5, 4))


def test_report_sync_status_envia_estado_y_conteos(monkeypatch):
    execution_id = 'ca96c00e-08f9-45d0-b194-5a5f3f56f5cf'
    target_date = date(2026, 5, 4)
    session = FakeSession(FakeResponse({
        'success': True,
        'execution_id': execution_id,
        'fecha': target_date.isoformat(),
        'estado': 'exitosa',
    }))
    monkeypatch.setattr(sync, '_build_http_session', lambda *args: session)

    sync.report_sync_status(
        make_config(),
        execution_id,
        target_date,
        'exitosa',
        mensaje='Carga y finalización completadas.',
        filas_ventas=279,
        filas_compras=53,
    )

    url, request_kwargs = session.request
    payload = json.loads(request_kwargs['data'].decode('utf-8'))
    assert url == 'https://app360.example/sabiogo/api/db-sync/status'
    assert payload == {
        'execution_id': execution_id,
        'fecha': '2026-05-04',
        'estado': 'exitosa',
        'mensaje': 'Carga y finalización completadas.',
        'filas_ventas': 279,
        'filas_compras': 53,
    }


def test_sync_fecha_falla_si_no_puede_reportar_exito(monkeypatch):
    target_date = date(2026, 5, 4)
    states = []

    monkeypatch.setattr(sync, 'query_ventas', lambda *args: (['EMPRESA'], []))
    monkeypatch.setattr(sync, 'query_compras', lambda *args: (['EMPRESA'], []))
    monkeypatch.setattr(
        sync,
        'push_daily_to_vps',
        lambda cfg, fecha, *args, **kwargs: daily_success_response(fecha, 0, 0),
    )
    monkeypatch.setattr(sync, 'finalize_sync', lambda *args: {'success': True})

    def fail_final_status(*args, **kwargs):
        states.append(args[3])
        return args[3] != 'exitosa'

    monkeypatch.setattr(sync, '_report_sync_status_safely', fail_final_status)

    assert sync.sync_fecha(make_config(), target_date) is False
    assert states == ['iniciada', 'exitosa']
