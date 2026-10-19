-- Validación post-release para 20260730_add_empresa_attribution.
--
-- Este archivo es sólo lectura: no asigna empresa ni modifica el histórico.
-- Ejecutar después de scripts/migrate_db_safely.sh con:
--   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
--     -f scripts/sql/validate_20260730_empresa_attribution.sql
--
-- Preservación de filas
-- --------------------
-- La base no conserva un snapshot de conteos previo a la migración. Antes de
-- migrar, capturá los cinco conteos y pasalos a esta misma validación:
--
--   WITH before_counts AS (
--     SELECT
--       (SELECT count(*) FROM movimientos_caja) AS movimientos_before,
--       (SELECT count(*) FROM adelantos) AS adelantos_before,
--       (SELECT count(*) FROM liquidaciones_sueldo) AS liquidaciones_before,
--       (SELECT count(*) FROM employees) AS employees_before,
--       (SELECT count(*) FROM purchase_orders) AS purchase_orders_before
--   )
--   SELECT * FROM before_counts;
--
--   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 \
--     -v movimientos_before=... -v adelantos_before=... \
--     -v liquidaciones_before=... -v employees_before=... \
--     -v purchase_orders_before=... \
--     -f scripts/sql/validate_20260730_empresa_attribution.sql
--
-- Sin los parámetros, el script igualmente valida estructura e informa los
-- conteos posteriores y los históricos sin empresa. No crea una tabla de
-- auditoría artificialmente.

\set ON_ERROR_STOP on

DO $$
DECLARE
    required_table text;
BEGIN
    FOREACH required_table IN ARRAY ARRAY[
        'movimientos_caja',
        'adelantos',
        'liquidaciones_sueldo',
        'employees',
        'purchase_orders'
    ]
    LOOP
        IF to_regclass('public.' || required_table) IS NULL THEN
            RAISE EXCEPTION 'Falta la tabla %', required_table;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = required_table
              AND column_name = 'empresa'
              AND is_nullable = 'YES'
        ) THEN
            RAISE EXCEPTION 'Falta columna nullable %.empresa', required_table;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_row.relnamespace
        WHERE schema_row.nspname = 'public'
          AND table_row.relname = 'movimientos_caja'
          AND constraint_row.conname = 'chk_movimientos_caja_empresa'
          AND constraint_row.contype = 'c'
    ) THEN
        RAISE EXCEPTION 'Falta check chk_movimientos_caja_empresa';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_row.relnamespace
        WHERE schema_row.nspname = 'public'
          AND table_row.relname = 'adelantos'
          AND constraint_row.conname = 'chk_adelantos_empresa'
          AND constraint_row.contype = 'c'
    ) THEN
        RAISE EXCEPTION 'Falta check chk_adelantos_empresa';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_row.relnamespace
        WHERE schema_row.nspname = 'public'
          AND table_row.relname = 'liquidaciones_sueldo'
          AND constraint_row.conname = 'chk_liquidaciones_sueldo_empresa'
          AND constraint_row.contype = 'c'
    ) THEN
        RAISE EXCEPTION 'Falta check chk_liquidaciones_sueldo_empresa';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_row.relnamespace
        WHERE schema_row.nspname = 'public'
          AND table_row.relname = 'employees'
          AND constraint_row.conname = 'chk_employees_empresa'
          AND constraint_row.contype = 'c'
    ) THEN
        RAISE EXCEPTION 'Falta check chk_employees_empresa';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_class table_row ON table_row.oid = constraint_row.conrelid
        JOIN pg_namespace schema_row ON schema_row.oid = table_row.relnamespace
        WHERE schema_row.nspname = 'public'
          AND table_row.relname = 'purchase_orders'
          AND constraint_row.conname = 'chk_purchase_orders_empresa'
          AND constraint_row.contype = 'c'
    ) THEN
        RAISE EXCEPTION 'Falta check chk_purchase_orders_empresa';
    END IF;

    IF to_regclass('public.idx_movimiento_empresa_fecha') IS NULL
       OR to_regclass('public.idx_adelantos_empresa_fecha_pago') IS NULL
       OR to_regclass('public.idx_liquidaciones_sueldo_empresa_fecha') IS NULL
       OR to_regclass('public.idx_employees_empresa') IS NULL
       OR to_regclass('public.idx_purchase_orders_empresa_order_date') IS NULL THEN
        RAISE EXCEPTION 'Falta al menos un índice de empresa de la revisión';
    END IF;
END
$$;

WITH post_counts AS (
    SELECT
        (SELECT count(*) FROM movimientos_caja) AS movimientos,
        (SELECT count(*) FROM adelantos) AS adelantos,
        (SELECT count(*) FROM liquidaciones_sueldo) AS liquidaciones,
        (SELECT count(*) FROM employees) AS employees,
        (SELECT count(*) FROM purchase_orders) AS purchase_orders,
        (SELECT count(*) FROM movimientos_caja WHERE empresa IS NULL) AS movimientos_historicos_sin_empresa,
        (SELECT count(*) FROM adelantos WHERE empresa IS NULL) AS adelantos_historicos_sin_empresa,
        (SELECT count(*) FROM liquidaciones_sueldo WHERE empresa IS NULL) AS liquidaciones_historicas_sin_empresa,
        (SELECT count(*) FROM employees WHERE empresa IS NULL) AS empleados_sin_empresa,
        (SELECT count(*) FROM purchase_orders WHERE empresa IS NULL) AS compras_historicas_sin_empresa
)
SELECT
    (SELECT string_agg(version_num, ', ' ORDER BY version_num) FROM alembic_version) AS revisions,
    post_counts.*
FROM post_counts;

\if :{?movimientos_before}
DO $$
BEGIN
    IF (SELECT count(*) FROM movimientos_caja) <> (:'movimientos_before')::bigint THEN
        RAISE EXCEPTION 'Cantidad de movimientos_caja cambió durante la migración';
    END IF;
    IF (SELECT count(*) FROM adelantos) <> (:'adelantos_before')::bigint THEN
        RAISE EXCEPTION 'Cantidad de adelantos cambió durante la migración';
    END IF;
    IF (SELECT count(*) FROM liquidaciones_sueldo) <> (:'liquidaciones_before')::bigint THEN
        RAISE EXCEPTION 'Cantidad de liquidaciones_sueldo cambió durante la migración';
    END IF;
    IF (SELECT count(*) FROM employees) <> (:'employees_before')::bigint THEN
        RAISE EXCEPTION 'Cantidad de employees cambió durante la migración';
    END IF;
    IF (SELECT count(*) FROM purchase_orders) <> (:'purchase_orders_before')::bigint THEN
        RAISE EXCEPTION 'Cantidad de purchase_orders cambió durante la migración';
    END IF;
END
$$;

WITH expected_counts AS (
    SELECT
        (:'movimientos_before')::bigint AS movimientos,
        (:'adelantos_before')::bigint AS adelantos,
        (:'liquidaciones_before')::bigint AS liquidaciones,
        (:'employees_before')::bigint AS employees,
        (:'purchase_orders_before')::bigint AS purchase_orders
),
post_counts AS (
    SELECT
        (SELECT count(*) FROM movimientos_caja) AS movimientos,
        (SELECT count(*) FROM adelantos) AS adelantos,
        (SELECT count(*) FROM liquidaciones_sueldo) AS liquidaciones,
        (SELECT count(*) FROM employees) AS employees,
        (SELECT count(*) FROM purchase_orders) AS purchase_orders
)
SELECT
    expected_counts.*,
    post_counts.*,
    expected_counts.movimientos = post_counts.movimientos AS movimientos_preservados,
    expected_counts.adelantos = post_counts.adelantos AS adelantos_preservados,
    expected_counts.liquidaciones = post_counts.liquidaciones AS liquidaciones_preservadas,
    expected_counts.employees = post_counts.employees AS employees_preservados,
    expected_counts.purchase_orders = post_counts.purchase_orders AS purchase_orders_preservadas
FROM expected_counts
CROSS JOIN post_counts;
\else
\echo 'Conteos previos no provistos: se omite comparación de preservación de filas.'
\endif
