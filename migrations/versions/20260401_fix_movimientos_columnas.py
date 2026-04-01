"""Agregar columnas faltantes a movimientos_caja: categoria_gasto_id, proveedor_id.

La migración 20260317_mov_cat_prov fue stamped sin ejecutarse realmente.
Esta migración agrega las columnas que deben existir según el modelo actual.
Se deja destino_id en su lugar ya que aún existe en la DB.

Revision ID: 20260401_fix_mov_cols
Revises: 20260401_portador_drop_gasto
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision = '20260401_fix_mov_cols'
down_revision = '20260401_portador_drop_gasto'
branch_labels = None
depends_on = None


def _col_exists(table, col):
    bind = op.get_bind()
    insp = sa_inspect(bind)
    return col in [c['name'] for c in insp.get_columns(table)]


def upgrade():
    with op.batch_alter_table('movimientos_caja') as batch_op:
        if not _col_exists('movimientos_caja', 'categoria_gasto_id'):
            batch_op.add_column(
                sa.Column('categoria_gasto_id', sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                'fk_mov_categoria_gasto', 'categoria_gasto',
                ['categoria_gasto_id'], ['id']
            )

        if not _col_exists('movimientos_caja', 'proveedor_id'):
            batch_op.add_column(
                sa.Column('proveedor_id', sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                'fk_mov_proveedor', 'proveedor',
                ['proveedor_id'], ['id']
            )


def downgrade():
    with op.batch_alter_table('movimientos_caja') as batch_op:
        if _col_exists('movimientos_caja', 'proveedor_id'):
            batch_op.drop_constraint('fk_mov_proveedor', type_='foreignkey')
            batch_op.drop_column('proveedor_id')
        if _col_exists('movimientos_caja', 'categoria_gasto_id'):
            batch_op.drop_constraint('fk_mov_categoria_gasto', type_='foreignkey')
            batch_op.drop_column('categoria_gasto_id')
