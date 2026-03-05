"""Add anulacion fields to movimientos_caja

Revision ID: 20260305_add_anulacion_movimientos
Revises: 20260219_add_sabiogo_origen_and_batch_import
Create Date: 2026-03-05 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260305_add_anulacion_movimientos"
down_revision = "20260219_add_sabiogo_origen_and_batch_import"
branch_labels = None
depends_on = None


def _column_exists(table, column):
    bind = op.get_bind()
    insp = inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols


def upgrade():
    cols = [
        ("estado", sa.String(25), False, "activo"),
        ("motivo_anulacion", sa.Text(), True, None),
        ("anulado_por_id", sa.Integer(), True, None),
        ("autorizado_por_id", sa.Integer(), True, None),
        ("fecha_anulacion", sa.DateTime(), True, None),
    ]
    for col_name, col_type, nullable, default in cols:
        if not _column_exists("movimientos_caja", col_name):
            kw = {}
            if default is not None:
                kw["server_default"] = default
            op.add_column(
                "movimientos_caja",
                sa.Column(col_name, col_type, nullable=nullable, **kw),
            )

    # FK constraints
    bind = op.get_bind()
    insp = inspect(bind)
    existing_fks = [fk["name"] for fk in insp.get_foreign_keys("movimientos_caja") if fk.get("name")]

    if "fk_movimiento_anulado_por" not in existing_fks:
        if _column_exists("movimientos_caja", "anulado_por_id"):
            op.create_foreign_key(
                "fk_movimiento_anulado_por",
                "movimientos_caja", "users",
                ["anulado_por_id"], ["id"],
            )
    if "fk_movimiento_autorizado_por" not in existing_fks:
        if _column_exists("movimientos_caja", "autorizado_por_id"):
            op.create_foreign_key(
                "fk_movimiento_autorizado_por",
                "movimientos_caja", "users",
                ["autorizado_por_id"], ["id"],
            )

    # Index on estado
    existing_indexes = [idx["name"] for idx in insp.get_indexes("movimientos_caja")]
    if "idx_movimiento_estado" not in existing_indexes:
        op.create_index("idx_movimiento_estado", "movimientos_caja", ["estado"])


def downgrade():
    op.drop_index("idx_movimiento_estado", table_name="movimientos_caja")
    op.drop_constraint("fk_movimiento_autorizado_por", "movimientos_caja", type_="foreignkey")
    op.drop_constraint("fk_movimiento_anulado_por", "movimientos_caja", type_="foreignkey")
    op.drop_column("movimientos_caja", "fecha_anulacion")
    op.drop_column("movimientos_caja", "autorizado_por_id")
    op.drop_column("movimientos_caja", "anulado_por_id")
    op.drop_column("movimientos_caja", "motivo_anulacion")
    op.drop_column("movimientos_caja", "estado")
