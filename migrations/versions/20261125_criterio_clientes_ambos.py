"""Permite el criterio AMBOS (PRE y FAC) en comercial_cliente_criterio.

Revision ID: 20261125_criterio_clientes_ambos
Revises: 20261120_usuarios_c4_auditoria_bloqueo
Create Date: 2026-11-25

Aditiva: amplía la columna de 3 a 5 caracteres y reemplaza el CHECK por uno que admite
'AMBOS'. No modifica filas. El downgrade pasa los clientes AMBOS a PRE (el valor por
defecto) antes de restaurar el CHECK y el ancho originales.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261125_criterio_clientes_ambos"
down_revision = "20261120_usuarios_c4_auditoria_bloqueo"
branch_labels = None
depends_on = None

TABLA = "comercial_cliente_criterio"
CHECK = "ck_comercial_cliente_criterio_tipo"


def _existe_tabla():
    return TABLA in inspect(op.get_bind()).get_table_names()


def _cambiar(ancho, valores):
    # batch_alter_table sirve en PostgreSQL (ALTER directo) y en SQLite (recrea la tabla).
    with op.batch_alter_table(TABLA) as lote:
        lote.drop_constraint(CHECK, type_="check")
        lote.alter_column(
            "criterio",
            existing_type=sa.String(),
            type_=sa.String(length=ancho),
            existing_nullable=False,
            existing_server_default="PRE",
        )
        lote.create_check_constraint(CHECK, "criterio IN (%s)" % valores)


def upgrade():
    if _existe_tabla():
        _cambiar(5, "'PRE', 'FAC', 'AMBOS'")


def downgrade():
    if _existe_tabla():
        op.execute(sa.text("UPDATE %s SET criterio = 'PRE' WHERE criterio = 'AMBOS'" % TABLA))
        _cambiar(3, "'PRE', 'FAC'")
