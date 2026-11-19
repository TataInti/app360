"""Clave temporal obligatoria y fechas de acceso en users (C1 de administración de usuarios).

Revision ID: 20261119_usuarios_c1_clave
Revises: 20261029_objetivos_comerciales_lineas
Create Date: 2026-11-19

Aditiva: tres columnas nuevas en users, con default seguro. must_change_password queda en
false y las fechas en NULL, así que los usuarios existentes conservan su clave, su rol, su
estado activo y sus sesiones. No hace UPDATE masivos ni toca password_hash.
La versión anterior de la aplicación sigue funcionando después de esta migración: no lee
las columnas nuevas. Por eso puede aplicarse antes de reiniciar.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261119_usuarios_c1_clave"
down_revision = "20261029_objetivos_comerciales_lineas"
branch_labels = None
depends_on = None


def _espera_acotada():
    # Si la tabla users está ocupada, la migración falla rápido y revierte la transacción
    # (PostgreSQL). No encola detrás de transacciones largas.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '10s'")


def upgrade():
    _espera_acotada()
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    _espera_acotada()
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("password_changed_at")
        batch_op.drop_column("must_change_password")
