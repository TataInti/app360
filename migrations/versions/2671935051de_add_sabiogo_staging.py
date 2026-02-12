"""add_sabiogo_staging

Revision ID: 2671935051de
Revises: 20260210_merge_heads
Create Date: 2026-02-11 23:32:55.909665

"""
from alembic import op
import sqlalchemy as sa


revision = "2671935051de"
down_revision = "20260210_merge_heads"
branch_labels = None
depends_on = None


SABIogo_COLUMNS = [
    sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
    sa.Column("rubro", sa.Text(), nullable=True),
    sa.Column("fecha", sa.DateTime(), nullable=True),
    sa.Column("subrubro", sa.Text(), nullable=True),
    sa.Column("codigo", sa.Text(), nullable=True),
    sa.Column("modelo", sa.Text(), nullable=True),
    sa.Column("producto", sa.Text(), nullable=True),
    sa.Column("marca", sa.Text(), nullable=True),
    sa.Column("comprobante", sa.Text(), nullable=True),
    sa.Column("nro_comprob", sa.Text(), nullable=True),
    sa.Column("cliente", sa.Text(), nullable=True),
    sa.Column("condicion_iva", sa.Text(), nullable=True),
    sa.Column("vendedor", sa.Text(), nullable=True),
    sa.Column("deposito", sa.Text(), nullable=True),
    sa.Column("uninegocio", sa.Text(), nullable=True),
    sa.Column("forma_pago", sa.Text(), nullable=True),
    sa.Column("kilos", sa.Float(), nullable=True),
    sa.Column("cajas", sa.Float(), nullable=True),
    sa.Column("dtos", sa.Float(), nullable=True),
    sa.Column("neto", sa.Float(), nullable=True),
    sa.Column("localidad", sa.Text(), nullable=True),
    sa.Column("zona", sa.Text(), nullable=True),
    sa.Column("sucursal", sa.Text(), nullable=True),
    sa.Column("iva", sa.Float(), nullable=True),
    sa.Column("moniva", sa.Float(), nullable=True),
    sa.Column("tipo", sa.Text(), nullable=True),
    sa.Column("subtot", sa.Float(), nullable=True),
    sa.Column("numlispre", sa.Integer(), nullable=True),
    sa.Column("lisprec", sa.Text(), nullable=True),
    sa.Column("fuente_archivo", sa.Text(), nullable=True),
    sa.Column("fecha_import", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column("hash_archivo", sa.Text(), nullable=True),
    sa.Column("estado", sa.String(length=50), server_default=sa.text("'cargado'"), nullable=False),
    sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(),
        server_default=sa.func.now(),
        server_onupdate=sa.func.now(),
        nullable=False,
    ),
]


def _create_base(table_name: str):
    op.create_table(table_name, *SABIogo_COLUMNS)
    op.create_index(f"ix_{table_name}_fecha", table_name, ["fecha"])
    op.create_index(f"ix_{table_name}_codigo", table_name, ["codigo"])
    op.create_index(f"ix_{table_name}_vendedor", table_name, ["vendedor"])
    op.create_index(f"ix_{table_name}_sucursal", table_name, ["sucursal"])
    op.create_unique_constraint(
        f"uq_{table_name}_nro_tipo_fecha",
        table_name,
        ["nro_comprob", "tipo", "fecha"],
        deferrable=False,
        initially=None,
    )


def upgrade():
    _create_base("stg_sabiogo_ventas")
    _create_base("stg_sabiogo_compras")


def downgrade():
    for name in ["stg_sabiogo_compras", "stg_sabiogo_ventas"]:
        op.drop_constraint(f"uq_{name}_nro_tipo_fecha", name, type_="unique")
        op.drop_index(f"ix_{name}_sucursal", table_name=name)
        op.drop_index(f"ix_{name}_vendedor", table_name=name)
        op.drop_index(f"ix_{name}_codigo", table_name=name)
        op.drop_index(f"ix_{name}_fecha", table_name=name)
        op.drop_table(name)