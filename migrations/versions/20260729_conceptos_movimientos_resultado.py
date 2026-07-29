"""Add structural Treasury concepts and result participation.

Revision ID: 20260729_conceptos_resultado
Revises: 20260713_sabiogo_sync_runs
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260729_conceptos_resultado"
down_revision = "20260713_sabiogo_sync_runs"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    return any(
        column["name"] == column_name
        for column in inspect(op.get_bind()).get_columns(table_name)
    )


def _table_exists(table_name):
    return table_name in inspect(op.get_bind()).get_table_names()


def _check_exists(table_name, constraint_name):
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspect(op.get_bind()).get_check_constraints(table_name)
    )


def upgrade():
    if not _column_exists("categoria_gasto", "naturaleza"):
        with op.batch_alter_table("categoria_gasto") as batch_op:
            batch_op.add_column(sa.Column("naturaleza", sa.String(length=10), nullable=True))

    if not _column_exists("categoria_gasto", "incluye_resultado"):
        with op.batch_alter_table("categoria_gasto") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "incluye_resultado",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    if not _check_exists("categoria_gasto", "chk_categoria_gasto_naturaleza"):
        with op.batch_alter_table("categoria_gasto") as batch_op:
            batch_op.create_check_constraint(
                "chk_categoria_gasto_naturaleza",
                "naturaleza IS NULL OR naturaleza IN ('ingreso', 'egreso', 'ambos')",
            )

    bind = op.get_bind()
    bind.execute(
        text(
            """
            UPDATE categoria_gasto AS c
            SET naturaleza = CASE
                WHEN EXISTS (
                    SELECT 1 FROM movimientos_caja m
                    WHERE m.categoria_gasto_id = c.id
                      AND m.tipo = 'ingreso'
                      AND LOWER(COALESCE(m.estado, 'activo')) <> 'anulado'
                ) AND EXISTS (
                    SELECT 1 FROM movimientos_caja m
                    WHERE m.categoria_gasto_id = c.id
                      AND m.tipo = 'egreso'
                      AND LOWER(COALESCE(m.estado, 'activo')) <> 'anulado'
                ) THEN 'ambos'
                WHEN EXISTS (
                    SELECT 1 FROM movimientos_caja m
                    WHERE m.categoria_gasto_id = c.id
                      AND m.tipo = 'ingreso'
                      AND LOWER(COALESCE(m.estado, 'activo')) <> 'anulado'
                ) THEN 'ingreso'
                WHEN EXISTS (
                    SELECT 1 FROM movimientos_caja m
                    WHERE m.categoria_gasto_id = c.id
                      AND m.tipo = 'egreso'
                      AND LOWER(COALESCE(m.estado, 'activo')) <> 'anulado'
                ) THEN 'egreso'
                ELSE naturaleza
            END
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE categoria_gasto
            SET naturaleza = 'egreso', incluye_resultado = true
            WHERE UPPER(TRIM(nombre)) = 'SUELDOS'
            """
        )
    )
    bind.execute(
        text(
            """
            INSERT INTO categoria_gasto (
                nombre, descripcion, activo, naturaleza, incluye_resultado
            )
            VALUES (
                'EFECTIVO IVA',
                'Ingreso de tesorería incluido en el resultado comercial.',
                true,
                'ingreso',
                true
            )
            ON CONFLICT (nombre) DO UPDATE
            SET naturaleza = EXCLUDED.naturaleza,
                incluye_resultado = EXCLUDED.incluye_resultado
            """
        )
    )

    if not _table_exists("categoria_movimiento_audit"):
        op.create_table(
            "categoria_movimiento_audit",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("categoria_id", sa.Integer(), nullable=False),
            sa.Column("usuario_id", sa.Integer(), nullable=True),
            sa.Column("fecha", sa.DateTime(), nullable=False),
            sa.Column("accion", sa.String(length=20), nullable=False),
            sa.Column("valores_anteriores", sa.JSON(), nullable=False),
            sa.Column("valores_nuevos", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["categoria_id"], ["categoria_gasto.id"]),
            sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_categoria_movimiento_audit_categoria_id",
            "categoria_movimiento_audit",
            ["categoria_id"],
        )
        op.create_index(
            "ix_categoria_movimiento_audit_fecha",
            "categoria_movimiento_audit",
            ["fecha"],
        )


def downgrade():
    if _table_exists("categoria_movimiento_audit"):
        op.drop_table("categoria_movimiento_audit")

    if _check_exists("categoria_gasto", "chk_categoria_gasto_naturaleza"):
        with op.batch_alter_table("categoria_gasto") as batch_op:
            batch_op.drop_constraint(
                "chk_categoria_gasto_naturaleza",
                type_="check",
            )
    if _column_exists("categoria_gasto", "incluye_resultado"):
        with op.batch_alter_table("categoria_gasto") as batch_op:
            batch_op.drop_column("incluye_resultado")
    if _column_exists("categoria_gasto", "naturaleza"):
        with op.batch_alter_table("categoria_gasto") as batch_op:
            batch_op.drop_column("naturaleza")
