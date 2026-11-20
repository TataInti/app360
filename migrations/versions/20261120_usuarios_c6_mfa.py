"""MFA opcional con aplicación de códigos y códigos de respaldo (C6 de administración de usuarios).

Revision ID: 20261120_usuarios_c6_mfa
Revises: 20261120_usuarios_c5_recuperacion
Create Date: 2026-11-20

Aditiva. users gana: mfa_enabled (NOT NULL, por defecto falso: los usuarios actuales siguen sin MFA),
mfa_secret y mfa_secret_pendiente (VARCHAR(64), NULL), mfa_pendiente_expira, mfa_last_step (último paso
TOTP aceptado, para no reutilizar un código) y mfa_activado_en (se suma a la huella de sesión solo
cuando el MFA se activó). Crea user_mfa_backup_codes con el hash salado de cada código de respaldo.
No toca password_hash, role, active, token_version ni las columnas de C4 y C5.

Downgrade explícito: borra la tabla de códigos de respaldo y las columnas de MFA (los secretos se pierden;
los usuarios que tenían MFA vuelven a entrar solo con su clave).
"""

import sqlalchemy as sa
from alembic import op

revision = "20261120_usuarios_c6_mfa"
down_revision = "20261120_usuarios_c5_recuperacion"
branch_labels = None
depends_on = None

COLUMNAS = (
    ("mfa_enabled", sa.Boolean()),
    ("mfa_secret", sa.String(length=64)),
    ("mfa_secret_pendiente", sa.String(length=64)),
    ("mfa_pendiente_expira", sa.DateTime(timezone=True)),
    ("mfa_last_step", sa.BigInteger()),
    ("mfa_activado_en", sa.DateTime(timezone=True)),
)


def _espera_acotada():
    # Si users está ocupada, la migración falla rápido y revierte (PostgreSQL).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '10s'")


def _columnas_existentes():
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns("users")}


def _tabla_existe(nombre):
    return sa.inspect(op.get_bind()).has_table(nombre)


def upgrade():
    _espera_acotada()
    existentes = _columnas_existentes()
    for nombre, tipo in COLUMNAS:
        if nombre in existentes:
            continue
        if nombre == "mfa_enabled":
            op.add_column(
                "users",
                sa.Column(
                    nombre,
                    tipo,
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        else:
            op.add_column("users", sa.Column(nombre, tipo, nullable=True))
    if not _tabla_existe("user_mfa_backup_codes"):
        op.create_table(
            "user_mfa_backup_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_hash", sa.CHAR(length=64), nullable=False),
            sa.Column("salt", sa.CHAR(length=32), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_user_mfa_backup_codes_user_id",
            "user_mfa_backup_codes",
            ["user_id"],
        )


def downgrade():
    _espera_acotada()
    if _tabla_existe("user_mfa_backup_codes"):
        op.drop_index("ix_user_mfa_backup_codes_user_id", table_name="user_mfa_backup_codes")
        op.drop_table("user_mfa_backup_codes")
    existentes = _columnas_existentes()
    for nombre, _tipo in reversed(COLUMNAS):
        if nombre in existentes:
            op.drop_column("users", nombre)
