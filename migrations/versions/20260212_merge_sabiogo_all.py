"""Merge SabioGo migrations

Revision ID: 20260212_merge_sabiogo_all
Revises: 20260212_add_sabiogo_facts, 2671935051de
Create Date: 2026-02-12 12:37:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260212_merge_sabiogo_all"
down_revision = ("20260212_add_sabiogo_facts", "2671935051de")
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration, no changes needed
    pass


def downgrade():
    # This is a merge migration, no changes needed
    pass
