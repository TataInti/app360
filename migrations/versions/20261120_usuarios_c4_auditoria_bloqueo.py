"""Registro de accesos y bloqueo por cuenta (C4 de administración de usuarios).

Revision ID: 20261120_usuarios_c4_auditoria_bloqueo
Revises: 20261119_usuarios_c2_admin
Create Date: 2026-11-20

Aditiva y sin UPDATE masivos. users gana failed_login_count (NOT NULL, default 0),
failed_login_window_start y locked_until (NULL): los usuarios existentes quedan sin fallos ni
bloqueo. user_audit_log gana clave_agrupacion (NULL) y repeticiones (NOT NULL, default 1). El índice
único parcial ix_user_audit_log_agrupacion (solo filas con clave) hace atómica la agrupación de los
fallos de login. No se tocan password_hash, role, active, token_version ni deactivated_at. La versión
anterior de la aplicación no lee estas columnas, así que puede convivir con esta migración.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261120_usuarios_c4_auditoria_bloqueo"
down_revision = "20261119_usuarios_c2_admin"
branch_labels = None
depends_on = None


def _espera_acotada():
    # Si users o user_audit_log están ocupadas, la migración falla rápido y revierte (PostgreSQL).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '10s'")


def upgrade():
    _espera_acotada()
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("failed_login_window_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_audit_log",
        sa.Column("clave_agrupacion", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "user_audit_log",
        sa.Column("repeticiones", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_user_audit_log_agrupacion",
        "user_audit_log",
        ["clave_agrupacion"],
        unique=True,
        postgresql_where=sa.text("clave_agrupacion IS NOT NULL"),
        sqlite_where=sa.text("clave_agrupacion IS NOT NULL"),
    )


def downgrade():
    _espera_acotada()
    op.drop_index("ix_user_audit_log_agrupacion", table_name="user_audit_log")
    with op.batch_alter_table("user_audit_log") as lote:
        lote.drop_column("repeticiones")
        lote.drop_column("clave_agrupacion")
    with op.batch_alter_table("users") as lote:
        lote.drop_column("locked_until")
        lote.drop_column("failed_login_window_start")
        lote.drop_column("failed_login_count")
