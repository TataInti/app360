"""Clave temporal de 72 horas, versión de token y auditoría de usuarios (C2 de administración).

Revision ID: 20261119_usuarios_c2_admin
Revises: 20261119_usuarios_c1_clave
Create Date: 2026-11-19

Aditiva. users gana token_version (NOT NULL, default 0), temp_password_expires_at y deactivated_at
(NULL). Se crea user_audit_log, de solo inserción desde la aplicación, con tres índices. Los
usuarios existentes no cambian: versión 0, sin vencimiento y sin baja. No hay UPDATE masivos y no
se tocan password_hash, role ni active. La versión anterior de la aplicación no lee estas columnas,
así que puede aplicarse antes de reiniciar.

Unicidad sin distinguir mayúsculas (A4): se crea el índice único ix_users_username_lower sobre
lower(username). Antes, la migración verifica que no haya nombres duplicados sin distinguir
mayúsculas. Si los hay, aborta y lista esos nombres: no borra ni cambia filas, y el esquema queda
como estaba.
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


def _verificar_sin_duplicados_sin_mayusculas():
    """Aborta si hay nombres que solo difieren en mayúsculas. Corre antes de tocar el esquema."""
    conexion = op.get_bind()
    claves = [
        fila[0]
        for fila in conexion.execute(
            sa.text(
                "SELECT lower(username) FROM users GROUP BY lower(username) "
                "HAVING COUNT(*) > 1 ORDER BY 1"
            )
        ).fetchall()
    ]
    if not claves:
        return
    nombres = []
    for clave in claves:
        filas = conexion.execute(
            sa.text("SELECT username FROM users WHERE lower(username) = :clave ORDER BY username"),
            {"clave": clave},
        ).fetchall()
        nombres.extend(fila[0] for fila in filas)
    listado = ", ".join(f"«{nombre}»" for nombre in nombres)
    raise RuntimeError(
        "No se crea el índice ix_users_username_lower: hay nombres de usuario duplicados sin "
        f"distinguir mayúsculas: {listado}. La migración no borró ni cambió nada. Resolvé los "
        "duplicados a mano y volvé a correr la migración."
    )


def upgrade():
    _espera_acotada()
    _verificar_sin_duplicados_sin_mayusculas()
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
    op.create_index("ix_user_audit_log_actor", "user_audit_log", ["actor_user_id"])
    op.execute("CREATE UNIQUE INDEX ix_users_username_lower ON users (lower(username))")


def downgrade():
    _espera_acotada()
    op.drop_index("ix_users_username_lower", table_name="users")
    op.drop_index("ix_user_audit_log_actor", table_name="user_audit_log")
    op.drop_index("ix_user_audit_log_target", table_name="user_audit_log")
    op.drop_index("ix_user_audit_log_created_at", table_name="user_audit_log")
    op.drop_table("user_audit_log")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("deactivated_at")
        batch_op.drop_column("temp_password_expires_at")
        batch_op.drop_column("token_version")
