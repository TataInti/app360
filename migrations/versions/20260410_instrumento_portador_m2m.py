"""Add instrumento_portador many-to-many association table

Revision ID: 20260410_instrumento_portador_m2m
Revises: 20260401_fichadas_nullable
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260410_instrumento_portador_m2m'
down_revision = '20260401_fichadas_nullable'
branch_labels = None
depends_on = None


def table_exists(name):
    return name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if not table_exists('instrumento_portador'):
        op.create_table(
            'instrumento_portador',
            sa.Column(
                'instrumento_id',
                sa.Integer(),
                sa.ForeignKey('instrumentos_pago.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'portador_id',
                sa.Integer(),
                sa.ForeignKey('portador_instrumento.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint('instrumento_id', 'portador_id', name='pk_instrumento_portador'),
        )
        op.create_index('idx_inst_portador_instrumento', 'instrumento_portador', ['instrumento_id'])
        op.create_index('idx_inst_portador_portador', 'instrumento_portador', ['portador_id'])


def downgrade():
    if table_exists('instrumento_portador'):
        op.drop_index('idx_inst_portador_portador', table_name='instrumento_portador')
        op.drop_index('idx_inst_portador_instrumento', table_name='instrumento_portador')
        op.drop_table('instrumento_portador')
