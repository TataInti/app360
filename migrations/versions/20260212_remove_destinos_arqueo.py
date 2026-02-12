"""Remove destinos_arqueo table and FK from movimientos

Revision ID: 20260212_remove_destinos_arqueo
Revises: 20260212_add_destino_id_to_movimientos
Create Date: 2026-02-12 18:00:00.000000

Elimina la tabla destinos_arqueo y cualquier FK asociada.
El campo destino_id en movimientos_caja se mantiene como simple integer 
para tracking de destinos sin relación de FK.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260212_remove_destinos_arqueo'
down_revision = '20260212_add_destino_id_to_movimientos'
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


def constraint_exists(table_name, constraint_name):
    """Check if a foreign key constraint exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    
    # Para PostgreSQL y SQLite
    try:
        fks = inspector.get_foreign_keys(table_name)
        return any(fk.get('name') == constraint_name for fk in fks)
    except:
        return False


def upgrade():
    """
    1. Elimina FK de movimientos_caja.destino_id si existe
    2. Elimina FK/columna destino_id en arqueos_caja si existe
    3. Elimina tabla destinos_arqueo si existe
    4. destino_id se mantiene en movimientos_caja como simple Integer para tracking
    """
    
    # 1. Eliminar FK de movimientos_caja.destino_id si existe
    if table_exists('movimientos_caja'):
        # Intentar eliminar la FK (puede tener diferentes nombres según cómo se creó)
        possible_fk_names = [
            'fk_movimiento_destino_id',
            'movimientos_caja_destino_id_fkey',
            'fk_movimientos_caja_destino_id'
        ]
        
        for fk_name in possible_fk_names:
            if constraint_exists('movimientos_caja', fk_name):
                try:
                    op.drop_constraint(fk_name, 'movimientos_caja', type_='foreignkey')
                    print(f"✓ FK {fk_name} eliminada de movimientos_caja")
                except Exception as e:
                    print(f"⚠ No se pudo eliminar FK {fk_name}: {e}")

    # 2. Eliminar FK/columna destino_id de arqueos_caja si existen
    if table_exists('arqueos_caja'):
        possible_fk_names_arqueo = [
            'fk_arqueo_destino_id',
            'arqueos_caja_destino_id_fkey',
            'fk_arqueos_caja_destino_id'
        ]

        for fk_name in possible_fk_names_arqueo:
            if constraint_exists('arqueos_caja', fk_name):
                try:
                    op.drop_constraint(fk_name, 'arqueos_caja', type_='foreignkey')
                    print(f"✓ FK {fk_name} eliminada de arqueos_caja")
                except Exception as e:
                    print(f"⚠ No se pudo eliminar FK {fk_name}: {e}")

        if column_exists('arqueos_caja', 'destino_id'):
            try:
                op.drop_column('arqueos_caja', 'destino_id')
                print("✓ Columna destino_id eliminada de arqueos_caja")
            except Exception as e:
                print(f"⚠ No se pudo eliminar columna arqueos_caja.destino_id: {e}")
    
    # 3. Eliminar tabla destinos_arqueo si existe
    if table_exists('destinos_arqueo'):
        op.drop_table('destinos_arqueo')
        print("✓ Tabla destinos_arqueo eliminada")
    
    # 4. destino_id en movimientos_caja se mantiene como está (simple Integer)
    print("✓ destino_id se mantiene en movimientos_caja como campo de tracking")


def downgrade():
    """
    Revierte los cambios:
    1. Recrea tabla destinos_arqueo
    2. Recrea FK en movimientos_caja (si se había eliminado)
    """
    
    # 1. Recrear tabla destinos_arqueo
    if not table_exists('destinos_arqueo'):
        op.create_table(
            'destinos_arqueo',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('nombre', sa.String(100), nullable=False, unique=True),
            sa.Column('descripcion', sa.String(200), nullable=True),
            sa.Column('activo', sa.Boolean(), default=True, server_default='1'),
        )
    
    # 2. Recrear FK si la columna existe
    if table_exists('movimientos_caja') and column_exists('movimientos_caja', 'destino_id'):
        if table_exists('destinos_arqueo') and not constraint_exists('movimientos_caja', 'fk_movimiento_destino_id'):
            try:
                op.create_foreign_key(
                    'fk_movimiento_destino_id',
                    'movimientos_caja', 'destinos_arqueo',
                    ['destino_id'], ['id']
                )
            except:
                pass  # Puede fallar si hay datos inconsistentes
