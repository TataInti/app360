"""Create the independent commercial sellers catalog and explicit aliases.

Revision ID: 20261020_comercial_vendedores
Revises: 20260729_ensure_efectivo_iva
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261020_comercial_vendedores"
down_revision = "20260729_ensure_efectivo_iva"
branch_labels = None
depends_on = None


EQUIVALENCIAS_COMERCIALES = (
    ("Benjamín Kalja", ("KALJA BENJAMIN", "BENJAMIN KALJA")),
    ("Walter Medina", ("MEDINA WALTER", "WALTER")),
)


def _table_exists(table_name):
    return table_name in inspect(op.get_bind()).get_table_names()


def _normalizar(nombre):
    return " ".join((nombre or "").split()).upper()


def _seed_catalog(bind):
    vendedores = sa.table(
        "comercial_vendedores",
        sa.column("id", sa.Integer),
        sa.column("nombre_visible", sa.String(200)),
        sa.column("activo", sa.Boolean),
    )
    aliases = sa.table(
        "comercial_vendedor_aliases",
        sa.column("id", sa.Integer),
        sa.column("vendedor_id", sa.Integer),
        sa.column("nombre_origen", sa.String(200)),
        sa.column("nombre_normalizado", sa.String(200)),
    )

    for nombre_visible, nombres_origen in EQUIVALENCIAS_COMERCIALES:
        vendedor_id = bind.execute(
            sa.select(vendedores.c.id).where(
                vendedores.c.nombre_visible == nombre_visible
            )
        ).scalar_one_or_none()
        if vendedor_id is None:
            bind.execute(
                sa.insert(vendedores).values(
                    nombre_visible=nombre_visible,
                    activo=True,
                )
            )
            vendedor_id = bind.execute(
                sa.select(vendedores.c.id).where(
                    vendedores.c.nombre_visible == nombre_visible
                )
            ).scalar_one()

        for nombre_origen in nombres_origen:
            nombre_normalizado = _normalizar(nombre_origen)
            alias_existente = bind.execute(
                sa.select(aliases.c.id).where(
                    sa.or_(
                        aliases.c.nombre_origen == nombre_origen,
                        aliases.c.nombre_normalizado == nombre_normalizado,
                    )
                )
            ).scalar_one_or_none()
            if alias_existente is not None:
                continue

            bind.execute(
                sa.insert(aliases).values(
                    vendedor_id=vendedor_id,
                    nombre_origen=nombre_origen,
                    nombre_normalizado=nombre_normalizado,
                )
            )


def upgrade():
    if not _table_exists("comercial_vendedores"):
        op.create_table(
            "comercial_vendedores",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nombre_visible", sa.String(length=200), nullable=False),
            sa.Column(
                "activo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.UniqueConstraint(
                "nombre_visible",
                name="uq_comercial_vendedores_nombre_visible",
            ),
        )

    if not _table_exists("comercial_vendedor_aliases"):
        op.create_table(
            "comercial_vendedor_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("vendedor_id", sa.Integer(), nullable=False),
            sa.Column("nombre_origen", sa.String(length=200), nullable=False),
            sa.Column("nombre_normalizado", sa.String(length=200), nullable=False),
            sa.ForeignKeyConstraint(
                ["vendedor_id"],
                ["comercial_vendedores.id"],
                name="fk_comercial_vendedor_aliases_vendedor_id_comercial_vendedores",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "nombre_origen",
                name="uq_comercial_vendedor_aliases_nombre_origen",
            ),
            sa.UniqueConstraint(
                "nombre_normalizado",
                name="uq_comercial_vendedor_aliases_nombre_normalizado",
            ),
        )

    _seed_catalog(op.get_bind())


def downgrade():
    if _table_exists("comercial_vendedor_aliases"):
        op.drop_table("comercial_vendedor_aliases")
    if _table_exists("comercial_vendedores"):
        op.drop_table("comercial_vendedores")
