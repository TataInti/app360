"""fichadas_reloj: empleado_id nullable + nombre_reloj + nueva UC por clock_id

Revision ID: 20260401_fichadas_nullable
Revises: 20260401_fichadas_reloj
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '20260401_fichadas_nullable'
down_revision = '20260401_fichadas_reloj'
branch_labels = None
depends_on = None


def _constraint_exists(name):
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.table_constraints "
            "  WHERE constraint_name = :n AND table_name = 'fichadas_reloj'"
            ")"
        ),
        {"n": name},
    )
    return result.scalar()


def _column_exists(table, column):
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns "
            "  WHERE table_name = :t AND column_name = :c"
            ")"
        ),
        {"t": table, "c": column},
    )
    return result.scalar()


def _index_exists(name):
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM pg_indexes WHERE indexname = :n"
            ")"
        ),
        {"n": name},
    )
    return result.scalar()


def upgrade():
    # 1. empleado_id → nullable
    op.alter_column('fichadas_reloj', 'empleado_id',
                    existing_type=sa.Integer(),
                    nullable=True)

    # 2. Agregar columna nombre_reloj
    if not _column_exists('fichadas_reloj', 'nombre_reloj'):
        op.add_column('fichadas_reloj',
                      sa.Column('nombre_reloj', sa.String(150), nullable=True))

    # 3. Reemplazar UniqueConstraint: (empleado_id, fecha_hora) → (clock_id_original, fecha_hora)
    if _constraint_exists('uq_fichada_empleado_fechahora'):
        op.drop_constraint('uq_fichada_empleado_fechahora', 'fichadas_reloj', type_='unique')

    if not _constraint_exists('uq_fichada_clock_fechahora'):
        op.create_unique_constraint('uq_fichada_clock_fechahora', 'fichadas_reloj',
                                    ['clock_id_original', 'fecha_hora'])

    # 4. Índice sobre clock_id_original para búsquedas de asociación
    if not _index_exists('ix_fichadas_clock_id'):
        op.create_index('ix_fichadas_clock_id', 'fichadas_reloj', ['clock_id_original'])


def downgrade():
    # Revertir: quitar nombre_reloj, restaurar NOT NULL y constraint original
    if _index_exists('ix_fichadas_clock_id'):
        op.drop_index('ix_fichadas_clock_id', 'fichadas_reloj')

    if _constraint_exists('uq_fichada_clock_fechahora'):
        op.drop_constraint('uq_fichada_clock_fechahora', 'fichadas_reloj', type_='unique')

    # Eliminar fichadas sin empleado antes de restaurar NOT NULL
    op.execute("DELETE FROM fichadas_reloj WHERE empleado_id IS NULL")

    if not _constraint_exists('uq_fichada_empleado_fechahora'):
        op.create_unique_constraint('uq_fichada_empleado_fechahora', 'fichadas_reloj',
                                    ['empleado_id', 'fecha_hora'])

    op.alter_column('fichadas_reloj', 'empleado_id',
                    existing_type=sa.Integer(),
                    nullable=False)

    if _column_exists('fichadas_reloj', 'nombre_reloj'):
        op.drop_column('fichadas_reloj', 'nombre_reloj')
