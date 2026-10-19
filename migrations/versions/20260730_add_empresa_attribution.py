"""Add nullable company attribution to operational financial records.

Existing rows intentionally remain ``NULL``: they are historical/global and
must only be included by the ``TODAS`` analytical scope.

Revision ID: 20260730_add_empresa_attribution
Revises: 20260729_ensure_efectivo_iva
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260730_add_empresa_attribution"
down_revision = "20260729_ensure_efectivo_iva"
branch_labels = None
depends_on = None


EMPRESA_CHECK = "empresa IS NULL OR empresa IN ('CARNES', 'LACTEOS')"


def _table_exists(table_name):
    return table_name in inspect(op.get_bind()).get_table_names()


def _column_exists(table_name, column_name):
    if not _table_exists(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in inspect(op.get_bind()).get_columns(table_name)
    )


def _columns_exist(table_name, column_names):
    return all(_column_exists(table_name, column_name) for column_name in column_names)


def _check_exists(table_name, constraint_name):
    if not _table_exists(table_name):
        return False
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspect(op.get_bind()).get_check_constraints(table_name)
    )


def _index_exists(table_name, index_name):
    if not _table_exists(table_name):
        return False
    return any(
        index.get("name") == index_name
        for index in inspect(op.get_bind()).get_indexes(table_name)
    )


def _ensure_empresa(table_name, constraint_name, index_name, index_columns):
    """Add the nullable attribute, its controlled-code check and its index.

    Each guard is independent so the revision can repair a database where a
    previous deployment stopped after adding only a subset of the objects.
    """
    if not _table_exists(table_name):
        return

    if not _column_exists(table_name, "empresa"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("empresa", sa.String(length=10), nullable=True))

    if not _check_exists(table_name, constraint_name):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_check_constraint(constraint_name, EMPRESA_CHECK)

    if (
        not _index_exists(table_name, index_name)
        and _columns_exist(table_name, index_columns)
    ):
        op.create_index(index_name, table_name, index_columns)


def upgrade():
    _ensure_empresa(
        "movimientos_caja",
        "chk_movimientos_caja_empresa",
        "idx_movimiento_empresa_fecha",
        ["empresa", "fecha_hora"],
    )
    _ensure_empresa(
        "adelantos",
        "chk_adelantos_empresa",
        "idx_adelantos_empresa_fecha_pago",
        ["empresa", "fecha_pago"],
    )
    _ensure_empresa(
        "liquidaciones_sueldo",
        "chk_liquidaciones_sueldo_empresa",
        "idx_liquidaciones_sueldo_empresa_fecha",
        ["empresa", "fecha_liquidacion"],
    )
    _ensure_empresa(
        "employees",
        "chk_employees_empresa",
        "idx_employees_empresa",
        ["empresa"],
    )
    _ensure_empresa(
        "purchase_orders",
        "chk_purchase_orders_empresa",
        "idx_purchase_orders_empresa_order_date",
        ["empresa", "order_date"],
    )


def downgrade():
    # A downgrade must not discard company attribution from operational data.
    pass
