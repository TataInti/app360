"""Add SabioGo sync execution status

Revision ID: 20260713_sabiogo_sync_runs
Revises: 20260410_instrumento_portador_m2m
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260713_sabiogo_sync_runs'
down_revision = '20260410_instrumento_portador_m2m'
branch_labels = None
depends_on = None


def table_exists(name):
    return name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if table_exists('sabiogo_sync_runs'):
        return

    op.create_table(
        'sabiogo_sync_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.String(length=36), nullable=False),
        sa.Column('fecha_objetivo', sa.Date(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('mensaje', sa.String(length=500), nullable=True),
        sa.Column('filas_ventas', sa.Integer(), nullable=True),
        sa.Column('filas_compras', sa.Integer(), nullable=True),
        sa.Column('iniciada_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finalizada_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actualizada_en', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('execution_id', name='uq_sabiogo_sync_runs_execution_id'),
    )
    op.create_index(
        'idx_sabiogo_sync_run_fecha_estado',
        'sabiogo_sync_runs',
        ['fecha_objetivo', 'estado'],
    )
    op.create_index(
        'ix_sabiogo_sync_runs_estado',
        'sabiogo_sync_runs',
        ['estado'],
    )
    op.create_index(
        'ix_sabiogo_sync_runs_execution_id',
        'sabiogo_sync_runs',
        ['execution_id'],
        unique=True,
    )
    op.create_index(
        'ix_sabiogo_sync_runs_fecha_objetivo',
        'sabiogo_sync_runs',
        ['fecha_objetivo'],
    )


def downgrade():
    if table_exists('sabiogo_sync_runs'):
        op.drop_table('sabiogo_sync_runs')