"""Correo opcional y enlaces de recuperación de clave (C5 de administración de usuarios).

Revision ID: 20261120_usuarios_c5_recuperacion
Revises: 20261120_usuarios_c4_auditoria_bloqueo
Create Date: 2026-11-20

Aditiva. users gana email (VARCHAR(254), NULL) y el índice único parcial ix_users_email_lower sobre
lower(email), que solo cubre filas con correo. Antes de crear el índice verifica que no haya correos
repetidos sin distinguir mayúsculas: si los hay, aborta con un mensaje claro (sin mostrar correos).
Crea user_recovery_tokens, que guarda solo el SHA-256 de cada enlace. No toca password_hash, role,
active, token_version ni las columnas de C4. La versión anterior de la aplicación no lee estas
columnas ni tablas, así que puede convivir con esta migración.

Downgrade: borra la tabla de enlaces y la columna email (los correos cargados se pierden).
"""

import sqlalchemy as sa
from alembic import op

revision = "20261120_usuarios_c5_recuperacion"
down_revision = "20261120_usuarios_c4_auditoria_bloqueo"
branch_labels = None
depends_on = None

INDICE_CORREO = "ix_users_email_lower"


def _espera_acotada():
    # Si users está ocupada, la migración falla rápido y revierte (PostgreSQL).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '10s'")


def _columna_existe(tabla, columna):
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == columna for col in inspector.get_columns(tabla))


def _verificar_correos_unicos():
    repetidos = op.get_bind().execute(
        sa.text(
            "SELECT lower(email) FROM users WHERE email IS NOT NULL "
            "GROUP BY lower(email) HAVING count(*) > 1"
        )
    ).fetchall()
    if repetidos:
        raise RuntimeError(
            f"No se puede crear el índice de correos: hay {len(repetidos)} correo(s) repetido(s) "
            "sin distinguir mayúsculas en users.email. Corregí los duplicados y volvé a correr la "
            "migración. No se aplicó ningún cambio."
        )


def upgrade():
    _espera_acotada()
    if not _columna_existe("users", "email"):
        op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    _verificar_correos_unicos()
    op.execute(
        f"CREATE UNIQUE INDEX {INDICE_CORREO} ON users (lower(email)) WHERE email IS NOT NULL"
    )
    op.create_table(
        "user_recovery_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_username", sa.String(length=80), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
    )
    op.create_index("ix_user_recovery_tokens_user_id", "user_recovery_tokens", ["user_id"])
    op.create_index("ix_user_recovery_tokens_expires_at", "user_recovery_tokens", ["expires_at"])
    op.create_index(
        "ix_user_recovery_tokens_emision",
        "user_recovery_tokens",
        ["created_by_user_id", "created_at"],
    )


def downgrade():
    _espera_acotada()
    op.drop_index("ix_user_recovery_tokens_emision", table_name="user_recovery_tokens")
    op.drop_index("ix_user_recovery_tokens_expires_at", table_name="user_recovery_tokens")
    op.drop_index("ix_user_recovery_tokens_user_id", table_name="user_recovery_tokens")
    op.drop_table("user_recovery_tokens")
    op.execute(f"DROP INDEX IF EXISTS {INDICE_CORREO}")
    with op.batch_alter_table("users") as lote:
        lote.drop_column("email")
