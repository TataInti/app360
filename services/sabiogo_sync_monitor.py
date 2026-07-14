"""Estado visible de la sincronización diaria SabioGo."""

from datetime import datetime, time, timedelta

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import aliased

from models import db
from models.sabiogo import SabiogoSyncRun
from models.time_utils import LOCAL_TZ, now_local


SYNC_SCHEDULE_HOUR = 2
SYNC_GRACE_MINUTES = 60


def _latest_run(fecha_objetivo):
    return (
        SabiogoSyncRun.query
        .filter_by(fecha_objetivo=fecha_objetivo)
        .order_by(SabiogoSyncRun.iniciada_en.desc(), SabiogoSyncRun.id.desc())
        .first()
    )


def _oldest_unresolved_failure():
    failed_run = aliased(SabiogoSyncRun)
    recovery = aliased(SabiogoSyncRun)
    failed_at = func.coalesce(
        failed_run.finalizada_en,
        failed_run.actualizada_en,
        failed_run.iniciada_en,
    )
    recovery_at = func.coalesce(
        recovery.finalizada_en,
        recovery.actualizada_en,
        recovery.iniciada_en,
    )
    recovered = exists().where(and_(
        recovery.fecha_objetivo == failed_run.fecha_objetivo,
        recovery.estado == 'exitosa',
        or_(
            recovery_at > failed_at,
            and_(recovery_at == failed_at, recovery.id > failed_run.id),
        ),
    ))
    return (
        db.session.query(failed_run)
        .filter(failed_run.estado == 'error', ~recovered)
        .order_by(failed_run.fecha_objetivo.asc(), failed_run.id.asc())
        .first()
    )


def _failure_alert(run):
    detail = run.mensaje or 'La ejecución terminó con error.'
    return {
        'level': 'danger',
        'title': 'Falló la sincronización SabioGo',
        'message': f'{run.fecha_objetivo.isoformat()}: {detail}',
    }


def get_sabiogo_sync_alert(now=None):
    """Retorna alerta vigente para la sincronización esperada, o ``None``."""
    current = now or now_local()
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    else:
        current = current.astimezone(LOCAL_TZ)

    scheduled_date = current.date() - timedelta(days=1)
    grace_cutoff = datetime.combine(
        current.date(),
        time(SYNC_SCHEDULE_HOUR, 0),
        tzinfo=LOCAL_TZ,
    ) + timedelta(minutes=SYNC_GRACE_MINUTES)

    unresolved_failure = _oldest_unresolved_failure()
    if unresolved_failure:
        return _failure_alert(unresolved_failure)

    current_run = _latest_run(scheduled_date)

    expected_date = scheduled_date
    if current < grace_cutoff:
        expected_date -= timedelta(days=1)

    run = current_run if expected_date == scheduled_date else _latest_run(expected_date)
    if run and run.estado == 'exitosa':
        return None
    if run and run.estado == 'error':
        return _failure_alert(run)
    if run and run.estado == 'iniciada':
        return {
            'level': 'warning',
            'title': 'Sincronización SabioGo demorada',
            'message': (
                f'La ejecución de {expected_date.isoformat()} no finalizó '
                'dentro de una hora.'
            ),
        }

    return {
        'level': 'warning',
        'title': 'Sincronización SabioGo pendiente',
        'message': (
            f'No se registró la ejecución programada para '
            f'{expected_date.isoformat()} a las 02:00.'
        ),
    }