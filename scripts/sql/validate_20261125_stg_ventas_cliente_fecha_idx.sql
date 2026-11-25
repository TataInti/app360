\set ON_ERROR_STOP on

DO $$
BEGIN
    IF (SELECT count(*) FROM alembic_version) <> 1 THEN
        RAISE EXCEPTION 'alembic_version debe tener exactamente una fila';
    END IF;
    IF (SELECT version_num FROM alembic_version) <> '20261125_stg_ventas_cliente_fecha_idx' THEN
        RAISE EXCEPTION 'La revision Alembic no es 20261125_stg_ventas_cliente_fecha_idx';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
        WHERE c.relname = 'ix_stg_sabiogo_ventas_cliente_trim_fecha' AND i.indisvalid
    ) THEN
        RAISE EXCEPTION 'Falta el indice valido ix_stg_sabiogo_ventas_cliente_trim_fecha';
    END IF;
END
$$;

SELECT
    (SELECT version_num FROM alembic_version) AS revision,
    (SELECT count(*) FROM stg_sabiogo_ventas) AS lineas_ventas,
    pg_size_pretty(pg_relation_size('ix_stg_sabiogo_ventas_cliente_trim_fecha')) AS tamano_indice;
