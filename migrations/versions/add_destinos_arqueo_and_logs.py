"""Add DestinoArqueo, LogArqueo, and new payment instruments

Revision ID: add_destinos_arqueo_and_logs
Revises: 0dd692d555b0
Create Date: 2026-02-04 10:00:00.000000

This migration adds:
- New table: destinos_arqueo (destinations for cash closures)
- New table: logs_arqueo (audit log for cash closure edits)
- New columns to arqueos_caja: destino_id, editado_por_id, fecha_edicion, created_at, updated_at
- Seeds for 8 initial destinations
- Seeds for 16 new payment instruments
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'add_destinos_arqueo_and_logs'
down_revision = '0dd692d555b0'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # 1. Crear tabla destinos_arqueo
    if not table_exists('destinos_arqueo'):
        op.create_table(
            'destinos_arqueo',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('nombre', sa.String(100), nullable=False, unique=True),
            sa.Column('descripcion', sa.String(200), nullable=True),
            sa.Column('activo', sa.Boolean(), default=True, server_default='1'),
        )
    
    # 2. Crear tabla logs_arqueo
    if not table_exists('logs_arqueo'):
        op.create_table(
            'logs_arqueo',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('arqueo_id', sa.Integer(), nullable=False),
            sa.Column('fecha_edicion', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('campos_anteriores', sa.JSON(), nullable=False),
            sa.Column('campos_nuevos', sa.JSON(), nullable=False),
            sa.Column('justificacion', sa.Text(), nullable=False),
        )
        
        # Foreign keys para logs_arqueo
        if table_exists('arqueos_caja'):
            op.create_foreign_key(
                'fk_logs_arqueo_arqueo_id',
                'logs_arqueo', 'arqueos_caja',
                ['arqueo_id'], ['id']
            )
        if table_exists('users'):
            op.create_foreign_key(
                'fk_logs_arqueo_usuario_id',
                'logs_arqueo', 'users',
                ['usuario_id'], ['id']
            )
    
    # 3. Agregar columnas a arqueos_caja
    if table_exists('arqueos_caja'):
        if not column_exists('arqueos_caja', 'destino_id'):
            op.add_column('arqueos_caja',
                sa.Column('destino_id', sa.Integer(), nullable=True))
            # Foreign key
            if table_exists('destinos_arqueo'):
                op.create_foreign_key(
                    'fk_arqueo_destino_id',
                    'arqueos_caja', 'destinos_arqueo',
                    ['destino_id'], ['id']
                )
        
        if not column_exists('arqueos_caja', 'editado_por_id'):
            op.add_column('arqueos_caja',
                sa.Column('editado_por_id', sa.Integer(), nullable=True))
            # Foreign key
            if table_exists('users'):
                op.create_foreign_key(
                    'fk_arqueo_editado_por_id',
                    'arqueos_caja', 'users',
                    ['editado_por_id'], ['id']
                )
        
        if not column_exists('arqueos_caja', 'fecha_edicion'):
            op.add_column('arqueos_caja',
                sa.Column('fecha_edicion', sa.DateTime(), nullable=True))
        
        if not column_exists('arqueos_caja', 'created_at'):
            op.add_column('arqueos_caja',
                sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        
        if not column_exists('arqueos_caja', 'updated_at'):
            op.add_column('arqueos_caja',
                sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()))
    
    # 4. Seed de destinos iniciales
    if table_exists('destinos_arqueo'):
        from sqlalchemy import table, column
        destinos_table = table('destinos_arqueo',
            column('nombre', sa.String),
            column('descripcion', sa.String),
            column('activo', sa.Boolean)
        )
        
        # Verificar si ya hay destinos
        bind = op.get_bind()
        result = bind.execute(sa.text("SELECT COUNT(*) FROM destinos_arqueo")).scalar()
        
        if result == 0:
            op.bulk_insert(destinos_table, [
                {'nombre': 'Banco', 'descripcion': 'Depósito en cuenta bancaria', 'activo': True},
                {'nombre': 'Caja Fuerte', 'descripcion': 'Almacenamiento en caja fuerte de la sucursal', 'activo': True},
                {'nombre': 'Caja General', 'descripcion': 'Efectivo disponible para operaciones del día', 'activo': True},
                {'nombre': 'Tesoro Central', 'descripcion': 'Transferencia a tesorería central', 'activo': True},
                {'nombre': 'Cambio de Turno', 'descripcion': 'Entrega a siguiente turno', 'activo': True},
                {'nombre': 'Transporte de Valores', 'descripcion': 'Recogido por empresa de transporte', 'activo': True},
                {'nombre': 'Caja Chica', 'descripcion': 'Fondo para gastos menores', 'activo': True},
                {'nombre': 'Otro', 'descripcion': 'Otro destino (especificar en observaciones)', 'activo': True},
            ])
    
    # 5. Seed de nuevos instrumentos de pago
    if table_exists('instrumentos_pago'):
        from sqlalchemy import table, column
        instrumentos_table = table('instrumentos_pago',
            column('nombre', sa.String),
            column('descripcion', sa.String),
            column('activo', sa.Boolean)
        )
        
        # Lista de instrumentos a crear
        nuevos_instrumentos = [
            {'nombre': 'Flor', 'descripcion': 'Cuenta Flor', 'activo': True},
            {'nombre': 'Lacteos', 'descripcion': 'Cuenta Lacteos', 'activo': True},
            {'nombre': 'Friar', 'descripcion': 'Cuenta Friar', 'activo': True},
            {'nombre': 'Financiera', 'descripcion': 'Cuenta Financiera', 'activo': True},
            {'nombre': 'Banco Galicia', 'descripcion': 'Cuenta Banco Galicia', 'activo': True},
            {'nombre': 'Banco Macro', 'descripcion': 'Cuenta Banco Macro', 'activo': True},
            {'nombre': 'Tarjetas cupones', 'descripcion': 'Cupones de tarjetas', 'activo': True},
            {'nombre': 'Efectivo Friar', 'descripcion': 'Efectivo de Friar', 'activo': True},
            {'nombre': 'Efectivo Lacteos', 'descripcion': 'Efectivo de Lacteos', 'activo': True},
            {'nombre': 'Cheques propios', 'descripcion': 'Cheques emitidos por la empresa', 'activo': True},
            {'nombre': 'Cheques clientes', 'descripcion': 'Cheques recibidos de clientes', 'activo': True},
            {'nombre': 'Cheques financiera', 'descripcion': 'Cheques de financiera', 'activo': True},
            {'nombre': 'Echeq', 'descripcion': 'Cheques electrónicos', 'activo': True},
            {'nombre': 'Diferencia Presup/Vta', 'descripcion': 'Diferencia entre presupuesto y venta', 'activo': True},
            {'nombre': 'Intereses', 'descripcion': 'Intereses cobrados o pagados', 'activo': True},
            {'nombre': 'Comisiones', 'descripcion': 'Comisiones cobradas o pagadas', 'activo': True},
        ]
        
        # Insertar solo los que no existen
        bind = op.get_bind()
        for instrumento in nuevos_instrumentos:
            result = bind.execute(
                sa.text("SELECT COUNT(*) FROM instrumentos_pago WHERE nombre = :nombre"),
                {'nombre': instrumento['nombre']}
            ).scalar()
            
            if result == 0:
                op.bulk_insert(instrumentos_table, [instrumento])


def downgrade():
    # Eliminar columnas de arqueos_caja
    if table_exists('arqueos_caja'):
        if column_exists('arqueos_caja', 'updated_at'):
            op.drop_column('arqueos_caja', 'updated_at')
        if column_exists('arqueos_caja', 'created_at'):
            op.drop_column('arqueos_caja', 'created_at')
        if column_exists('arqueos_caja', 'fecha_edicion'):
            op.drop_column('arqueos_caja', 'fecha_edicion')
        
        # Eliminar foreign keys primero
        try:
            op.drop_constraint('fk_arqueo_editado_por_id', 'arqueos_caja', type_='foreignkey')
        except:
            pass
        if column_exists('arqueos_caja', 'editado_por_id'):
            op.drop_column('arqueos_caja', 'editado_por_id')
        
        try:
            op.drop_constraint('fk_arqueo_destino_id', 'arqueos_caja', type_='foreignkey')
        except:
            pass
        if column_exists('arqueos_caja', 'destino_id'):
            op.drop_column('arqueos_caja', 'destino_id')
    
    # Eliminar foreign keys de logs_arqueo
    if table_exists('logs_arqueo'):
        try:
            op.drop_constraint('fk_logs_arqueo_usuario_id', 'logs_arqueo', type_='foreignkey')
        except:
            pass
        try:
            op.drop_constraint('fk_logs_arqueo_arqueo_id', 'logs_arqueo', type_='foreignkey')
        except:
            pass
        op.drop_table('logs_arqueo')
    
    # Eliminar tabla destinos_arqueo
    if table_exists('destinos_arqueo'):
        op.drop_table('destinos_arqueo')
