"""Tablas fichadas_reloj y resumen_asistencia_diaria para control de asistencia

Revision ID: 20260401_fichadas_reloj
Revises: 20260327_turno_dias_employee_clock
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '20260401_fichadas_reloj'
down_revision = '20260401_fix_mov_cols'
branch_labels = None
depends_on = None


def _table_exists(name):
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
        {"t": name},
    )
    return result.scalar()


def upgrade():
    if not _table_exists('fichadas_reloj'):
        op.create_table(
            'fichadas_reloj',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('empleado_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('clock_id_original', sa.String(50), nullable=False),
            sa.Column('fecha', sa.Date(), nullable=False),
            sa.Column('hora', sa.Time(), nullable=False),
            sa.Column('fecha_hora', sa.DateTime(), nullable=False),
            sa.Column('archivo_origen', sa.String(255)),
            sa.Column('lote_importacion', sa.String(40), nullable=False),
            sa.UniqueConstraint('empleado_id', 'fecha_hora', name='uq_fichada_empleado_fechahora'),
        )
        op.create_index('ix_fichada_empleado_fecha', 'fichadas_reloj', ['empleado_id', 'fecha'])
        op.create_index('ix_fichadas_reloj_lote', 'fichadas_reloj', ['lote_importacion'])

    if not _table_exists('resumen_asistencia_diaria'):
        op.create_table(
            'resumen_asistencia_diaria',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('empleado_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('fecha', sa.Date(), nullable=False),
            sa.Column('turno_id', sa.Integer(), sa.ForeignKey('turnos.id'), nullable=True),
            sa.Column('fichadas_count', sa.Integer(), default=0),
            sa.Column('fichadas_esperadas', sa.Integer(), default=2),
            sa.Column('hora_entrada_1', sa.Time()),
            sa.Column('hora_salida_1', sa.Time()),
            sa.Column('hora_entrada_2', sa.Time()),
            sa.Column('hora_salida_2', sa.Time()),
            sa.Column('minutos_tarde_total', sa.Integer(), default=0),
            sa.Column('es_falta', sa.Boolean(), default=False),
            sa.Column('es_tarde', sa.Boolean(), default=False),
            sa.Column('fichada_faltante', sa.Boolean(), default=False),
            sa.Column('justificado', sa.Boolean(), default=False),
            sa.Column('notas', sa.Text()),
            sa.Column('lote_importacion', sa.String(40)),
            sa.UniqueConstraint('empleado_id', 'fecha', name='uq_resumen_empleado_fecha'),
        )
        op.create_index('ix_resumen_empleado_fecha', 'resumen_asistencia_diaria', ['empleado_id', 'fecha'])
        op.create_index('ix_resumen_lote', 'resumen_asistencia_diaria', ['lote_importacion'])


def downgrade():
    op.drop_table('resumen_asistencia_diaria')
    op.drop_table('fichadas_reloj')
