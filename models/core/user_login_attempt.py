"""Contadores de login por par (cuenta, IP), añadidos en C4-fix."""

from .. import db


class UserLoginAttempt(db.Model):
    __tablename__ = "user_login_attempts"
    __table_args__ = (db.Index("ix_user_login_attempts_updated_at", "updated_at"),)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ip = db.Column(db.String(45), primary_key=True)
    failed_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    window_start = db.Column(db.DateTime(timezone=True), nullable=False)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
