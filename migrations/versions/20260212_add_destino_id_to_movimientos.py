"""Add destino_id to movimientos_caja

Revision ID: 20260212_add_destino_id_to_movimientos
Revises: 20260212_add_sabiogo_facts
Create Date: 2026-02-12 17:50:00.000000

Agrega la columna destino_id a movimientos_caja como simple integer sin FK
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260212_add_destino_id_to_movimientos'
down_revision = '20260212_add_sabiogo_facts'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add destino_id column to movimientos_caja"""
    if not column_exists('movimientos_caja', 'destino_id'):
        op.add_column('movimientos_caja', sa.Column('destino_id', sa.Integer(), nullable=True))


def downgrade():
    """Remove destino_id column from movimientos_caja"""
    if column_exists('movimientos_caja', 'destino_id'):
        op.drop_column('movimientos_caja', 'destino_id')
