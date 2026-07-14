from datetime import date, datetime
from uuid import uuid4

import pytest
from flask import render_template_string

from app import create_app
from config import Config
from models import db
from models.sabiogo import SabiogoSyncRun
from models.time_utils import LOCAL_TZ
from services.sabiogo_sync_monitor import get_sabiogo_sync_alert


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret')
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(Config, 'SQLALCHEMY_ENGINE_OPTIONS', {})
    monkeypatch.setattr(Config, 'WTF_CSRF_ENABLED', True)
    monkeypatch.setattr(Config, 'RATELIMIT_ENABLED', False)
    monkeypatch.setattr(Config, 'SERVER_NAME', None)
    monkeypatch.setattr(Config, 'SESSION_COOKIE_SECURE', False)

    test_app = create_app()
    test_app.config.update(
        TESTING=True,
        SABIOGO_SYNC_API_KEY='test-sync-key',
    )
    test_app.add_url_rule(
        '/_test/sync-alert',
        endpoint='test_sync_alert',
        view_func=lambda: render_template_string(
            '{% extends "base.html" %}{% block content %}OK{% endblock %}'
        ),
    )

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def add_run(
    fecha_objetivo,
    estado,
    mensaje=None,
    *,
    iniciada_en=None,
    finalizada_en=None,
):
    iniciada_en = iniciada_en or datetime(2026, 7, 14, 2, 0, tzinfo=LOCAL_TZ)
    if estado in {'exitosa', 'error'} and finalizada_en is None:
        finalizada_en = iniciada_en
    run = SabiogoSyncRun(
        execution_id=str(uuid4()),
        fecha_objetivo=fecha_objetivo,
        estado=estado,
        mensaje=mensaje,
        iniciada_en=iniciada_en,
        finalizada_en=finalizada_en,
    )
    db.session.add(run)
    db.session.commit()
    return run


def test_alerta_pendiente_despues_de_hora_de_gracia(app):
    with app.app_context():
        alert = get_sabiogo_sync_alert(
            datetime(2026, 7, 14, 3, 1, tzinfo=LOCAL_TZ)
        )

    assert alert['level'] == 'warning'
    assert '2026-07-13' in alert['message']
    assert '02:00' in alert['message']


def test_ejecucion_exitosa_limpia_alerta(app):
    with app.app_context():
        add_run(date(2026, 7, 13), 'exitosa')
        alert = get_sabiogo_sync_alert(
            datetime(2026, 7, 14, 3, 1, tzinfo=LOCAL_TZ)
        )

    assert alert is None


def test_error_se_muestra_sin_esperar_hora_de_gracia(app):
    with app.app_context():
        add_run(date(2026, 7, 13), 'error', 'Falló extracción: ventas.')
        alert = get_sabiogo_sync_alert(
            datetime(2026, 7, 14, 2, 15, tzinfo=LOCAL_TZ)
        )

    assert alert['level'] == 'danger'
    assert alert['message'] == '2026-07-13: Falló extracción: ventas.'


def test_fallo_anterior_sigue_visible_hasta_recuperar_misma_fecha(app):
    with app.app_context():
        add_run(date(2026, 7, 11), 'error', 'Falló la carga.')
        add_run(date(2026, 7, 12), 'exitosa')
        alert = get_sabiogo_sync_alert(
            datetime(2026, 7, 13, 3, 1, tzinfo=LOCAL_TZ)
        )
        add_run(date(2026, 7, 11), 'exitosa')
        recovered_alert = get_sabiogo_sync_alert(
            datetime(2026, 7, 13, 3, 1, tzinfo=LOCAL_TZ)
        )

    assert alert['level'] == 'danger'
    assert '2026-07-11' in alert['message']
    assert recovered_alert is None


def test_exito_iniciado_despues_no_oculta_error_finalizado_mas_tarde(app):
    with app.app_context():
        add_run(
            date(2026, 7, 13),
            'error',
            'Falló intento A.',
            iniciada_en=datetime(2026, 7, 14, 2, 0, tzinfo=LOCAL_TZ),
            finalizada_en=datetime(2026, 7, 14, 2, 20, tzinfo=LOCAL_TZ),
        )
        add_run(
            date(2026, 7, 13),
            'exitosa',
            iniciada_en=datetime(2026, 7, 14, 2, 5, tzinfo=LOCAL_TZ),
            finalizada_en=datetime(2026, 7, 14, 2, 10, tzinfo=LOCAL_TZ),
        )
        alert = get_sabiogo_sync_alert(
            datetime(2026, 7, 14, 3, 1, tzinfo=LOCAL_TZ)
        )

    assert alert['level'] == 'danger'
    assert alert['message'] == '2026-07-13: Falló intento A.'


def test_status_requiere_clave_y_actualiza_ejecucion(client, app):
    execution_id = str(uuid4())
    payload = {
        'execution_id': execution_id,
        'fecha': '2026-07-13',
        'estado': 'iniciada',
    }

    assert client.post('/sabiogo/api/db-sync/status', json=payload).status_code == 401
    response = client.post(
        '/sabiogo/api/db-sync/status',
        json=payload,
        headers={'X-Sync-Key': 'test-sync-key'},
    )
    assert response.status_code == 200

    payload.update({
        'estado': 'exitosa',
        'filas_ventas': 279,
        'filas_compras': 53,
    })
    response = client.post(
        '/sabiogo/api/db-sync/status',
        json=payload,
        headers={'X-Sync-Key': 'test-sync-key'},
    )
    assert response.status_code == 200

    with app.app_context():
        run = SabiogoSyncRun.query.filter_by(execution_id=execution_id).one()
        assert run.estado == 'exitosa'
        assert run.filas_ventas == 279
        assert run.filas_compras == 53
        assert run.finalizada_en is not None
        first_finished_at = run.finalizada_en

    response = client.post(
        '/sabiogo/api/db-sync/status',
        json=payload,
        headers={'X-Sync-Key': 'test-sync-key'},
    )
    assert response.status_code == 200

    with app.app_context():
        run = SabiogoSyncRun.query.filter_by(execution_id=execution_id).one()
        assert run.finalizada_en == first_finished_at


def test_banner_visible_solo_para_rol_gerente(client, app):
    with app.app_context():
        add_run(date(2026, 7, 12), 'error', 'Falló la carga.')

    with client.session_transaction() as user_session:
        user_session['user'] = 'Gerencia'
        user_session['role'] = 'gerente'
    gerente_response = client.get('/_test/sync-alert')
    assert b'Fall\xc3\xb3 la sincronizaci\xc3\xb3n SabioGo' in gerente_response.data

    with client.session_transaction() as user_session:
        user_session['role'] = 'manager'
    manager_response = client.get('/_test/sync-alert')
    assert b'Fall\xc3\xb3 la sincronizaci\xc3\xb3n SabioGo' not in manager_response.data