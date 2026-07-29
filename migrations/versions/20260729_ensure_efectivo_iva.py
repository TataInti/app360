"""Ensure the structural EFECTIVO IVA concept exists.

This reconciliation revision also covers local databases that had already
applied the first, unreleased revision of the result-concepts migration.

Revision ID: 20260729_ensure_efectivo_iva
Revises: 20260729_conceptos_resultado
Create Date: 2026-07-29
"""

from alembic import op
from sqlalchemy import text


revision = "20260729_ensure_efectivo_iva"
down_revision = "20260729_conceptos_resultado"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(
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


def downgrade():
    # El concepto puede tener movimientos históricos; nunca se elimina en un
    # downgrade automático.
    pass
