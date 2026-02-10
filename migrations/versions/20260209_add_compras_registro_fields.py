"""Add fields for compras registro and tesoreria link

Revision ID: 20260209_add_compras_registro_fields
Revises: 0dd692d555b0
Create Date: 2026-02-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260209_add_compras_registro_fields"
down_revision = "fix_alembic_version_len"
branch_labels = None
depends_on = None


def table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not table_exists("purchase_orders"):
        return

    if not column_exists("purchase_orders", "comprobante_numero"):
        op.add_column(
            "purchase_orders",
            sa.Column("comprobante_numero", sa.String(length=100), nullable=True),
        )

    if not column_exists("purchase_orders", "monto_total"):
        op.add_column(
            "purchase_orders",
            sa.Column("monto_total", sa.Numeric(12, 2), nullable=True),
        )

    if not column_exists("purchase_orders", "instrumento_id"):
        op.add_column(
            "purchase_orders",
            sa.Column("instrumento_id", sa.Integer(), nullable=True),
        )
        if table_exists("instrumentos_pago"):
            op.create_foreign_key(
                "fk_purchase_orders_instrumento_id",
                "purchase_orders",
                "instrumentos_pago",
                ["instrumento_id"],
                ["id"],
            )

    if not column_exists("purchase_orders", "tesoreria_movimiento_id"):
        op.add_column(
            "purchase_orders",
            sa.Column("tesoreria_movimiento_id", sa.Integer(), nullable=True),
        )
        if table_exists("movimientos_caja"):
            op.create_foreign_key(
                "fk_purchase_orders_movimiento_id",
                "purchase_orders",
                "movimientos_caja",
                ["tesoreria_movimiento_id"],
                ["id"],
            )


def downgrade():
    # No destructive downgrade to avoid data loss
    pass
