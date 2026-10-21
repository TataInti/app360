"""Link legacy HR goals to explicitly selected commercial objectives.

Revision ID: 20261020_objetivo_vinculos
Revises: 20261020_comercial_objetivos
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_objetivo_vinculos"
down_revision = "20261020_comercial_objetivos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "comercial_objetivo_vinculos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("comercial_objetivo_id", sa.Integer(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name="fk_comercial_objetivo_vinculos_goal_id_goals",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["comercial_objetivo_id"],
            ["comercial_objetivos.id"],
            name="fk_comercial_objetivo_vinculos_objetivo_id_objetivos",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "goal_id",
            name="uq_comercial_objetivo_vinculo_goal",
        ),
        sa.UniqueConstraint(
            "comercial_objetivo_id",
            name="uq_comercial_objetivo_vinculo_objetivo",
        ),
    )


def downgrade():
    op.drop_table("comercial_objetivo_vinculos")
