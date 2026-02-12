"""Add SabioGo materialized views for facts

Revision ID: 20260212_add_sabiogo_facts
Revises: 20260212_add_sabiogo_mapeos
Create Date: 2026-02-12 01:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260212_add_sabiogo_facts"
down_revision = "20260212_add_sabiogo_mapeos"
branch_labels = None
depends_on = None


def view_exists(view_name):
    """Verifica si una vista materializada existe."""
    bind = op.get_bind()
    result = bind.execute(text(f"""
        SELECT EXISTS (
            SELECT 1 FROM pg_matviews 
            WHERE schemaname = 'public' AND matviewname = '{view_name}'
        )
    """))
    return result.scalar()


def upgrade():
    bind = op.get_bind()
    
    # Vista materializada: fact_ventas_sabiogo
    if not view_exists('fact_ventas_sabiogo'):
        bind.execute(text("""
            CREATE MATERIALIZED VIEW fact_ventas_sabiogo AS
            SELECT 
                v.id,
                v.fecha,
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
                v.total,
                v.marca,
                v.modelo
            FROM stg_sabiogo_ventas v
            LEFT JOIN sabiogo_product_map pm ON v.codigo = pm.codigo AND pm.activo = true
            LEFT JOIN sabiogo_client_map cm ON v.cliente = cm.cliente 
                AND (v.condicion_iva = cm.condicion_iva OR (v.condicion_iva IS NULL AND cm.condicion_iva IS NULL))
                AND cm.activo = true
            LEFT JOIN sabiogo_location_map lm ON v.sucursal = lm.sucursal 
                AND (v.deposito = lm.deposito OR (v.deposito IS NULL AND lm.deposito IS NULL))
                AND lm.activo = true
            WHERE v.estado = 'procesado'
            WITH DATA
        """))
        
        # Índices para la vista de ventas
        bind.execute(text("""
            CREATE UNIQUE INDEX idx_fact_ventas_pk 
            ON fact_ventas_sabiogo (id)
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_ventas_fecha 
            ON fact_ventas_sabiogo (fecha)
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_ventas_product 
            ON fact_ventas_sabiogo (product_id, fecha) 
            WHERE product_id IS NOT NULL
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_ventas_client 
            ON fact_ventas_sabiogo (client_id, fecha) 
            WHERE client_id IS NOT NULL
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_ventas_location 
            ON fact_ventas_sabiogo (location_id, fecha) 
            WHERE location_id IS NOT NULL
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_ventas_vendedor 
            ON fact_ventas_sabiogo (vendedor, fecha)
        """))
    
    # Vista materializada: fact_costos_sabiogo
    if not view_exists('fact_costos_sabiogo'):
        bind.execute(text("""
            CREATE MATERIALIZED VIEW fact_costos_sabiogo AS
            SELECT 
                c.id,
                c.fecha,
                c.codigo,
                pm.product_id,
                lm.location_id,
                c.proveedor,
                c.forma_pago,
                c.tipo,
                c.rubro,
                c.nro_comprob,
                c.kilos,
                c.cajas,
                c.neto,
                c.subtot as costo_bruto,
                c.iva,
                c.total,
                c.marca,
                c.modelo
            FROM stg_sabiogo_compras c
            LEFT JOIN sabiogo_product_map pm ON c.codigo = pm.codigo AND pm.activo = true
            LEFT JOIN sabiogo_location_map lm ON c.sucursal = lm.sucursal 
                AND (c.deposito = lm.deposito OR (c.deposito IS NULL AND lm.deposito IS NULL))
                AND lm.activo = true
            WHERE c.estado = 'procesado'
            WITH DATA
        """))
        
        # Índices para la vista de costos
        bind.execute(text("""
            CREATE UNIQUE INDEX idx_fact_costos_pk 
            ON fact_costos_sabiogo (id)
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_costos_fecha 
            ON fact_costos_sabiogo (fecha)
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_costos_product 
            ON fact_costos_sabiogo (product_id, fecha) 
            WHERE product_id IS NOT NULL
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_costos_location 
            ON fact_costos_sabiogo (location_id, fecha) 
            WHERE location_id IS NOT NULL
        """))
        
        bind.execute(text("""
            CREATE INDEX idx_fact_costos_proveedor 
            ON fact_costos_sabiogo (proveedor, fecha)
        """))
    
    # Vista regular (no materializada): vw_margen_producto
    # Esta vista combina ventas y costos para calcular márgenes
    bind.execute(text("""
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
    """))


def downgrade():
    bind = op.get_bind()
    
    # Drop vista regular
    bind.execute(text("DROP VIEW IF EXISTS vw_margen_producto"))
    
    # Drop vista materializada de costos
    if view_exists('fact_costos_sabiogo'):
        bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS fact_costos_sabiogo CASCADE"))
    
    # Drop vista materializada de ventas
    if view_exists('fact_ventas_sabiogo'):
        bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS fact_ventas_sabiogo CASCADE"))
