"""Crear tabla turno_dias y agregar clock_id/turno_id a employees.
Eliminar columnas obsoletas hora_inicio, hora_fin, dias_semana de turnos.

Revision ID: 20260327_turno_dias_employee_clock
Revises: 20260317_merge_heads
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa

revision = '20260327_turno_dias_employee_clock'
down_revision = '20260317_merge_heads'
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t)"
    ), {"t": name})
    return result.scalar()


def _column_exists(conn, table, column):
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c)"
    ), {"t": table, "c": column})
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # 1) Crear tabla turno_dias
    if not _table_exists(conn, "turno_dias"):
        op.create_table(
            'turno_dias',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('turno_id', sa.Integer(),
                      sa.ForeignKey('turnos.id'), nullable=False),
            sa.Column('dia_semana', sa.Integer(), nullable=False),
            sa.Column('activo', sa.Boolean(), server_default='true'),
            sa.Column('es_cortado', sa.Boolean(), server_default='false'),
            sa.Column('hora_inicio_1', sa.Time(), nullable=True),
            sa.Column('hora_fin_1', sa.Time(), nullable=True),
            sa.Column('hora_inicio_2', sa.Time(), nullable=True),
            sa.Column('hora_fin_2', sa.Time(), nullable=True),
        )
        op.create_unique_constraint(
            'uq_turno_dia', 'turno_dias', ['turno_id', 'dia_semana']
        )

    # 2) Agregar clock_id a employees
    if not _column_exists(conn, 'employees', 'clock_id'):
        op.add_column('employees',
                       sa.Column('clock_id', sa.String(50), nullable=True))
        op.create_unique_constraint('uq_employee_clock_id', 'employees', ['clock_id'])
        op.create_index('ix_employees_clock_id', 'employees', ['clock_id'])

    # 3) Agregar turno_id a employees
    if not _column_exists(conn, 'employees', 'turno_id'):
        op.add_column('employees',
                       sa.Column('turno_id', sa.Integer(),
                                 sa.ForeignKey('turnos.id'), nullable=True))

    # 4) Eliminar columnas obsoletas de turnos
    for col in ('hora_inicio', 'hora_fin', 'dias_semana'):
        if _column_exists(conn, 'turnos', col):
            op.drop_column('turnos', col)


def downgrade():
    conn = op.get_bind()

    # Restaurar columnas de turnos
    if not _column_exists(conn, 'turnos', 'hora_inicio'):
        op.add_column('turnos',
                       sa.Column('hora_inicio', sa.Time(), nullable=True))
    if not _column_exists(conn, 'turnos', 'hora_fin'):
        op.add_column('turnos',
                       sa.Column('hora_fin', sa.Time(), nullable=True))
    if not _column_exists(conn, 'turnos', 'dias_semana'):
        op.add_column('turnos',
                       sa.Column('dias_semana', sa.String(20), nullable=True))

    # Quitar turno_id de employees
    if _column_exists(conn, 'employees', 'turno_id'):
        op.drop_column('employees', 'turno_id')

    # Quitar clock_id de employees
    if _column_exists(conn, 'employees', 'clock_id'):
        op.drop_index('ix_employees_clock_id', 'employees')
        op.drop_constraint('uq_employee_clock_id', 'employees')
        op.drop_column('employees', 'clock_id')

    # Eliminar tabla turno_dias
    if _table_exists(conn, 'turno_dias'):
        op.drop_table('turno_dias')
