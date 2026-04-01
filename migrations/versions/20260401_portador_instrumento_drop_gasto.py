"""Add portador_instrumento table, requiere_portador to instrumentos_pago,
portador_id to movimientos_caja, drop gasto table.

Revision ID: 20260401_portador_drop_gasto
Revises: 20260327_turno_dias_employee_clock
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '20260401_portador_drop_gasto'
down_revision = '20260327_turno_dias_employee_clock'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create portador_instrumento table
    op.create_table(
        'portador_instrumento',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombre', sa.String(200), nullable=False),
        sa.Column('documento', sa.String(30), nullable=True),
        sa.Column('telefono', sa.String(50), nullable=True),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('activo', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # 2. Add requiere_portador to instrumentos_pago
    with op.batch_alter_table('instrumentos_pago') as batch_op:
        batch_op.add_column(
            sa.Column('requiere_portador', sa.Boolean(), server_default='0', nullable=False)
        )

    # 3. Add portador_id FK to movimientos_caja
    with op.batch_alter_table('movimientos_caja') as batch_op:
        batch_op.add_column(
            sa.Column('portador_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_movimiento_portador', 'portador_instrumento',
            ['portador_id'], ['id']
        )

    # 4. Drop gasto table (confirmed empty)
    op.drop_table('gasto')


def downgrade():
    # Recreate gasto table
    op.create_table(
        'gasto',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('descripcion', sa.String(300), nullable=False),
        sa.Column('monto', sa.Numeric(12, 2), nullable=False),
        sa.Column('categoria_id', sa.Integer(), sa.ForeignKey('categoria_gasto.id'), nullable=False),
        sa.Column('proveedor_id', sa.Integer(), sa.ForeignKey('proveedor.id'), nullable=False),
        sa.Column('numero_factura', sa.String(50), nullable=True),
        sa.Column('fecha_vencimiento', sa.Date(), nullable=True),
        sa.Column('pagado', sa.Boolean(), server_default='0'),
        sa.Column('fecha_pago', sa.DateTime(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    with op.batch_alter_table('movimientos_caja') as batch_op:
        batch_op.drop_constraint('fk_movimiento_portador', type_='foreignkey')
        batch_op.drop_column('portador_id')

    with op.batch_alter_table('instrumentos_pago') as batch_op:
        batch_op.drop_column('requiere_portador')

    op.drop_table('portador_instrumento')
