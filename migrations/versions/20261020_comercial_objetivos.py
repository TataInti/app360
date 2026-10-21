"""Create monthly commercial objectives without altering HR goals.

Revision ID: 20261020_comercial_objetivos
Revises: 20261020_comercial_vendedores
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_comercial_objetivos"
down_revision = "20261020_comercial_vendedores"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "comercial_objetivos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendedor_id", sa.Integer(), nullable=False),
        sa.Column("empresa", sa.String(length=10), nullable=False),
        sa.Column("mes", sa.String(length=7), nullable=False),
        sa.Column("medida", sa.String(length=10), nullable=False),
        sa.Column("meta", sa.Numeric(18, 4), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["vendedor_id"],
            ["comercial_vendedores.id"],
            name="fk_comercial_objetivos_vendedor_id_comercial_vendedores",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["creado_por_id"],
            ["users.id"],
            name="fk_comercial_objetivos_creado_por_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["users.id"],
            name="fk_comercial_objetivos_actualizado_por_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "vendedor_id",
            "empresa",
            "mes",
            "medida",
            name="uq_comercial_objetivo_vendedor_empresa_mes_medida",
        ),
        sa.CheckConstraint(
            "empresa IN ('CARNES', 'LACTEOS')",
            name="ck_comercial_objetivo_empresa",
        ),
        sa.CheckConstraint(
            "medida IN ('importe', 'cajas', 'kilos')",
            name="ck_comercial_objetivo_medida",
        ),
        sa.CheckConstraint("meta > 0", name="ck_comercial_objetivo_meta_positiva"),
        sa.CheckConstraint(
            "length(mes) = 7 AND substr(mes, 5, 1) = '-'",
            name="ck_comercial_objetivo_mes_formato",
        ),
    )
    op.create_index(
        "ix_comercial_objetivos_mes_empresa_medida",
        "comercial_objetivos",
        ["mes", "empresa", "medida"],
    )


def downgrade():
    op.drop_index(
        "ix_comercial_objetivos_mes_empresa_medida",
        table_name="comercial_objetivos",
    )
    op.drop_table("comercial_objetivos")
