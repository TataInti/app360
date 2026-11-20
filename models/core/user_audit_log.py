"""Auditoría de la administración de usuarios (C2): una fila por acción, solo inserción desde la app.

Guarda quién actuó, sobre quién, qué acción y un detalle mínimo. Nunca guarda claves, hashes,
tokens ni correos completos: el detalle pasa por un filtro en services/usuarios_admin.py.
Migración: 20261119_usuarios_c2_admin.
"""

from .. import db


class UserAuditLog(db.Model):
    __tablename__ = "user_audit_log"
    __table_args__ = (
        db.Index("ix_user_audit_log_created_at", "created_at"),
        db.Index("ix_user_audit_log_target", "target_user_id", "created_at"),
        db.Index("ix_user_audit_log_actor", "actor_user_id"),
        # Agrupación de fallos de login (C4): una fila por IP, motivo, cuenta y minuto.
        db.Index(
            "ix_user_audit_log_agrupacion",
            "clave_agrupacion",
            unique=True,
            postgresql_where=db.text("clave_agrupacion IS NOT NULL"),
            sqlite_where=db.text("clave_agrupacion IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_username = db.Column(db.String(80), nullable=True)
    accion = db.Column(db.String(40), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_username = db.Column(db.String(80), nullable=True)
    detalle = db.Column(db.JSON, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    # C4 (migración 20261120_usuarios_c4_auditoria_bloqueo): clave de agrupación de los fallos de login y
    # cantidad de intentos agrupados. Las acciones administrativas no la usan: repeticiones queda en 1.
    clave_agrupacion = db.Column(db.String(200), nullable=True)
    repeticiones = db.Column(db.Integer, nullable=False, default=1, server_default="1")
