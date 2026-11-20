"""Enlaces de recuperación de clave (C5): una fila por enlace, sin guardar nunca el enlace.

La fila guarda solo el SHA-256 del token (token_hash, CHAR(64), único). Un enlace nuevo revoca los
vigentes del mismo usuario. Migración: 20261120_usuarios_c5_recuperacion.
"""

from .. import db


class UserRecoveryToken(db.Model):
    __tablename__ = "user_recovery_tokens"
    __table_args__ = (
        db.Index("ix_user_recovery_tokens_user_id", "user_id"),
        db.Index("ix_user_recovery_tokens_expires_at", "expires_at"),
        # Límite de emisiones por administrador (5 cada 10 minutos).
        db.Index("ix_user_recovery_tokens_emision", "created_by_user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = db.Column(db.CHAR(64), nullable=False, unique=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.text("CURRENT_TIMESTAMP")
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_username = db.Column(db.String(80), nullable=True)
    ip = db.Column(db.String(45), nullable=True)
