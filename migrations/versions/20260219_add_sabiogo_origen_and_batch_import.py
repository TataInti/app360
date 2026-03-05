"""Add SabioGo origen fields + batch import logs + refresh facts for origen join

Revision ID: 20260219_add_sabiogo_origen_and_batch_import
Revises: 20260212_remove_destinos_arqueo
Create Date: 2026-02-19 00:00:00

Objetivos:
- Introducir el concepto de "origen" (CARNES/LACTEOS/LEGACY) para soportar dos catálogos SabioGo.
- Robustecer importación guardando codigo_raw además de codigo normalizado.
- Cambiar unicidad de mapeos de producto a (origen,codigo).
- Re-crear materialized views de facts para joinear por (origen,codigo).
- Agregar tabla de logs para import batch (manifiesto + estado).

Nota: La migración intenta ser SAFE; solo aplica cambios si detecta que faltan.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260219_add_sabiogo_origen_and_batch_import"
down_revision = "20260212_remove_destinos_arqueo"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    cols = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in cols


def constraint_exists(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    uniques = inspector.get_unique_constraints(table_name)
    return any(u.get("name") == constraint_name for u in uniques)


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    idxs = inspector.get_indexes(table_name)
    return any(i.get("name") == index_name for i in idxs)


def matview_exists(view_name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews
                WHERE schemaname = 'public' AND matviewname = :v
            )
            """
        ),
        {"v": view_name},
    )
    return bool(res.scalar())


def upgrade():
    bind = op.get_bind()

    # 1) Staging: agregar origen + codigo_raw
    for table_name, origen_idx_name, origen_fecha_codigo_idx in [
        ("stg_sabiogo_ventas", "ix_stg_sabiogo_ventas_origen", "idx_stg_ventas_origen_fecha_codigo"),
        ("stg_sabiogo_compras", "ix_stg_sabiogo_compras_origen", "idx_stg_compras_origen_fecha_codigo"),
    ]:
        if table_exists(table_name):
            if not column_exists(table_name, "origen"):
                op.add_column(table_name, sa.Column("origen", sa.String(length=20), nullable=True, server_default=sa.text("'LEGACY'")))
            if not column_exists(table_name, "codigo_raw"):
                op.add_column(table_name, sa.Column("codigo_raw", sa.String(length=80), nullable=True))

            # Backfill simple para datos existentes
            bind.execute(text(f"UPDATE {table_name} SET origen = COALESCE(origen, 'LEGACY')"))
            bind.execute(text(f"UPDATE {table_name} SET codigo_raw = COALESCE(codigo_raw, codigo)"))

            if not index_exists(table_name, origen_fecha_codigo_idx):
                op.create_index(origen_fecha_codigo_idx, table_name, ["origen", "fecha", "codigo"], unique=False)

    # 2) Mapeos producto: agregar origen y ajustar constraint única
    if table_exists("sabiogo_product_map"):
        if not column_exists("sabiogo_product_map", "origen"):
            op.add_column(
                "sabiogo_product_map",
                sa.Column("origen", sa.String(length=20), nullable=True, server_default=sa.text("'LEGACY'")),
            )
        bind.execute(text("UPDATE sabiogo_product_map SET origen = COALESCE(origen, 'LEGACY')"))

        # Reemplazar uq_sabiogo_product_map_codigo por uq_sabiogo_product_map_origen_codigo
        if constraint_exists("sabiogo_product_map", "uq_sabiogo_product_map_codigo"):
            op.drop_constraint("uq_sabiogo_product_map_codigo", "sabiogo_product_map", type_="unique")

        if not constraint_exists("sabiogo_product_map", "uq_sabiogo_product_map_origen_codigo"):
            op.create_unique_constraint(
                "uq_sabiogo_product_map_origen_codigo",
                "sabiogo_product_map",
                ["origen", "codigo"],
            )

        if not index_exists("sabiogo_product_map", "idx_sabiogo_product_origen_codigo"):
            op.create_index(
                "idx_sabiogo_product_origen_codigo",
                "sabiogo_product_map",
                ["origen", "codigo"],
                unique=False,
            )

    # 3) Logs batch
    if not table_exists("logs_sabiogo_batch"):
        op.create_table(
            "logs_sabiogo_batch",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.String(length=120), nullable=False, index=True),
            sa.Column("fecha_datos", sa.Date(), nullable=True, index=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'"), index=True),
            sa.Column("manifest_path", sa.String(length=512), nullable=True),
            sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
            sa.Column("stats_json", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint("batch_id", name="uq_logs_sabiogo_batch_batch_id"),
        )
        op.create_index("idx_logs_sabiogo_batch_status_fecha", "logs_sabiogo_batch", ["status", "fecha_datos"], unique=False)

    # 4) Facts: recrear MVs con join por (origen,codigo)
    # Nota: solo en Postgres; en SQLite de tests no existen pg_matviews.
    try:
        if matview_exists("fact_ventas_sabiogo"):
            bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS fact_ventas_sabiogo CASCADE"))
        if matview_exists("fact_costos_sabiogo"):
            bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS fact_costos_sabiogo CASCADE"))

        bind.execute(
            text(
                """
                CREATE MATERIALIZED VIEW fact_ventas_sabiogo AS
                SELECT
                    v.id,
                    v.fecha,
                    v.origen,
                    v.codigo,
                    pm.product_id,
                    cm.client_id,
                    lm.location_id,
                    v.vendedor,
                    v.forma_pago,
                    v.tipo,
                    v.rubro,
                    v.nro_comprob,
                    v.kilos,
                    v.cajas,
                    v.neto,
                    v.subtot as ingresos_bruto,
                    v.iva,
                    COALESCE(
                        NULLIF(to_jsonb(v)->>'total', '')::numeric,
                        NULLIF(to_jsonb(v)->>'total_venta', '')::numeric,
                        NULLIF(to_jsonb(v)->>'importe_total', '')::numeric,
                        COALESCE(NULLIF(to_jsonb(v)->>'subtot', '')::numeric, 0)
                        + COALESCE(NULLIF(to_jsonb(v)->>'iva', '')::numeric, 0)
                    ) as total,
                    v.marca,
                    v.modelo
                FROM stg_sabiogo_ventas v
                LEFT JOIN sabiogo_product_map pm
                    ON v.codigo = pm.codigo
                    AND COALESCE(v.origen, 'LEGACY') = COALESCE(pm.origen, 'LEGACY')
                    AND pm.activo = true
                LEFT JOIN sabiogo_client_map cm
                    ON v.cliente = cm.cliente
                    AND (v.condicion_iva = cm.condicion_iva OR (v.condicion_iva IS NULL AND cm.condicion_iva IS NULL))
                    AND cm.activo = true
                LEFT JOIN sabiogo_location_map lm
                    ON v.sucursal = lm.sucursal
                    AND (v.deposito = lm.deposito OR (v.deposito IS NULL AND lm.deposito IS NULL))
                    AND lm.activo = true
                WHERE v.estado = 'procesado'
                WITH DATA
                """
            )
        )

        bind.execute(text("CREATE UNIQUE INDEX idx_fact_ventas_pk ON fact_ventas_sabiogo (id)"))
        bind.execute(text("CREATE INDEX idx_fact_ventas_fecha ON fact_ventas_sabiogo (fecha)"))
        bind.execute(text("CREATE INDEX idx_fact_ventas_origen_fecha ON fact_ventas_sabiogo (origen, fecha)"))
        bind.execute(
            text(
                """
                CREATE INDEX idx_fact_ventas_product
                ON fact_ventas_sabiogo (product_id, fecha)
                WHERE product_id IS NOT NULL
                """
            )
        )

        bind.execute(
            text(
                """
                CREATE MATERIALIZED VIEW fact_costos_sabiogo AS
                SELECT
                    c.id,
                    c.fecha,
                    c.origen,
                    c.codigo,
                    pm.product_id,
                    lm.location_id,
                    COALESCE(
                        NULLIF(to_jsonb(c)->>'proveedor', ''),
                        NULLIF(to_jsonb(c)->>'cliente', ''),
                        NULLIF(to_jsonb(c)->>'vendedor', '')
                    ) as proveedor,
                    c.forma_pago,
                    c.tipo,
                    c.rubro,
                    c.nro_comprob,
                    c.kilos,
                    c.cajas,
                    c.neto,
                    c.subtot as costo_bruto,
                    c.iva,
                    COALESCE(
                        NULLIF(to_jsonb(c)->>'total', '')::numeric,
                        NULLIF(to_jsonb(c)->>'total_compra', '')::numeric,
                        NULLIF(to_jsonb(c)->>'importe_total', '')::numeric,
                        COALESCE(NULLIF(to_jsonb(c)->>'subtot', '')::numeric, 0)
                        + COALESCE(NULLIF(to_jsonb(c)->>'iva', '')::numeric, 0)
                    ) as total,
                    c.marca,
                    c.modelo
                FROM stg_sabiogo_compras c
                LEFT JOIN sabiogo_product_map pm
                    ON c.codigo = pm.codigo
                    AND COALESCE(c.origen, 'LEGACY') = COALESCE(pm.origen, 'LEGACY')
                    AND pm.activo = true
                LEFT JOIN sabiogo_location_map lm
                    ON c.sucursal = lm.sucursal
                    AND (c.deposito = lm.deposito OR (c.deposito IS NULL AND lm.deposito IS NULL))
                    AND lm.activo = true
                WHERE c.estado = 'procesado'
                WITH DATA
                """
            )
        )

        bind.execute(text("CREATE UNIQUE INDEX idx_fact_costos_pk ON fact_costos_sabiogo (id)"))
        bind.execute(text("CREATE INDEX idx_fact_costos_fecha ON fact_costos_sabiogo (fecha)"))
        bind.execute(text("CREATE INDEX idx_fact_costos_origen_fecha ON fact_costos_sabiogo (origen, fecha)"))
        bind.execute(
            text(
                """
                CREATE INDEX idx_fact_costos_product
                ON fact_costos_sabiogo (product_id, fecha)
                WHERE product_id IS NOT NULL
                """
            )
        )

        # Mantener vista de márgenes
        bind.execute(
            text(
                """
                CREATE OR REPLACE VIEW vw_margen_producto AS
                SELECT
                    COALESCE(v.product_id, c.product_id) as product_id,
                    p.sku,
                    p.name as producto,
                    p.category,
                    DATE_TRUNC('month', COALESCE(v.fecha, c.fecha))::date as periodo_mes,
                    COALESCE(SUM(v.ingresos_bruto), 0) as ingresos_totales,
                    COALESCE(SUM(c.costo_bruto), 0) as costos_totales,
                    COALESCE(SUM(v.ingresos_bruto), 0) - COALESCE(SUM(c.costo_bruto), 0) as margen_bruto,
                    CASE
                        WHEN COALESCE(SUM(v.ingresos_bruto), 0) > 0
                        THEN ((COALESCE(SUM(v.ingresos_bruto), 0) - COALESCE(SUM(c.costo_bruto), 0))
                              / COALESCE(SUM(v.ingresos_bruto), 0) * 100)
                        ELSE 0
                    END as margen_porcentual,
                    COALESCE(SUM(v.kilos), 0) as kilos_vendidos,
                    COALESCE(SUM(c.kilos), 0) as kilos_comprados,
                    COALESCE(SUM(v.cajas), 0) as cajas_vendidas,
                    COALESCE(SUM(c.cajas), 0) as cajas_compradas
                FROM fact_ventas_sabiogo v
                FULL OUTER JOIN fact_costos_sabiogo c
                    ON v.product_id = c.product_id
                    AND DATE_TRUNC('month', v.fecha) = DATE_TRUNC('month', c.fecha)
                LEFT JOIN products p ON COALESCE(v.product_id, c.product_id) = p.id
                WHERE COALESCE(v.product_id, c.product_id) IS NOT NULL
                GROUP BY
                    COALESCE(v.product_id, c.product_id),
                    p.sku,
                    p.name,
                    p.category,
                    DATE_TRUNC('month', COALESCE(v.fecha, c.fecha))::date
                """
            )
        )
    except Exception:
        # En SQLite / entornos sin pg_matviews, skip
        pass


def downgrade():
    # Downgrade best-effort (no re-crea constraints anteriores si ya existían).
    bind = op.get_bind()

    if table_exists("logs_sabiogo_batch"):
        op.drop_index("idx_logs_sabiogo_batch_status_fecha", table_name="logs_sabiogo_batch")
        op.drop_constraint("uq_logs_sabiogo_batch_batch_id", "logs_sabiogo_batch", type_="unique")
        op.drop_table("logs_sabiogo_batch")

    # Facts: dejar a cargo de migración original si se requiere rollback manual.
    try:
        bind.execute(text("DROP VIEW IF EXISTS vw_margen_producto"))
        bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS fact_costos_sabiogo CASCADE"))
        bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS fact_ventas_sabiogo CASCADE"))
    except Exception:
        pass

    # Revertir constraints de mapeos (best-effort)
    if table_exists("sabiogo_product_map"):
        if constraint_exists("sabiogo_product_map", "uq_sabiogo_product_map_origen_codigo"):
            op.drop_constraint("uq_sabiogo_product_map_origen_codigo", "sabiogo_product_map", type_="unique")
        if not constraint_exists("sabiogo_product_map", "uq_sabiogo_product_map_codigo"):
            op.create_unique_constraint("uq_sabiogo_product_map_codigo", "sabiogo_product_map", ["codigo"])

        if index_exists("sabiogo_product_map", "idx_sabiogo_product_origen_codigo"):
            op.drop_index("idx_sabiogo_product_origen_codigo", table_name="sabiogo_product_map")

        if column_exists("sabiogo_product_map", "origen"):
            op.drop_column("sabiogo_product_map", "origen")

    for table_name in ["stg_sabiogo_ventas", "stg_sabiogo_compras"]:
        if table_exists(table_name):
            if column_exists(table_name, "codigo_raw"):
                op.drop_column(table_name, "codigo_raw")
            if column_exists(table_name, "origen"):
                op.drop_column(table_name, "origen")
