"""Store per-client document inclusion criteria for the sales dashboard.

Revision ID: 20261021_comercial_cliente_criterio
Revises: 20261020_objetivo_vinculos
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261021_comercial_cliente_criterio"
down_revision = "20261020_objetivo_vinculos"
branch_labels = None
depends_on = None


def _table_exists(table_name):
    return table_name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _table_exists("comercial_cliente_criterio"):
        op.create_table(
            "comercial_cliente_criterio",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cliente", sa.String(length=255), nullable=False),
            sa.Column(
                "criterio",
                sa.String(length=3),
                nullable=False,
                server_default="PRE",
            ),
            sa.Column("actualizado_por", sa.String(length=120), nullable=False),
            sa.Column(
                "actualizado_en",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "cliente",
                name="uq_comercial_cliente_criterio_cliente",
            ),
            sa.CheckConstraint(
                "criterio IN ('PRE', 'FAC')",
                name="ck_comercial_cliente_criterio_tipo",
            ),
        )

    index_name = "ix_comercial_cliente_criterio_criterio"
    existing_indexes = {
        index["name"]
        for index in inspect(op.get_bind()).get_indexes("comercial_cliente_criterio")
    }
    if index_name not in existing_indexes:
        op.create_index(
            index_name,
            "comercial_cliente_criterio",
            ["criterio"],
            unique=False,
        )


def downgrade():
    if _table_exists("comercial_cliente_criterio"):
        op.drop_table("comercial_cliente_criterio")
