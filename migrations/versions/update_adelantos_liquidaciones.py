"""Update adelantos y crear liquidaciones

Revision ID: update_adelantos_liquidaciones
Revises: add_cta_cte_friar
Create Date: 2026-02-04 18:00:00.000000

This migration:
- Expands adelantos table to support tipos (efectivo, mercaderia, prestamo)
- Adds new fields for loans (cuotas, interés)
- Creates liquidaciones_sueldo table
- Renames motivo column to concepto
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'update_adelantos_liquidaciones'
down_revision = 'add_cta_cte_friar'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Agregar nuevas columnas a adelantos
    op.add_column('adelantos', sa.Column('tipo', sa.String(30), nullable=True, server_default='adelanto_efectivo'))
    op.add_column('adelantos', sa.Column('concepto', sa.Text(), nullable=True))
    op.add_column('adelantos', sa.Column('mes_aplicacion', sa.String(7), nullable=True))
    op.add_column('adelantos', sa.Column('cantidad_cuotas', sa.Integer(), nullable=True))
    op.add_column('adelantos', sa.Column('interes_porcentaje', sa.Numeric(5, 2), nullable=True))
    op.add_column('adelantos', sa.Column('cuotas_pagadas', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('adelantos', sa.Column('liquidado', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('adelantos', sa.Column('fecha_liquidacion', sa.DateTime(), nullable=True))
    
    # 2. Migrar datos existentes: copiar motivo a concepto
    op.execute("UPDATE adelantos SET concepto = motivo WHERE concepto IS NULL")
    
    # 3. Hacer concepto NOT NULL
    op.alter_column('adelantos', 'concepto', nullable=False)
    
    # 4. Eliminar columna motivo
    op.drop_column('adelantos', 'motivo')
    
    # 5. Hacer tipo NOT NULL
    op.alter_column('adelantos', 'tipo', nullable=False)
    
    # 6. Crear tabla de liquidaciones
    op.create_table(
        'liquidaciones_sueldo',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empleado_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('periodo', sa.String(7), nullable=False),  # YYYY-MM
        sa.Column('sueldo_base', sa.Numeric(10, 2), nullable=False),
        sa.Column('descuento_adelanto_efectivo', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('descuento_adelanto_mercaderia', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('descuento_cuota_prestamo', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('otros_descuentos', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('sueldo_neto', sa.Numeric(10, 2), nullable=False),
        sa.Column('fecha_liquidacion', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('liquidado_por_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True)
    )
    
    # Crear índices
    op.create_index('idx_liquidacion_empleado_periodo', 'liquidaciones_sueldo', ['empleado_id', 'periodo'], unique=True)
    op.create_index('idx_liquidacion_periodo', 'liquidaciones_sueldo', ['periodo'])


def downgrade():
    # Eliminar tabla liquidaciones
    op.drop_index('idx_liquidacion_periodo', table_name='liquidaciones_sueldo')
    op.drop_index('idx_liquidacion_empleado_periodo', table_name='liquidaciones_sueldo')
    op.drop_table('liquidaciones_sueldo')
    
    # Restaurar columna motivo
    op.add_column('adelantos', sa.Column('motivo', sa.Text(), nullable=True))
    op.execute("UPDATE adelantos SET motivo = concepto WHERE motivo IS NULL")
    op.alter_column('adelantos', 'motivo', nullable=False)
    
    # Eliminar nuevas columnas de adelantos
    op.drop_column('adelantos', 'fecha_liquidacion')
    op.drop_column('adelantos', 'liquidado')
    op.drop_column('adelantos', 'cuotas_pagadas')
    op.drop_column('adelantos', 'interes_porcentaje')
    op.drop_column('adelantos', 'cantidad_cuotas')
    op.drop_column('adelantos', 'mes_aplicacion')
    op.drop_column('adelantos', 'concepto')
    op.drop_column('adelantos', 'tipo')
