"""Crear tabla user_module_permissions (control de accesos por usuario)

Revision ID: 20260317_add_user_module_permissions
Revises: 20260305_add_arqueo_detalle
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = '20260317_add_user_module_permissions'
down_revision = '20260305_add_arqueo_detalle'
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t)"
    ), {"t": name})
    return result.scalar()


def upgrade():
    conn = op.get_bind()
    if _table_exists(conn, "user_module_permissions"):
        return

    op.create_table(
        'user_module_permissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('access_level', sa.String(10), nullable=False),
    )
    op.create_unique_constraint(
        'uq_user_module_perm', 'user_module_permissions',
        ['user_id', 'module']
    )
    op.create_index(
        'ix_user_module_permissions_user_id',
        'user_module_permissions', ['user_id']
    )


def downgrade():
    op.drop_index('ix_user_module_permissions_user_id',
                  table_name='user_module_permissions')
    op.drop_constraint('uq_user_module_perm',
                       'user_module_permissions', type_='unique')
    op.drop_table('user_module_permissions')
