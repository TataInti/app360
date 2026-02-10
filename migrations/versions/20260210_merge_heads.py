"""Merge Alembic heads

Revision ID: 20260210_merge_heads
Revises: 20260209_add_lead_pipeline_stages, add_ausentismo_fields_asistencia
Create Date: 2026-02-10 00:00:00
"""

revision = "20260210_merge_heads"
down_revision = ("20260209_add_lead_pipeline_stages", "add_ausentismo_fields_asistencia")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
