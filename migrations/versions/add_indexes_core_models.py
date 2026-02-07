"""Add indexes for core API tables

Revision ID: add_indexes_core_models
Revises: update_adelantos_liquidaciones
Create Date: 2026-02-06 00:00:00.000000

This migration adds indexes for common lookup and join fields used by the API.
It is safe to run on existing databases: indexes are created only if missing.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'add_indexes_core_models'
down_revision = 'update_adelantos_liquidaciones'
branch_labels = None
depends_on = None


def table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name, index_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def columns_exist(table_name, columns):
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    existing = {col['name'] for col in inspector.get_columns(table_name)}
    return all(col in existing for col in columns)


def create_index_if_missing(table_name, index_name, columns):
    if not table_exists(table_name):
        return
    if not columns_exist(table_name, columns):
        return
    if index_exists(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns)


def upgrade():
    # products
    create_index_if_missing('products', 'idx_products_category', ['category'])
    create_index_if_missing('products', 'idx_products_business_unit_id', ['business_unit_id'])
    create_index_if_missing('products', 'idx_products_location_id', ['location_id'])
    create_index_if_missing('products', 'idx_products_created_at', ['created_at'])

    # locations
    create_index_if_missing('locations', 'idx_locations_name', ['name'])
    create_index_if_missing('locations', 'idx_locations_city', ['city'])
    create_index_if_missing('locations', 'idx_locations_state', ['state'])
    create_index_if_missing('locations', 'idx_locations_is_active', ['is_active'])
    create_index_if_missing('locations', 'idx_locations_type', ['type'])

    # stock_levels
    create_index_if_missing('stock_levels', 'idx_stock_levels_product_id', ['product_id'])
    create_index_if_missing('stock_levels', 'idx_stock_levels_location_id', ['location_id'])
    create_index_if_missing('stock_levels', 'idx_stock_levels_expiry_date', ['expiry_date'])

    # leads
    create_index_if_missing('leads', 'idx_leads_created_at', ['created_at'])
    create_index_if_missing('leads', 'idx_leads_source', ['source'])
    create_index_if_missing('leads', 'idx_leads_status', ['status'])
    create_index_if_missing('leads', 'idx_leads_business_unit_id', ['business_unit_id'])
    create_index_if_missing('leads', 'idx_leads_product_id', ['product_id'])
    create_index_if_missing('leads', 'idx_leads_location_id', ['location_id'])
    create_index_if_missing('leads', 'idx_leads_campaign_id', ['campaign_id'])

    # purchase_orders
    create_index_if_missing('purchase_orders', 'idx_purchase_orders_status', ['status'])
    create_index_if_missing('purchase_orders', 'idx_purchase_orders_location_id', ['location_id'])
    create_index_if_missing('purchase_orders', 'idx_purchase_orders_created_at', ['created_at'])
    create_index_if_missing('purchase_orders', 'idx_purchase_orders_order_date', ['order_date'])
    create_index_if_missing('purchase_orders', 'idx_purchase_orders_expected_delivery_date', ['expected_delivery_date'])

    # purchase_order_items
    create_index_if_missing('purchase_order_items', 'idx_purchase_order_items_order_id', ['order_id'])
    create_index_if_missing('purchase_order_items', 'idx_purchase_order_items_product_id', ['product_id'])

    # purchase_receipts
    create_index_if_missing('purchase_receipts', 'idx_purchase_receipts_order_id', ['order_id'])
    create_index_if_missing('purchase_receipts', 'idx_purchase_receipts_product_id', ['product_id'])
    create_index_if_missing('purchase_receipts', 'idx_purchase_receipts_location_id', ['location_id'])
    create_index_if_missing('purchase_receipts', 'idx_purchase_receipts_received_at', ['received_at'])

    # employees
    create_index_if_missing('employees', 'idx_employees_email', ['email'])
    create_index_if_missing('employees', 'idx_employees_department', ['department'])
    create_index_if_missing('employees', 'idx_employees_location_id', ['location_id'])
    create_index_if_missing('employees', 'idx_employees_is_active', ['is_active'])

    # rrhh_attendance
    create_index_if_missing('rrhh_attendance', 'idx_rrhh_attendance_employee_id', ['employee_id'])
    create_index_if_missing('rrhh_attendance', 'idx_rrhh_attendance_date', ['date'])

    # goals
    create_index_if_missing('goals', 'idx_goals_employee_id', ['employee_id'])
    create_index_if_missing('goals', 'idx_goals_period', ['period'])
    create_index_if_missing('goals', 'idx_goals_status', ['status'])

    # surveys
    create_index_if_missing('surveys', 'idx_surveys_location_id', ['location_id'])

    # survey_responses
    create_index_if_missing('survey_responses', 'idx_survey_responses_survey_id', ['survey_id'])
    create_index_if_missing('survey_responses', 'idx_survey_responses_employee_id', ['employee_id'])
    create_index_if_missing('survey_responses', 'idx_survey_responses_submitted_at', ['submitted_at'])


def downgrade():
    # No-op to avoid accidental data loss or long-running drops in production.
    pass
