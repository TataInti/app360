"""merge_sabiogo_staging_and_facts

Revision ID: 53a8d4de6d8f
Revises: 20260212_add_sabiogo_facts, 2671935051de
Create Date: 2026-02-12 12:37:55.203387

"""
from alembic import op
import sqlalchemy as sa


revision = '53a8d4de6d8f'
down_revision = ('20260212_add_sabiogo_facts', '2671935051de')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass