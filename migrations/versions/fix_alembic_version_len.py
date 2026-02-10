"""Expand alembic version length

Revision ID: fix_alembic_version_len
Revises: 0dd692d555b0
Create Date: 2026-02-10 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "fix_alembic_version_len"
down_revision = "0dd692d555b0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    elif bind.dialect.name == "mysql":
        op.execute("ALTER TABLE alembic_version MODIFY version_num VARCHAR(64)")
    else:
        # SQLite and others do not enforce length on VARCHAR
        pass


def downgrade():
    # Avoid shrinking to prevent truncation of existing values
    pass
