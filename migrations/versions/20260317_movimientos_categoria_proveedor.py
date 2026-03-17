"""movimientos_caja: reemplazar destino_id con categoria_gasto_id y proveedor_id

Revision ID: 20260317_mov_cat_prov
Revises: 20260305_add_arqueo_detalle
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = '20260317_mov_cat_prov'
down_revision = '20260305_add_arqueo_detalle'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('movimientos_caja') as batch_op:
        batch_op.add_column(sa.Column('categoria_gasto_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('proveedor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_movimiento_categoria_gasto', 'categoria_gasto',
            ['categoria_gasto_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_movimiento_proveedor', 'proveedor',
            ['proveedor_id'], ['id']
        )
        batch_op.drop_column('destino_id')


def downgrade():
    with op.batch_alter_table('movimientos_caja') as batch_op:
        batch_op.add_column(sa.Column('destino_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('fk_movimiento_proveedor', type_='foreignkey')
        batch_op.drop_constraint('fk_movimiento_categoria_gasto', type_='foreignkey')
        batch_op.drop_column('proveedor_id')
        batch_op.drop_column('categoria_gasto_id')
