"""Clave temporal de 72 horas, versión de token y auditoría de usuarios (C2 de administración).

Revision ID: 20261119_usuarios_c2_admin
Revises: 20261119_usuarios_c1_clave
Create Date: 2026-11-19

Aditiva. users gana token_version (NOT NULL, default 0), temp_password_expires_at y deactivated_at
(NULL). Se crea user_audit_log, de solo inserción desde la aplicación, con dos índices. Los
usuarios existentes no cambian: versión 0, sin vencimiento y sin baja. No hay UPDATE masivos y no
se tocan password_hash, role ni active. La versión anterior de la aplicación no lee estas columnas,
así que puede aplicarse antes de reiniciar.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261119_usuarios_c2_admin"
down_revision = "20261119_usuarios_c1_clave"
branch_labels = None
depends_on = None


def _espera_acotada():
    # Si users o la tabla nueva están ocupadas, la migración falla rápido y revierte (PostgreSQL).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '10s'")


def upgrade():
    _espera_acotada()
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("temp_password_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "user_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_username", sa.String(length=80), nullable=True),
        sa.Column("accion", sa.String(length=40), nullable=False),
        sa.Column(
            "target_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_username", sa.String(length=80), nullable=True),
        sa.Column("detalle", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
    )
    op.create_index("ix_user_audit_log_created_at", "user_audit_log", ["created_at"])
    op.create_index("ix_user_audit_log_target", "user_audit_log", ["target_user_id", "created_at"])


def downgrade():
    _espera_acotada()
    op.drop_index("ix_user_audit_log_target", table_name="user_audit_log")
    op.drop_index("ix_user_audit_log_created_at", table_name="user_audit_log")
    op.drop_table("user_audit_log")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("deactivated_at")
        batch_op.drop_column("temp_password_expires_at")
        batch_op.drop_column("token_version")
