"""Último recurso del MFA (C6, M5): restablece el MFA de una cuenta desde el servidor.

Uso (solo con acceso al servidor; no se ejecuta contra producción sin autorización):
    python scripts/restablecer_mfa.py --usuario <nombre>              simulación: no cambia nada
    python scripts/restablecer_mfa.py --usuario <nombre> --confirmar  aplica el cambio

Borra secreto y códigos de respaldo, suma token_version (cierra sesiones y JWT de la cuenta) y registra
la auditoría user_mfa_reset con actor «script». La persona entra con su clave y puede activar el MFA otra vez.
"""

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def restablecer(usuario_nombre, confirmar):
    from models import db
    from models.core.user import User
    from models.core.user_audit_log import UserAuditLog
    from models.core.user_mfa_backup_code import UserMfaBackupCode
    from security import ahora

    usuario = User.query.filter(User.username == usuario_nombre).with_for_update().one_or_none()
    if usuario is None:
        db.session.rollback()
        return {"estado": "no_encontrado", "usuario": usuario_nombre}
    if usuario.mfa_enabled is not True:
        db.session.rollback()
        return {"estado": "sin_mfa", "usuario": usuario.username}
    if not confirmar:
        db.session.rollback()
        return {"estado": "simulado", "usuario": usuario.username, "rol": usuario.role}
    instante = ahora()
    UserMfaBackupCode.query.filter_by(user_id=usuario.id).delete(synchronize_session=False)
    usuario.mfa_enabled = False
    usuario.mfa_secret = None
    usuario.mfa_secret_pendiente = None
    usuario.mfa_pendiente_expira = None
    usuario.token_version = (usuario.token_version or 0) + 1
    db.session.add(
        UserAuditLog(
            created_at=instante,
            actor_user_id=None,
            actor_username="script",
            accion="user_mfa_reset",
            target_user_id=usuario.id,
            target_username=usuario.username,
            detalle={},
            ip=None,
            clave_agrupacion=None,
            repeticiones=1,
        )
    )
    db.session.commit()
    return {"estado": "restablecido", "usuario": usuario.username, "rol": usuario.role}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Restablece el MFA de una cuenta desde el servidor.")
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--confirmar", action="store_true", help="aplica el cambio (sin esto solo simula)")
    args = parser.parse_args(argv)
    from app import create_app

    aplicacion = create_app()
    with aplicacion.app_context():
        resultado = restablecer(args.usuario, args.confirmar)
    print(f"RESULTADO {resultado['estado']} usuario={resultado.get('usuario')}")
    return 0 if resultado["estado"] in ("simulado", "restablecido") else 1


if __name__ == "__main__":
    sys.exit(main())
