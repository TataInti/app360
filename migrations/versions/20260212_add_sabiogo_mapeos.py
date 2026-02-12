"""Add SabioGo mapping tables

Revision ID: 20260212_add_sabiogo_mapeos
Revises: 20260210_merge_heads
Create Date: 2026-02-12 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260212_add_sabiogo_mapeos"
down_revision = "20260210_merge_heads"
branch_labels = None
depends_on = None


def table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    # Tabla de mapeo de productos
    if not table_exists("sabiogo_product_map"):
        op.create_table(
            "sabiogo_product_map",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("codigo", sa.String(length=50), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("marca", sa.String(length=100), nullable=True),
            sa.Column("modelo", sa.String(length=100), nullable=True),
            sa.Column("producto_descripcion", sa.String(length=200), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_sabiogo_product_map_product_id"),
            sa.UniqueConstraint("codigo", name="uq_sabiogo_product_map_codigo"),
        )
        op.create_index("ix_sabiogo_product_map_codigo", "sabiogo_product_map", ["codigo"])
        op.create_index("ix_sabiogo_product_map_product_id", "sabiogo_product_map", ["product_id"])
        op.create_index("ix_sabiogo_product_map_activo", "sabiogo_product_map", ["activo"])
        op.create_index("idx_sabiogo_product_active", "sabiogo_product_map", ["activo", "product_id"])
    
    # Tabla de mapeo de clientes
    if not table_exists("sabiogo_client_map"):
        op.create_table(
            "sabiogo_client_map",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cliente", sa.String(length=200), nullable=False),
            sa.Column("condicion_iva", sa.String(length=50), nullable=True),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("zona", sa.String(length=100), nullable=True),
            sa.Column("localidad", sa.String(length=100), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name="fk_sabiogo_client_map_client_id"),
        )
        op.create_index("ix_sabiogo_client_map_cliente", "sabiogo_client_map", ["cliente"])
        op.create_index("ix_sabiogo_client_map_client_id", "sabiogo_client_map", ["client_id"])
        op.create_index("ix_sabiogo_client_map_activo", "sabiogo_client_map", ["activo"])
        op.create_index("idx_sabiogo_client_composite", "sabiogo_client_map", ["cliente", "condicion_iva"])
        op.create_index("idx_sabiogo_client_active", "sabiogo_client_map", ["activo", "client_id"])
    
    # Tabla de mapeo de ubicaciones
    if not table_exists("sabiogo_location_map"):
        op.create_table(
            "sabiogo_location_map",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sucursal", sa.String(length=100), nullable=False),
            sa.Column("deposito", sa.String(length=100), nullable=True),
            sa.Column("uninegocio", sa.String(length=100), nullable=True),
            sa.Column("location_id", sa.Integer(), nullable=True),
            sa.Column("canal", sa.String(length=50), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name="fk_sabiogo_location_map_location_id"),
            sa.UniqueConstraint("sucursal", "deposito", name="uq_sabiogo_location"),
        )
        op.create_index("ix_sabiogo_location_map_location_id", "sabiogo_location_map", ["location_id"])
        op.create_index("ix_sabiogo_location_map_activo", "sabiogo_location_map", ["activo"])
        op.create_index("idx_sabiogo_location_active", "sabiogo_location_map", ["activo", "location_id"])
    
    # Tabla de logs de carga
    if not table_exists("logs_sabiogo_carga"):
        op.create_table(
            "logs_sabiogo_carga",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fecha_carga", sa.DateTime(), nullable=False),
            sa.Column("archivo_nombre", sa.String(length=255), nullable=False),
            sa.Column("tipo_carga", sa.String(length=20), nullable=False),
            sa.Column("hash_archivo", sa.String(length=64), nullable=True),
            sa.Column("filas_insertadas", sa.Integer(), server_default="0"),
            sa.Column("filas_duplicadas", sa.Integer(), server_default="0"),
            sa.Column("filas_sin_mapeo", sa.Integer(), server_default="0"),
            sa.Column("filas_error", sa.Integer(), server_default="0"),
            sa.Column("usuario_id", sa.Integer(), nullable=True),
            sa.Column("observaciones", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["usuario_id"], ["users.id"], name="fk_logs_sabiogo_carga_usuario_id"),
        )
        op.create_index("ix_logs_sabiogo_carga_fecha_carga", "logs_sabiogo_carga", ["fecha_carga"])
        op.create_index("idx_sabiogo_log_tipo_fecha", "logs_sabiogo_carga", ["tipo_carga", "fecha_carga"])


def downgrade():
    # Drop logs table
    if table_exists("logs_sabiogo_carga"):
        op.drop_index("idx_sabiogo_log_tipo_fecha", table_name="logs_sabiogo_carga")
        op.drop_index("ix_logs_sabiogo_carga_fecha_carga", table_name="logs_sabiogo_carga")
        op.drop_table("logs_sabiogo_carga")
    
    # Drop location map table
    if table_exists("sabiogo_location_map"):
        op.drop_index("idx_sabiogo_location_active", table_name="sabiogo_location_map")
        op.drop_index("ix_sabiogo_location_map_activo", table_name="sabiogo_location_map")
        op.drop_index("ix_sabiogo_location_map_location_id", table_name="sabiogo_location_map")
        op.drop_table("sabiogo_location_map")
    
    # Drop client map table
    if table_exists("sabiogo_client_map"):
        op.drop_index("idx_sabiogo_client_active", table_name="sabiogo_client_map")
        op.drop_index("idx_sabiogo_client_composite", table_name="sabiogo_client_map")
        op.drop_index("ix_sabiogo_client_map_activo", table_name="sabiogo_client_map")
        op.drop_index("ix_sabiogo_client_map_client_id", table_name="sabiogo_client_map")
        op.drop_index("ix_sabiogo_client_map_cliente", table_name="sabiogo_client_map")
        op.drop_table("sabiogo_client_map")
    
    # Drop product map table
    if table_exists("sabiogo_product_map"):
        op.drop_index("idx_sabiogo_product_active", table_name="sabiogo_product_map")
        op.drop_index("ix_sabiogo_product_map_activo", table_name="sabiogo_product_map")
        op.drop_index("ix_sabiogo_product_map_product_id", table_name="sabiogo_product_map")
        op.drop_index("ix_sabiogo_product_map_codigo", table_name="sabiogo_product_map")
        op.drop_table("sabiogo_product_map")
