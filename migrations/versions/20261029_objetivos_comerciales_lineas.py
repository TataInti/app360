"""Convert commercial objectives into monthly dimension lines.

Revision ID: 20261029_objetivos_comerciales_lineas
Revises: 20261021_comercial_cliente_criterio
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20261029_objetivos_comerciales_lineas"
down_revision = "20261021_comercial_cliente_criterio"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(
        "ix_comercial_objetivos_mes_empresa_medida",
        table_name="comercial_objetivos",
    )

    with op.batch_alter_table("comercial_objetivos") as batch_op:
        batch_op.drop_constraint(
            "uq_comercial_objetivo_vendedor_empresa_mes_medida",
            type_="unique",
        )
        batch_op.drop_constraint("ck_comercial_objetivo_empresa", type_="check")
        batch_op.drop_constraint("ck_comercial_objetivo_medida", type_="check")
        batch_op.drop_constraint("ck_comercial_objetivo_meta_positiva", type_="check")
        batch_op.add_column(sa.Column("dimension_tipo", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("dimension_valor", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "meta_importe",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "meta_cajas",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "meta_kilos",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.alter_column(
            "empresa",
            existing_type=sa.String(length=10),
            nullable=True,
        )
        batch_op.alter_column(
            "medida",
            existing_type=sa.String(length=10),
            nullable=True,
        )
        batch_op.alter_column(
            "meta",
            existing_type=sa.Numeric(precision=18, scale=4),
            nullable=True,
        )

    objetivos = sa.table(
        "comercial_objetivos",
        sa.column("empresa", sa.String(length=10)),
        sa.column("medida", sa.String(length=10)),
        sa.column("meta", sa.Numeric(18, 4)),
        sa.column("dimension_tipo", sa.String(length=20)),
        sa.column("dimension_valor", sa.String(length=255)),
        sa.column("meta_importe", sa.Numeric(18, 4)),
        sa.column("meta_cajas", sa.Numeric(18, 4)),
        sa.column("meta_kilos", sa.Numeric(18, 4)),
    )
    op.execute(
        sa.update(objetivos)
        .where(objetivos.c.dimension_tipo.is_(None))
        .values(
            dimension_tipo="empresa",
            dimension_valor=objetivos.c.empresa,
            meta_importe=sa.case(
                (objetivos.c.medida == "importe", objetivos.c.meta),
                else_=0,
            ),
            meta_cajas=sa.case(
                (objetivos.c.medida == "cajas", objetivos.c.meta),
                else_=0,
            ),
            meta_kilos=sa.case(
                (objetivos.c.medida == "kilos", objetivos.c.meta),
                else_=0,
            ),
        )
    )

    with op.batch_alter_table("comercial_objetivos") as batch_op:
        batch_op.alter_column(
            "dimension_tipo",
            existing_type=sa.String(length=20),
            nullable=False,
        )
        batch_op.alter_column(
            "dimension_valor",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_comercial_objetivo_dimension_tipo",
            "dimension_tipo IN ('empresa', 'rubro', 'subrubro', 'marca', 'producto')",
        )
        batch_op.create_check_constraint(
            "ck_comercial_objetivo_dimension_valor",
            "length(trim(dimension_valor)) > 0",
        )
        batch_op.create_check_constraint(
            "ck_comercial_objetivo_empresa_valor",
            "dimension_tipo != 'empresa' OR dimension_valor IN ('CARNES', 'LACTEOS')",
        )
        batch_op.create_check_constraint(
            "ck_comercial_objetivo_metas_no_negativas",
            "meta_importe >= 0 AND meta_cajas >= 0 AND meta_kilos >= 0",
        )
        batch_op.create_check_constraint(
            "ck_comercial_objetivo_al_menos_una_meta",
            "meta_importe > 0 OR meta_cajas > 0 OR meta_kilos > 0",
        )


    op.create_index(
        "ix_comercial_objetivos_mes_vendedor",
        "comercial_objetivos",
        ["mes", "vendedor_id"],
        unique=False,
    )
    op.create_index(
        "ix_comercial_objetivos_mes_dimension",
        "comercial_objetivos",
        ["mes", "dimension_tipo", "dimension_valor"],
        unique=False,
    )


def downgrade():
    raise RuntimeError(
        "La migración de objetivos comerciales por líneas es forward-only."
    )
