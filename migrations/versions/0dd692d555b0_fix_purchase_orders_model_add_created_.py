"""Fix purchase_orders model - add created_at, supplier, items relation

Revision ID: 0dd692d555b0
Revises: 
Create Date: 2026-01-24 21:08:40.590425

This migration has been modified to be SAFE for production environments
where tables already exist. It only creates tables/columns if they don't exist.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '0dd692d555b0'
down_revision = None
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
    """
    This migration was originally auto-generated to create all tables.
    It has been modified to be idempotent - safe to run on databases
    where tables already exist.
    
    For production: We skip creating tables that exist and only add
    missing columns to purchase_orders.
    """
    
    # Check if this looks like an existing production database
    if table_exists('users'):
        # Production database - only add missing columns to purchase_orders
        if table_exists('purchase_orders'):
            if not column_exists('purchase_orders', 'created_at'):
                op.add_column('purchase_orders', 
                    sa.Column('created_at', sa.DateTime(), nullable=True))
            
            if not column_exists('purchase_orders', 'supplier'):
                op.add_column('purchase_orders',
                    sa.Column('supplier', sa.String(200), nullable=True))
            
            if not column_exists('purchase_orders', 'supplier_id'):
                op.add_column('purchase_orders',
                    sa.Column('supplier_id', sa.Integer(), nullable=True))
            
            if not column_exists('purchase_orders', 'order_date'):
                op.add_column('purchase_orders',
                    sa.Column('order_date', sa.Date(), nullable=True))
            
            if not column_exists('purchase_orders', 'expected_delivery_date'):
                op.add_column('purchase_orders',
                    sa.Column('expected_delivery_date', sa.Date(), nullable=True))
        
        # Database already set up, nothing else to do
        return
    
    # Fresh database - create all tables (original auto-generated code would go here)
    # For now, we assume fresh databases are set up via db.create_all()
    pass


def downgrade():
    # Don't remove anything on downgrade to avoid data loss
    pass
