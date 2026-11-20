from datetime import datetime, timezone

from .. import db


class UserMfaBackupCode(db.Model):
    """Código de respaldo del MFA (C6). Guarda solo el hash salado (SHA-256), nunca el código.

    Cada código es de un solo uso: used_at se fija con un UPDATE condicional (used_at IS NULL).
    Regenerar o desactivar borra las filas del usuario.
    """

    __tablename__ = "user_mfa_backup_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash = db.Column(db.CHAR(64), nullable=False)
    salt = db.Column(db.CHAR(32), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
