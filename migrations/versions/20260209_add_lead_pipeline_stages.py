"""Add lead pipeline stages and history

Revision ID: 20260209_add_lead_pipeline_stages
Revises: 20260209_add_compras_registro_fields
Create Date: 2026-02-09 00:00:01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260209_add_lead_pipeline_stages"
down_revision = "20260209_add_compras_registro_fields"
branch_labels = None
depends_on = None

DEFAULT_STAGES = [
    {"name": "nuevo", "position": 1, "activo": True},
    {"name": "contactado", "position": 2, "activo": True},
    {"name": "propuesta", "position": 3, "activo": True},
    {"name": "cierre", "position": 4, "activo": True},
]


def table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not table_exists("lead_stages"):
        op.create_table(
            "lead_stages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.UniqueConstraint("name", name="uq_lead_stages_name"),
        )
        op.create_index("ix_lead_stages_name", "lead_stages", ["name"])
        op.create_index("ix_lead_stages_position", "lead_stages", ["position"])
        op.create_index("ix_lead_stages_activo", "lead_stages", ["activo"])

    if not table_exists("lead_stage_history"):
        op.create_table(
            "lead_stage_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("lead_id", sa.Integer(), nullable=False),
            sa.Column("from_stage", sa.String(length=80), nullable=True),
            sa.Column("to_stage", sa.String(length=80), nullable=True),
            sa.Column("comment", sa.String(length=300), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name="fk_lead_stage_history_lead_id"),
        )
        op.create_index("ix_lead_stage_history_lead_id", "lead_stage_history", ["lead_id"])
        op.create_index("ix_lead_stage_history_from_stage", "lead_stage_history", ["from_stage"])
        op.create_index("ix_lead_stage_history_to_stage", "lead_stage_history", ["to_stage"])
        op.create_index("ix_lead_stage_history_created_at", "lead_stage_history", ["created_at"])
        op.create_index("ix_lead_stage_history_created_by", "lead_stage_history", ["created_by"])

    bind = op.get_bind()
    if table_exists("lead_stages"):
        existing = bind.execute(sa.text("SELECT COUNT(1) FROM lead_stages")).scalar()
        if existing == 0:
            lead_stages_table = sa.table(
                "lead_stages",
                sa.column("name", sa.String),
                sa.column("position", sa.Integer),
                sa.column("activo", sa.Boolean),
            )
            op.bulk_insert(lead_stages_table, DEFAULT_STAGES)


def downgrade():
    if table_exists("lead_stage_history"):
        op.drop_index("ix_lead_stage_history_created_by", table_name="lead_stage_history")
        op.drop_index("ix_lead_stage_history_created_at", table_name="lead_stage_history")
        op.drop_index("ix_lead_stage_history_to_stage", table_name="lead_stage_history")
        op.drop_index("ix_lead_stage_history_from_stage", table_name="lead_stage_history")
        op.drop_index("ix_lead_stage_history_lead_id", table_name="lead_stage_history")
        op.drop_table("lead_stage_history")

    if table_exists("lead_stages"):
        op.drop_index("ix_lead_stages_activo", table_name="lead_stages")
        op.drop_index("ix_lead_stages_position", table_name="lead_stages")
        op.drop_index("ix_lead_stages_name", table_name="lead_stages")
        op.drop_table("lead_stages")
