"""Índice por cliente y fecha en stg_sabiogo_ventas para el desplegable de Seguimiento de clientes.

Revision ID: 20261125_stg_ventas_cliente_fecha_idx
Revises: 20261125_criterio_clientes_ambos
Create Date: 2026-11-25

Aditiva y reversible. Las lecturas del panel comparan TRIM(cliente) (el panel agrupa por ese
valor), así que el índice es sobre btrim(cliente) + fecha descendente. En PostgreSQL se crea con
CREATE INDEX CONCURRENTLY, fuera de la transacción de Alembic: no bloquea escrituras (la
sincronización puede seguir) y usa lock_timeout para no esperar indefinidamente. Si una corrida
anterior dejó el índice inválido, se descarta y se vuelve a crear. En otros motores no hace nada.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261125_stg_ventas_cliente_fecha_idx"
down_revision = "20261125_criterio_clientes_ambos"
branch_labels = None
depends_on = None

INDICE = "ix_stg_sabiogo_ventas_cliente_trim_fecha"


def _es_postgres():
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    if not _es_postgres():
        return
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        invalido = op.get_bind().execute(sa.text(
            "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :nombre AND NOT i.indisvalid"), {"nombre": INDICE}).first()
        if invalido:
            op.execute("DROP INDEX CONCURRENTLY %s" % INDICE)
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS %s ON stg_sabiogo_ventas ((btrim(cliente)), fecha DESC)"
            % INDICE
        )
        op.execute("RESET lock_timeout")


def downgrade():
    if not _es_postgres():
        return
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS %s" % INDICE)
        op.execute("RESET lock_timeout")
