"""Add CuentaCorrienteFriar, PagoFriar, and LogCuentaCorrienteFriar

Revision ID: add_cta_cte_friar
Revises: add_destinos_arqueo_and_logs
Create Date: 2026-02-04 12:00:00.000000

This migration adds:
- New table: cuenta_corriente_friar (Friar account with initial balance)
- New table: pagos_friar (payments to Friar with instrument and amount)
- New table: logs_cuenta_corriente_friar (audit log for balance changes)
- Creates initial Friar account if Friar provider exists
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect
from decimal import Decimal


revision = 'add_cta_cte_friar'
down_revision = 'add_destinos_arqueo_and_logs'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    # 1. Crear tabla cuenta_corriente_friar
    if not table_exists('cuenta_corriente_friar'):
        op.create_table(
            'cuenta_corriente_friar',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('proveedor_id', sa.Integer(), sa.ForeignKey('proveedor.id', ondelete='CASCADE'), nullable=False),
            sa.Column('saldo_inicial', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
            sa.Column('observaciones', sa.Text(), nullable=True),
            sa.Column('editado_por_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('fecha_edicion', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())
        )
        
        # Crear índice en proveedor_id
        op.create_index('idx_cuenta_corriente_friar_proveedor', 'cuenta_corriente_friar', ['proveedor_id'])
    
    # 2. Crear tabla pagos_friar
    if not table_exists('pagos_friar'):
        op.create_table(
            'pagos_friar',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('cuenta_corriente_id', sa.Integer(), sa.ForeignKey('cuenta_corriente_friar.id', ondelete='CASCADE'), nullable=False),
            sa.Column('fecha', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('monto', sa.Numeric(12, 2), nullable=False),
            sa.Column('instrumento_id', sa.Integer(), sa.ForeignKey('instrumentos_pago.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('descripcion', sa.String(500), nullable=False),
            sa.Column('referencia', sa.String(100), nullable=True),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
        )
        
        # Crear índices
        op.create_index('idx_pago_friar_fecha', 'pagos_friar', ['fecha'])
        op.create_index('idx_pago_friar_cuenta', 'pagos_friar', ['cuenta_corriente_id'])
    
    # 3. Crear tabla logs_cuenta_corriente_friar
    if not table_exists('logs_cuenta_corriente_friar'):
        op.create_table(
            'logs_cuenta_corriente_friar',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('cuenta_corriente_id', sa.Integer(), sa.ForeignKey('cuenta_corriente_friar.id', ondelete='CASCADE'), nullable=False),
            sa.Column('fecha_edicion', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('campos_anteriores', postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.Column('campos_nuevos', postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.Column('justificacion', sa.Text(), nullable=False)
        )
        
        # Crear índice en cuenta_corriente_id
        op.create_index('idx_log_cuenta_friar_cuenta', 'logs_cuenta_corriente_friar', ['cuenta_corriente_id'])
    
    # 4. Crear cuenta inicial si existe proveedor "Friar"
    bind = op.get_bind()
    
    # Verificar si existe el proveedor "Friar" (case insensitive)
    result = bind.execute(sa.text("""
        SELECT id FROM proveedor 
        WHERE LOWER(nombre) LIKE '%friar%' 
        LIMIT 1
    """))
    
    proveedor_row = result.fetchone()
    
    if proveedor_row:
        proveedor_id = proveedor_row[0]
        
        # Verificar que no exista ya una cuenta
        result = bind.execute(sa.text("""
            SELECT COUNT(*) FROM cuenta_corriente_friar
        """))
        
        count = result.scalar()
        
        if count == 0:
            # Crear cuenta inicial con saldo 0
            bind.execute(sa.text("""
                INSERT INTO cuenta_corriente_friar (proveedor_id, saldo_inicial, observaciones, created_at, updated_at)
                VALUES (:proveedor_id, 0.00, 'Cuenta creada automáticamente por migración', NOW(), NOW())
            """), {"proveedor_id": proveedor_id})
            
            print(f"✓ Cuenta corriente Friar creada para proveedor ID {proveedor_id}")
        else:
            print("✓ Ya existe una cuenta corriente Friar")
    else:
        print("⚠ No se encontró proveedor Friar. Deberá crear la cuenta manualmente.")


def downgrade():
    # Eliminar tablas en orden inverso (por dependencias FK)
    if table_exists('logs_cuenta_corriente_friar'):
        op.drop_index('idx_log_cuenta_friar_cuenta', table_name='logs_cuenta_corriente_friar')
        op.drop_table('logs_cuenta_corriente_friar')
    
    if table_exists('pagos_friar'):
        op.drop_index('idx_pago_friar_cuenta', table_name='pagos_friar')
        op.drop_index('idx_pago_friar_fecha', table_name='pagos_friar')
        op.drop_table('pagos_friar')
    
    if table_exists('cuenta_corriente_friar'):
        op.drop_index('idx_cuenta_corriente_friar_proveedor', table_name='cuenta_corriente_friar')
        op.drop_table('cuenta_corriente_friar')
