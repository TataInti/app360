"""Tests para cobertura de fechas, historial de cargas y duplicados cross-carga.

Usa la BD postgres real con transacciones + rollback para aislar cada test.
"""

import pytest
import pandas as pd
from datetime import date, datetime, timedelta
from uuid import uuid4

from app import create_app
from blueprints.sabiogo import _importar_df_a_staging, _normalizar_fecha_dia
from models import db as _db
from models.sabiogo import StgSabiogoVentas, StgSabiogoCompras, LogSabiogoCarga


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['LOGIN_DISABLED'] = True
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
