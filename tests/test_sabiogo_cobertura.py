"""Tests para cobertura de fechas, historial de cargas y duplicados cross-carga.

Usa la BD postgres real con transacciones + rollback para aislar cada test.
"""

import pytest
import pandas as pd
from datetime import date, datetime, timedelta
from uuid import uuid4

from app import create_app
from blueprints.sabiogo import _hash_sync_payload, _importar_df_a_staging, _normalizar_fecha_dia
from models import db as _db
from models.sabiogo import StgSabiogoVentas, StgSabiogoCompras, LogSabiogoCarga
from services.sabiogo_service import SabiogoService

# El fixture crea las tablas (incluida users), así que el módulo recibe la sesión admin
# igual que el resto de la suite.


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['LOGIN_DISABLED'] = True
    app.config['SABIOGO_SYNC_API_KEY'] = 'test-sync-key'
    with app.app_context():
        # En SQLite (CI, base en memoria) no existen las tablas de staging ni de log:
        # se crean desde los modelos importados arriba. En Postgres se usa el esquema real.
        if _db.engine.dialect.name == 'sqlite':
            _db.create_all()
    return app


@pytest.fixture(autouse=True)
def db_session(app):
    """Transactional fixture: cada test corre dentro de un SAVEPOINT que se revierte."""
    with app.app_context():
        _db.session.begin_nested()
        yield _db.session
        _db.session.rollback()


@pytest.fixture
def client(app):
    return app.test_client()


class TestValidarDuplicadosCrossCarga:
    """Verifica que validar_duplicados detecta filas pendientes que ya existen procesadas."""

    def test_cross_carga_marks_duplicates(self, db_session):
        existing = StgSabiogoVentas(
            fecha=date(2025, 3, 10),
            codigo='TEST-DUP-CROSS',
            nro_comprob='FAC-TEST-001',
            tipo='FAC',
            subtot=1000.0,
            origen='CARNES',
            estado='procesado',
        )
        db_session.add(existing)
        db_session.flush()

        duplicate = StgSabiogoVentas(
            fecha=date(2025, 3, 10),
            codigo='TEST-DUP-CROSS',
            nro_comprob='FAC-TEST-001',
            tipo='FAC',
            subtot=1000.0,
            origen='CARNES',
            estado='pendiente',
        )
        db_session.add(duplicate)
        db_session.flush()

        count = StgSabiogoVentas.validar_duplicados(db_session)
        assert count == 1

        db_session.expire_all()
        assert duplicate.estado == 'duplicado'
        assert existing.estado == 'procesado'

    def test_cross_carga_marks_duplicates_con_campos_nulos(self, db_session):
        existing = StgSabiogoVentas(
            fecha=date(2025, 3, 10),
            codigo='TEST-DUP-NULL',
            nro_comprob=None,
            tipo=None,
            subtot=1000.0,
            origen='CARNES',
            estado='procesado',
        )
        duplicate = StgSabiogoVentas(
            fecha=date(2025, 3, 10),
            codigo='TEST-DUP-NULL',
            nro_comprob=None,
            tipo=None,
            subtot=1000.0,
            origen='CARNES',
            estado='pendiente',
        )
        db_session.add_all([existing, duplicate])
        db_session.flush()

        count = StgSabiogoVentas.validar_duplicados(db_session)

        assert count == 1
        db_session.expire_all()
        assert duplicate.estado == 'duplicado'

    def test_no_false_positives(self, db_session):
        existing = StgSabiogoVentas(
            fecha=date(2025, 3, 10),
            codigo='TEST-NF',
            nro_comprob='FAC-TEST-NF1',
            tipo='FAC',
            subtot=1000.0,
            origen='CARNES',
            estado='procesado',
        )
        new_row = StgSabiogoVentas(
            fecha=date(2025, 3, 11),
            codigo='TEST-NF',
            nro_comprob='FAC-TEST-NF2',
            tipo='FAC',
            subtot=500.0,
            origen='CARNES',
            estado='pendiente',
        )
        db_session.add_all([existing, new_row])
        db_session.flush()

        count = StgSabiogoVentas.validar_duplicados(db_session)
        assert count == 0

        db_session.expire_all()
        assert new_row.estado == 'pendiente'

    def test_intra_batch_still_works(self, db_session):
        r1 = StgSabiogoVentas(
            fecha=date(2025, 3, 10), codigo='TEST-INTRA', nro_comprob='F-INTRA',
            tipo='FAC', subtot=100.0, origen='CARNES', estado='pendiente',
        )
        r2 = StgSabiogoVentas(
            fecha=date(2025, 3, 10), codigo='TEST-INTRA', nro_comprob='F-INTRA',
            tipo='FAC', subtot=100.0, origen='CARNES', estado='pendiente',
        )
        db_session.add_all([r1, r2])
        db_session.flush()

        count = StgSabiogoVentas.validar_duplicados(db_session)
        assert count == 1

        db_session.expire_all()
        assert r1.estado == 'pendiente'
        assert r2.estado == 'duplicado'

    def test_compras_cross_carga(self, db_session):
        existing = StgSabiogoCompras(
            fecha=date(2025, 3, 10), codigo='TEST-CMP', nro_comprob='OC-TEST',
            tipo='OC', subtot=2000.0, origen='LACTEOS', estado='procesado',
        )
        dup = StgSabiogoCompras(
            fecha=date(2025, 3, 10), codigo='TEST-CMP', nro_comprob='OC-TEST',
            tipo='OC', subtot=2000.0, origen='LACTEOS', estado='pendiente',
        )
        db_session.add_all([existing, dup])
        db_session.flush()

        count = StgSabiogoCompras.validar_duplicados(db_session)
        assert count == 1

        db_session.expire_all()
        assert dup.estado == 'duplicado'


class TestDescartarDuplicadosEnImportacion:
    """Verifica que los duplicados detectados se eliminan del staging del archivo nuevo."""

    def test_import_descarta_cross_carga_y_no_persiste_duplicado(self, db_session):
        existente = StgSabiogoVentas(
            fecha=date(2025, 3, 10), codigo='TEST-DISCARD-CROSS', nro_comprob='FAC-DISC-001',
            tipo='FAC', subtot=500.0, origen='CARNES', estado='procesado',
        )
        db_session.add(existente)
        db_session.flush()

        df = pd.DataFrame([
            {
                'fecha': date(2025, 3, 10),
                'codigo': 'TEST-DISCARD-CROSS',
                'nro_comprob': 'FAC-DISC-001',
                'tipo': 'FAC',
                'subtot': 500.0,
                'producto': 'Producto X',
            }
        ])

        stats = _importar_df_a_staging(
            df,
            ModelClass=StgSabiogoVentas,
            origen='CARNES',
            filename='cross.xlsx',
            file_sha256='hash_cross_discard',
        )

        db_session.expire_all()
        assert stats['filas_insertadas'] == 1
        assert stats['filas_duplicadas'] == 1
        assert stats['filas_procesadas'] == 0
        assert StgSabiogoVentas.query.filter_by(hash_archivo='hash_cross_discard').count() == 0
        assert StgSabiogoVentas.query.filter_by(codigo='TEST-DISCARD-CROSS', estado='procesado').count() == 1

    def test_import_descarta_intra_lote_y_conserva_uno(self, db_session):
        df = pd.DataFrame([
            {
                'fecha': date(2025, 3, 11),
                'codigo': 'TEST-DISCARD-INTRA',
                'nro_comprob': 'FAC-DISC-002',
                'tipo': 'FAC',
                'subtot': 700.0,
                'producto': 'Producto Y',
            },
            {
                'fecha': date(2025, 3, 11),
                'codigo': 'TEST-DISCARD-INTRA',
                'nro_comprob': 'FAC-DISC-002',
                'tipo': 'FAC',
                'subtot': 700.0,
                'producto': 'Producto Y',
            },
        ])

        stats = _importar_df_a_staging(
            df,
            ModelClass=StgSabiogoVentas,
            origen='CARNES',
            filename='intra.xlsx',
            file_sha256='hash_intra_discard',
        )

        rows = StgSabiogoVentas.query.filter_by(hash_archivo='hash_intra_discard').order_by(StgSabiogoVentas.id.asc()).all()
        assert stats['filas_insertadas'] == 2
        assert stats['filas_duplicadas'] == 1
        assert stats['filas_procesadas'] == 1
        assert len(rows) == 1
        assert rows[0].estado == 'procesado'


class TestCoberturaFechasEndpoint:
    """Verifica el endpoint GET /sabiogo/api/cobertura-fechas."""

    def test_normalizar_fecha_dia_convierte_datetime(self):
        assert _normalizar_fecha_dia(datetime(2026, 3, 30, 14, 15)) == date(2026, 3, 30)
        assert _normalizar_fecha_dia(date(2026, 3, 30)) == date(2026, 3, 30)

    def test_cobertura_responde_ok(self, client):
        resp = client.get('/sabiogo/api/cobertura-fechas?fecha_desde=2025-03-10&fecha_hasta=2025-03-15')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'rango' in data
        assert 'resumen' in data
        assert data['rango']['desde'] == '2025-03-10'
        assert data['rango']['hasta'] == '2025-03-15'

    def test_cobertura_estructura_mensual(self, client):
        resp = client.get('/sabiogo/api/cobertura-fechas?fecha_desde=2025-03-10&fecha_hasta=2025-04-10')
        assert resp.status_code == 200
        data = resp.get_json()
        # Rango cubre 2 meses
        meses = [m['mes'] for m in data['resumen']]
        assert '2025-03' in meses
        assert '2025-04' in meses
        # Cada mes tiene las 4 columnas
        for entry in data['resumen']:
            for campo in ['ventas_carnes', 'ventas_lacteos', 'compras_carnes', 'compras_lacteos']:
                assert campo in entry
                assert 'dias_cargados' in entry[campo]
                assert 'dias_habiles' in entry[campo]
                assert 'filas' in entry[campo]
                assert 'dias_faltantes' in entry[campo]

    def test_cobertura_excluye_domingos(self, client):
        # 2025-03-09 es domingo
        resp = client.get('/sabiogo/api/cobertura-fechas?fecha_desde=2025-03-09&fecha_hasta=2025-03-09')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['resumen'] == []

    def test_cobertura_dias_habiles_lun_sab(self, client):
        # 2025-03-10 (lun) a 2025-03-15 (sab) = 6 dias habiles
        resp = client.get('/sabiogo/api/cobertura-fechas?fecha_desde=2025-03-10&fecha_hasta=2025-03-15')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['resumen']) == 1
        vc = data['resumen'][0]['ventas_carnes']
        assert vc['dias_habiles'] == 6


class TestDbSyncEndpoint:
    """Verifica el endpoint POST /sabiogo/api/db-sync."""

    def test_sync_key_no_habilita_otras_rutas(self, client):
        with client.session_transaction() as session:
            session.clear()

        resp = client.get(
            '/sabiogo/api/historial-cargas',
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 401
        assert resp.is_json

    def test_requiere_sync_key_aun_con_sesion(self, client):
        resp = client.post('/sabiogo/api/db-sync', json={
            'tipo': 'ventas',
            'fecha': '2025-03-10',
            'rows': [{'EMPRESA': 'VYP', 'CODIGO': 'TEST-NOKEY', 'PRODUCTO': 'Prod', 'SUBTOT': 1}],
        })

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'Unauthorized'

    def test_daily_requiere_sync_key(self, client):
        resp = client.post('/sabiogo/api/db-sync/daily', json={
            'fecha': '2025-04-01',
            'origenes': ['CARNES'],
            'ventas': [],
            'compras': [],
        })

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'Unauthorized'

    def test_daily_rechaza_origen_custom_fuera_de_whitelist(self, client):
        resp = client.post(
            '/sabiogo/api/db-sync/daily',
            json={
                'fecha': '2025-04-01',
                'empresa_map': {'OTRA_EMPRESA': 'ORIGEN_FANTASMA'},
                'origenes': ['ORIGEN_FANTASMA'],
                'ventas': [{'EMPRESA': 'OTRA_EMPRESA', 'CODIGO': 'X-1'}],
                'compras': [],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 400
        assert 'origen inválido' in resp.get_json()['error']

    def test_daily_confirma_ventas_y_compras_juntas(self, client):
        unique_id = uuid4().hex[:8]
        resp = client.post(
            '/sabiogo/api/db-sync/daily',
            json={
                'fecha': '2025-04-01',
                'origenes': ['CARNES'],
                'ventas': [{
                    'EMPRESA': 'VYP',
                    'FECHA': '2025-04-01',
                    'CODIGO': f'DAILY-V-{unique_id}',
                    'PRODUCTO': 'Venta diaria',
                    'NRO_COMPROB': f'FAC-{unique_id}',
                    'TIPO': 'FAC',
                    'SUBTOT': 100.0,
                }],
                'compras': [{
                    'EMPRESA': 'VYP',
                    'FECHA': '2025-04-01',
                    'CODIGO': f'DAILY-C-{unique_id}',
                    'PRODUCTO': 'Compra diaria',
                    'NRO_COMPROB': f'OC-{unique_id}',
                    'TIPO': 'OC',
                    'SUBTOT': 60.0,
                }],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['total_filas'] == {'ventas': 1, 'compras': 1, 'total': 2}
        assert set(data['resultados']) == {'ventas', 'compras'}
        assert StgSabiogoVentas.query.filter_by(codigo=f'DAILY-V-{unique_id}').count() == 1
        assert StgSabiogoCompras.query.filter_by(codigo=f'DAILY-C-{unique_id}').count() == 1

    def test_daily_revierte_ventas_si_dedupe_compras_falla(self, db_session, client, monkeypatch):
        unique_id = uuid4().hex[:8]
        fecha_lote = date(2025, 4, 2)
        old_venta = StgSabiogoVentas(
            fecha=fecha_lote,
            origen='CARNES',
            codigo=f'DAILY-OLD-V-{unique_id}',
            estado='procesado',
            hash_archivo=f'daily-old-v-{unique_id}',
        )
        old_compra = StgSabiogoCompras(
            fecha=fecha_lote,
            origen='CARNES',
            codigo=f'DAILY-OLD-C-{unique_id}',
            estado='procesado',
            hash_archivo=f'daily-old-c-{unique_id}',
        )
        db_session.add_all([old_venta, old_compra])
        db_session.commit()

        def fail_compras_dedupe(session):
            raise RuntimeError('fallo de deduplicación')

        monkeypatch.setattr(StgSabiogoCompras, 'validar_duplicados', fail_compras_dedupe)

        resp = client.post(
            '/sabiogo/api/db-sync/daily',
            json={
                'fecha': fecha_lote.isoformat(),
                'origenes': ['CARNES'],
                'ventas': [{
                    'EMPRESA': 'VYP',
                    'FECHA': fecha_lote.isoformat(),
                    'CODIGO': f'DAILY-NEW-V-{unique_id}',
                }],
                'compras': [{
                    'EMPRESA': 'VYP',
                    'FECHA': fecha_lote.isoformat(),
                    'CODIGO': f'DAILY-NEW-C-{unique_id}',
                }],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 500
        db_session.expire_all()
        assert StgSabiogoVentas.query.filter_by(codigo=f'DAILY-OLD-V-{unique_id}').count() == 1
        assert StgSabiogoCompras.query.filter_by(codigo=f'DAILY-OLD-C-{unique_id}').count() == 1
        assert StgSabiogoVentas.query.filter_by(codigo=f'DAILY-NEW-V-{unique_id}').count() == 0

    def test_sync_key_alcanza_sin_sesion_y_separa_por_origen(self, db_session, client):
        with client.session_transaction() as session:
            session.clear()

        unique_id = uuid4().hex[:8]
        payload = {
            'tipo': 'ventas',
            'fecha': '2025-03-11',
            'rows': [
                {
                    'EMPRESA': 'VYP',
                    'FECHA': '2025-03-11',
                    'CODIGO': f'CARN-{unique_id}',
                    'PRODUCTO': 'Producto carnes',
                    'NRO_COMPROB': f'FAC-C-{unique_id}',
                    'TIPO': 'FAC',
                    'SUBTOT': 100.0,
                },
                {
                    'EMPRESA': 'LACTEOS_VP',
                    'FECHA': '2025-03-11',
                    'CODIGO': f'LAC-{unique_id}',
                    'PRODUCTO': 'Producto lacteos',
                    'NRO_COMPROB': f'FAC-L-{unique_id}',
                    'TIPO': 'FAC',
                    'SUBTOT': 200.0,
                },
            ],
        }

        resp = client.post(
            '/sabiogo/api/db-sync',
            json=payload,
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['resultados']['CARNES']['filas_insertadas'] == 1
        assert data['resultados']['LACTEOS']['filas_insertadas'] == 1

        venta_carnes = StgSabiogoVentas.query.filter_by(codigo=f'CARN-{unique_id}').one()
        venta_lacteos = StgSabiogoVentas.query.filter_by(codigo=f'LAC-{unique_id}').one()
        assert venta_carnes.origen == 'CARNES'
        assert venta_lacteos.origen == 'LACTEOS'
        assert venta_carnes.estado == 'procesado'
        assert venta_lacteos.estado == 'procesado'

        hash_carnes = _hash_sync_payload(
            'ventas',
            date(2025, 3, 11),
            'CARNES',
            [{
                'empresa': 'VYP',
                'fecha': date(2025, 3, 11),
                'codigo': f'CARN-{unique_id}',
                'producto': 'Producto carnes',
                'nro_comprob': f'FAC-C-{unique_id}',
                'tipo': 'FAC',
                'subtot': 100.0,
            }],
            True,
        )
        hash_lacteos = _hash_sync_payload(
            'ventas',
            date(2025, 3, 11),
            'LACTEOS',
            [{
                'empresa': 'LACTEOS_VP',
                'fecha': date(2025, 3, 11),
                'codigo': f'LAC-{unique_id}',
                'producto': 'Producto lacteos',
                'nro_comprob': f'FAC-L-{unique_id}',
                'tipo': 'FAC',
                'subtot': 200.0,
            }],
            True,
        )
        logs = LogSabiogoCarga.query.filter(
            LogSabiogoCarga.hash_archivo.in_([hash_carnes, hash_lacteos])
        ).all()
        assert len(logs) == 2

    def test_replace_reemplaza_lote_por_fecha_y_origen(self, db_session, client):
        existing = StgSabiogoVentas(
            fecha=date(2025, 3, 12),
            origen='CARNES',
            codigo='OLD-CODE',
            producto='Viejo',
            nro_comprob='FAC-OLD',
            tipo='FAC',
            subtot=50.0,
            estado='procesado',
            hash_archivo='old-hash',
        )
        db_session.add(existing)
        db_session.commit()

        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-12',
                'replace': True,
                'rows': [
                    {
                        'EMPRESA': 'VYP',
                        'FECHA': '2025-03-12',
                        'CODIGO': 'NEW-CODE',
                        'PRODUCTO': 'Nuevo',
                        'NRO_COMPROB': 'FAC-NEW',
                        'TIPO': 'FAC',
                        'SUBTOT': 75.0,
                    },
                ],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        assert StgSabiogoVentas.query.filter_by(codigo='OLD-CODE').count() == 0
        assert StgSabiogoVentas.query.filter_by(codigo='NEW-CODE', origen='CARNES').count() == 1

    def test_rechaza_empresa_no_mapeada(self, client):
        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-13',
                'rows': [{'EMPRESA': 'DESCONOCIDA', 'CODIGO': 'X1', 'PRODUCTO': 'Prod', 'SUBTOT': 1}],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 400
        assert 'EMPRESA no mapeada' in resp.get_json()['error']

    def test_rechaza_fecha_distinta_a_fecha_lote(self, client):
        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-13',
                'rows': [{
                    'EMPRESA': 'VYP',
                    'FECHA': '2025-03-12',
                    'CODIGO': 'FECHA-INVALIDA',
                    'PRODUCTO': 'Prod',
                    'SUBTOT': 1,
                }],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 400
        assert 'no coincide con el lote' in resp.get_json()['error']

    def test_lote_vacio_reemplaza_y_audita_origenes_declarados(self, db_session, client):
        unique_id = uuid4().hex[:8]
        existing = StgSabiogoVentas(
            fecha=date(2025, 3, 14),
            origen='CARNES',
            codigo=f'EMPTY-{unique_id}',
            producto='Existente',
            estado='procesado',
            hash_archivo=f'empty-{unique_id}',
        )
        db_session.add(existing)
        db_session.commit()

        empty_log_names = [
            'api_sync_ventas_2025-03-14_carnes.json',
            'api_sync_ventas_2025-03-14_lacteos.json',
        ]
        logs_before = LogSabiogoCarga.query.filter(
            LogSabiogoCarga.archivo_nombre.in_(empty_log_names)
        ).count()

        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-14',
                'replace': True,
                'origenes': ['CARNES', 'LACTEOS'],
                'rows': [],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        assert resp.get_json() == {
            'success': True,
            'tipo': 'ventas',
            'fecha': '2025-03-14',
            'total_filas': 0,
            'resultados': {
                'CARNES': {
                    'filas_insertadas': 0,
                    'filas_procesadas': 0,
                    'filas_duplicadas': 0,
                    'filas_error': 0,
                },
                'LACTEOS': {
                    'filas_insertadas': 0,
                    'filas_procesadas': 0,
                    'filas_duplicadas': 0,
                    'filas_error': 0,
                },
            },
            'errores': None,
            'replace': True,
        }
        assert StgSabiogoVentas.query.filter_by(codigo=f'EMPTY-{unique_id}').count() == 0
        logs = LogSabiogoCarga.query.filter(
            LogSabiogoCarga.archivo_nombre.in_(empty_log_names)
        ).all()
        assert len(logs) == logs_before + 2
        assert all(log.filas_insertadas == 0 for log in logs[-2:])

    def test_lote_vacio_requiere_origenes(self, client):
        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-14',
                'rows': [],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 400
        assert 'origenes requerido' in resp.get_json()['error']

    def test_compras_inserta_en_staging_correcto(self, client):
        unique_id = uuid4().hex[:8]
        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'compras',
                'fecha': '2025-03-15',
                'rows': [{
                    'EMPRESA': 'VYP',
                    'FECHA': '2025-03-15',
                    'CODIGO': f'COMP-{unique_id}',
                    'PRODUCTO': 'Compra carnes',
                    'NRO_COMPROB': f'OC-{unique_id}',
                    'TIPO': 'OC',
                    'SUBTOT': 125.0,
                }],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        compra = StgSabiogoCompras.query.filter_by(codigo=f'COMP-{unique_id}').one()
        assert compra.origen == 'CARNES'
        assert compra.estado == 'procesado'

    def test_firma_duplicado_incluye_origen(self, client):
        unique_id = uuid4().hex[:8]
        common = {
            'FECHA': '2025-03-15',
            'CODIGO': f'DUPE-{unique_id}',
            'PRODUCTO': 'Mismo producto',
            'NRO_COMPROB': f'FAC-{unique_id}',
            'TIPO': 'FAC',
            'SUBTOT': 100.0,
        }
        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-15',
                'rows': [
                    {'EMPRESA': 'VYP', **common},
                    {'EMPRESA': 'LACTEOS_VP', **common},
                ],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        rows = StgSabiogoVentas.query.filter_by(codigo=f'DUPE-{unique_id}').all()
        assert {row.origen for row in rows} == {'CARNES', 'LACTEOS'}

    def test_fallo_de_un_origen_revierte_todo_el_lote(self, client, monkeypatch):
        unique_id = uuid4().hex[:8]

        def fail_lacteos(df, *, ModelClass, origen, filename, file_sha256):
            if origen == 'LACTEOS':
                raise RuntimeError('fallo forzado')
            return _importar_df_a_staging(
                df,
                ModelClass=ModelClass,
                origen=origen,
                filename=filename,
                file_sha256=file_sha256,
            )

        monkeypatch.setattr('blueprints.sabiogo._importar_df_a_staging', fail_lacteos)
        resp = client.post(
            '/sabiogo/api/db-sync',
            json={
                'tipo': 'ventas',
                'fecha': '2025-03-15',
                'rows': [
                    {
                        'EMPRESA': 'VYP',
                        'FECHA': '2025-03-15',
                        'CODIGO': f'ROLL-C-{unique_id}',
                        'PRODUCTO': 'Carnes',
                    },
                    {
                        'EMPRESA': 'LACTEOS_VP',
                        'FECHA': '2025-03-15',
                        'CODIGO': f'ROLL-L-{unique_id}',
                        'PRODUCTO': 'Lacteos',
                    },
                ],
            },
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 500
        assert resp.get_json()['success'] is False
        assert StgSabiogoVentas.query.filter(
            StgSabiogoVentas.codigo.in_([
                f'ROLL-C-{unique_id}',
                f'ROLL-L-{unique_id}',
            ])
        ).count() == 0

    def test_finalize_requiere_sync_key(self, client):
        resp = client.post(
            '/sabiogo/api/db-sync/finalize',
            json={'fecha': '2025-03-15'},
        )

        assert resp.status_code == 401

    def test_finalize_refresca_facts_sin_sync_de_objetivos(self, client, monkeypatch):
        calls = []

        def fake_refresh(service):
            calls.append(('facts', None))
            return {
                'mensaje': 'Vistas materializadas actualizadas',
                'staging_promovidos': {'ventas': 0, 'compras': 0},
            }

        monkeypatch.setattr(SabiogoService, 'refresh_facts', fake_refresh)

        resp = client.post(
            '/sabiogo/api/db-sync/finalize',
            json={'fecha': '2025-03-15'},
            headers={'X-Sync-Key': 'test-sync-key'},
        )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        assert calls == [('facts', None)]
        assert 'objetivos' not in resp.get_json()

    def test_endpoint_legacy_sync_objetivos_pre_fue_retirado(self, client):
        resp = client.post(
            '/sabiogo/api/sync-objetivos-pre-cron',
            json={'periodo': '2025-03'},
        )
        assert resp.status_code == 404


class TestHistorialCargasEndpoint:
    """Verifica el endpoint GET /sabiogo/api/historial-cargas."""

    def test_historial_responde(self, client):
        resp = client.get('/sabiogo/api/historial-cargas')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'items' in data

    def test_historial_con_datos(self, db_session, client):
        unique_id = uuid4().hex
        log = LogSabiogoCarga(
            archivo_nombre=f'test_cobertura_{unique_id}.xls',
            tipo_carga='ventas',
            hash_archivo=f'test_hash_cob_{unique_id}',
            filas_insertadas=100,
            filas_duplicadas=5,
            filas_error=2,
        )
        db_session.add(log)
        db_session.commit()

        resp = client.get('/sabiogo/api/historial-cargas')
        assert resp.status_code == 200
        data = resp.get_json()
        found = [i for i in data['items'] if i['archivo_nombre'] == log.archivo_nombre]
        assert len(found) == 1
        assert found[0]['filas_insertadas'] == 100
        assert found[0]['filas_duplicadas'] == 5

    def test_historial_limit(self, client):
        resp = client.get('/sabiogo/api/historial-cargas?limit=3')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['items']) <= 3


class TestPurgarDuplicadosEndpoint:
    """Verifica la limpieza manual de duplicados heredados."""

    def test_purgar_duplicados_heredados(self, db_session, client):
        venta_dup = StgSabiogoVentas(
            fecha=date(2025, 3, 12), codigo='TEST-PURGE-V', nro_comprob='PURGE-V',
            tipo='FAC', subtot=100.0, origen='CARNES', estado='duplicado', hash_archivo='purge_ventas_hash',
        )
        compra_dup = StgSabiogoCompras(
            fecha=date(2025, 3, 12), codigo='TEST-PURGE-C', nro_comprob='PURGE-C',
            tipo='OC', subtot=200.0, origen='LACTEOS', estado='duplicado', hash_archivo='purge_compras_hash',
        )
        db_session.add_all([venta_dup, compra_dup])
        db_session.commit()

        resp = client.post('/sabiogo/api/purgar-duplicados')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['purgados']['total'] >= 2
        assert StgSabiogoVentas.query.filter_by(hash_archivo='purge_ventas_hash').count() == 0
        assert StgSabiogoCompras.query.filter_by(hash_archivo='purge_compras_hash').count() == 0
