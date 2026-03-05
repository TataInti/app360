"""Crear tabla arqueo_detalle (desglose por instrumento)

Revision ID: 20260305_add_arqueo_detalle
Revises: 20260305_add_liquidaciones_friar
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa

revision = '20260305_add_arqueo_detalle'
down_revision = '20260305_add_liquidaciones_friar'
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
    if _table_exists(conn, "arqueo_detalle"):
        return

    op.create_table(
        'arqueo_detalle',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('arqueo_id', sa.Integer(),
                   sa.ForeignKey('arqueos_caja.id'), nullable=False),
        sa.Column('instrumento_id', sa.Integer(),
                   sa.ForeignKey('instrumentos_pago.id'), nullable=False),
        sa.Column('conteo_real', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('saldo_calculado', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('diferencia', sa.Numeric(12, 2), nullable=False, server_default='0'),
    )
    op.create_unique_constraint('unique_arqueo_instrumento', 'arqueo_detalle',
                                ['arqueo_id', 'instrumento_id'])


def downgrade():
    op.drop_constraint('unique_arqueo_instrumento', 'arqueo_detalle', type_='unique')
    op.drop_table('arqueo_detalle')
