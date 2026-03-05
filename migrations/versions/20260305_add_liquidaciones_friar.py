"""Crear tabla liquidaciones_friar

Revision ID: 20260305_add_liquidaciones_friar
Revises: 20260305_add_anulacion_movimientos
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa

revision = '20260305_add_liquidaciones_friar'
down_revision = '20260305_add_anulacion_movimientos'
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t)"
    ), {"t": name})
    return result.scalar()


def upgrade():
    conn = op.get_bind()
    if _table_exists(conn, "liquidaciones_friar"):
        return

    op.create_table(
        'liquidaciones_friar',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cuenta_corriente_id', sa.Integer(),
                   sa.ForeignKey('cuenta_corriente_friar.id'), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('monto', sa.Numeric(12, 2), nullable=False),
        sa.Column('tipo', sa.String(50), nullable=False, server_default='consignado'),
        sa.Column('descripcion', sa.String(200), nullable=False),
        sa.Column('referencia', sa.String(100), nullable=True),
        sa.Column('usuario_id', sa.Integer(),
                   sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_liquidacion_friar_fecha', 'liquidaciones_friar', ['fecha'])
    op.create_index('idx_liquidacion_friar_cuenta', 'liquidaciones_friar', ['cuenta_corriente_id'])


def downgrade():
    op.drop_index('idx_liquidacion_friar_cuenta', table_name='liquidaciones_friar')
    op.drop_index('idx_liquidacion_friar_fecha', table_name='liquidaciones_friar')
    op.drop_table('liquidaciones_friar')
