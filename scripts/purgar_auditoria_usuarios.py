"""Purga manual de user_audit_log (retención de 2 años, D10). Simulación por defecto.

No corre sola: no hay cron ni la llama la aplicación. Borra las filas con created_at anterior a la
medianoche (hora de Argentina) del día indicado.

Simular (no borra nada):
    python scripts/purgar_auditoria_usuarios.py --antes-de AAAA-MM-DD
Borrar (exige repetir la misma fecha en --confirmar):
    python scripts/purgar_auditoria_usuarios.py --antes-de AAAA-MM-DD --ejecutar --confirmar AAAA-MM-DD

Sin --confirmar igual a --antes-de, con --ejecutar no se borra nada y sale con código 2. La base es
la de DATABASE_URL: no ejecutar contra producción sin autorización de Inti (vía Ciro).
"""

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ZONA_ARGENTINA = timezone(timedelta(hours=-3))
PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _fecha(valor):
    if not PATRON_FECHA.fullmatch(valor):
        raise argparse.ArgumentTypeError("Usá la fecha como AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError("La fecha no existe.")


def limite_utc(dia):
    """Medianoche de Argentina del día indicado, expresada en UTC."""
    return datetime(dia.year, dia.month, dia.day, tzinfo=ZONA_ARGENTINA).astimezone(timezone.utc)


def purgar(antes_de, ejecutar=False, confirmar=None):
    """Devuelve (cantidad_a_borrar, borradas). Requiere contexto de aplicación activo."""
    from models import db
    from models.core.user_audit_log import UserAuditLog

    consulta = UserAuditLog.query.filter(UserAuditLog.created_at < limite_utc(antes_de))
    cantidad = consulta.count()
    if not ejecutar:
        return cantidad, 0
    if confirmar != antes_de.isoformat():
        raise ValueError("La confirmación no coincide con la fecha de corte.")
    borradas = consulta.delete(synchronize_session=False)
    db.session.commit()
    return cantidad, borradas


def purgar_enlaces(antes_de, ejecutar=False, confirmar=None):
    """Enlaces de recuperación usados o vencidos, creados antes del corte (B5). Devuelve (cantidad, borrados)."""
    from sqlalchemy import or_

    from models import db
    from models.core.user_recovery_token import UserRecoveryToken

    ahora = datetime.now(timezone.utc)
    consulta = UserRecoveryToken.query.filter(
        UserRecoveryToken.created_at < limite_utc(antes_de),
        or_(UserRecoveryToken.used_at.isnot(None), UserRecoveryToken.expires_at <= ahora),
    )
    cantidad = consulta.count()
    if not ejecutar:
        return cantidad, 0
    if confirmar != antes_de.isoformat():
        raise ValueError("La confirmación no coincide con la fecha de corte.")
    borrados = consulta.delete(synchronize_session=False)
    db.session.commit()
    return cantidad, borrados


def main(argv=None):
    parser = argparse.ArgumentParser(description="Purga manual de la auditoría de usuarios (simulación por defecto).")
    parser.add_argument("--antes-de", required=True, type=_fecha, help="AAAA-MM-DD; se purga lo anterior.")
    parser.add_argument("--ejecutar", action="store_true", help="Borra de verdad (requiere --confirmar).")
    parser.add_argument("--confirmar", default=None, help="Repetir la misma fecha de --antes-de.")
    args = parser.parse_args(argv)
    fecha = args.antes_de.isoformat()
    if args.ejecutar and args.confirmar != fecha:
        print(f"No se borra nada: --confirmar tiene que ser {fecha}.", file=sys.stderr)
        return 2
    sys.path.insert(0, RAIZ)
    from app import create_app

    aplicacion = create_app()
    with aplicacion.app_context():
        cantidad, borradas = purgar(args.antes_de, args.ejecutar, args.confirmar)
        enlaces, borrados_enlaces = purgar_enlaces(args.antes_de, args.ejecutar, args.confirmar)
    if args.ejecutar:
        print(f"Borradas {borradas} filas de auditoría anteriores al {fecha}.")
    else:
        print(
            f"Simulación: se borrarían {cantidad} filas anteriores al {fecha}. No se borró nada. "
            f"Para borrar: --ejecutar --confirmar {fecha}."
        )
    if args.ejecutar:
        print(f"Borrados {borrados_enlaces} enlaces de recuperación usados o vencidos anteriores al {fecha}.")
    else:
        print(f"Simulación: se borrarían {enlaces} enlaces de recuperación usados o vencidos anteriores al {fecha}. No se borró nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
