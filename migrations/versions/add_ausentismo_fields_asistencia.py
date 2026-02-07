"""Add ausentismo fields to asistencia

Revision ID: add_ausentismo_fields_asistencia
Revises: add_indexes_core_models
Create Date: 2026-02-07 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'add_ausentismo_fields_asistencia'
down_revision = 'add_indexes_core_models'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not column_exists('asistencia', 'motivo'):
        op.add_column('asistencia', sa.Column('motivo', sa.Text(), nullable=True))
    if not column_exists('asistencia', 'justificado'):
        op.add_column('asistencia', sa.Column('justificado', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    if not column_exists('asistencia', 'minutos_tarde'):
        op.add_column('asistencia', sa.Column('minutos_tarde', sa.Integer(), nullable=True))


def downgrade():
    if column_exists('asistencia', 'minutos_tarde'):
        op.drop_column('asistencia', 'minutos_tarde')
    if column_exists('asistencia', 'justificado'):
        op.drop_column('asistencia', 'justificado')
    if column_exists('asistencia', 'motivo'):
        op.drop_column('asistencia', 'motivo')
