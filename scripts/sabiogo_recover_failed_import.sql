-- Recuperación de staging SabioGo tras cargas fallidas/timeouts.
-- Uso recomendado:
--   psql "$DATABASE_URL" -f scripts/sabiogo_recover_failed_import.sql
--
-- Este script:
-- 1) muestra estado actual de staging
-- 2) elimina pendientes recientes (ventana configurable)
-- 3) elimina duplicados marcados recientes (opcional por defecto activado)
-- 4) refresca facts (intenta CONCURRENTLY; fallback normal)

BEGIN;

-- Ventana de limpieza: ajustar si hace falta.
-- Por defecto se limpia lo ingresado en los ultimos 7 dias.
CREATE TEMP TABLE _cfg_window AS
SELECT NOW() - INTERVAL '7 days' AS since_ts;

-- 1) Diagnóstico previo
SELECT 'ventas_pre' AS tabla, estado, origen, COUNT(*) AS cantidad,
       MIN(fecha_import) AS min_fecha_import,
       MAX(fecha_import) AS max_fecha_import
FROM stg_sabiogo_ventas
GROUP BY estado, origen
ORDER BY estado, origen;

SELECT 'compras_pre' AS tabla, estado, origen, COUNT(*) AS cantidad,
       MIN(fecha_import) AS min_fecha_import,
       MAX(fecha_import) AS max_fecha_import
FROM stg_sabiogo_compras
GROUP BY estado, origen
ORDER BY estado, origen;

-- 2) Limpieza de pendientes huérfanos recientes
DELETE FROM stg_sabiogo_ventas
WHERE estado = 'pendiente'
  AND fecha_import >= (SELECT since_ts FROM _cfg_window);

DELETE FROM stg_sabiogo_compras
WHERE estado = 'pendiente'
  AND fecha_import >= (SELECT since_ts FROM _cfg_window);

-- 3) Limpieza de duplicados marcados recientes (opcional, aquí habilitada)
DELETE FROM stg_sabiogo_ventas
WHERE estado = 'duplicado'
  AND fecha_import >= (SELECT since_ts FROM _cfg_window);

DELETE FROM stg_sabiogo_compras
WHERE estado = 'duplicado'
  AND fecha_import >= (SELECT since_ts FROM _cfg_window);

COMMIT;

-- 4) Refresh de facts fuera de transacción
-- CONCURRENTLY requiere no estar dentro de BEGIN/COMMIT.
DO $$
BEGIN
    BEGIN
        EXECUTE 'REFRESH MATERIALIZED VIEW CONCURRENTLY fact_ventas_sabiogo';
        EXECUTE 'REFRESH MATERIALIZED VIEW CONCURRENTLY fact_costos_sabiogo';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'CONCURRENTLY no disponible, usando refresh estándar: %', SQLERRM;
        EXECUTE 'REFRESH MATERIALIZED VIEW fact_ventas_sabiogo';
        EXECUTE 'REFRESH MATERIALIZED VIEW fact_costos_sabiogo';
    END;
END
$$;

-- Diagnóstico final
SELECT 'ventas_post' AS tabla, estado, origen, COUNT(*) AS cantidad,
       MIN(fecha_import) AS min_fecha_import,
       MAX(fecha_import) AS max_fecha_import
FROM stg_sabiogo_ventas
GROUP BY estado, origen
ORDER BY estado, origen;

SELECT 'compras_post' AS tabla, estado, origen, COUNT(*) AS cantidad,
       MIN(fecha_import) AS min_fecha_import,
       MAX(fecha_import) AS max_fecha_import
FROM stg_sabiogo_compras
GROUP BY estado, origen
ORDER BY estado, origen;
