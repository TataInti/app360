-- Auditoria de solo lectura posterior al rebaseline 2026.
-- Ejecutar en el VPS con:
--   set -a; source /var/www/app360/.env; set +a
--   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f validate_rebaseline_2026.sql

\set ON_ERROR_STOP on
\pset pager off
\echo '=== BASE Y FECHA DE AUDITORIA ==='
SELECT current_database() AS database_name,
       current_user AS database_user,
       clock_timestamp() AS audited_at;

\echo '=== RESUMEN DE EJECUCIONES POR FECHA ==='
WITH expected AS (
    SELECT d::date AS fecha
    FROM generate_series(date '2026-01-01', date '2026-07-28', interval '1 day') AS d
), latest AS (
    SELECT DISTINCT ON (fecha_objetivo)
           fecha_objetivo,
           estado,
           filas_ventas,
           filas_compras,
           actualizada_en,
           mensaje
    FROM sabiogo_sync_runs
    WHERE fecha_objetivo BETWEEN date '2026-01-01' AND date '2026-07-28'
    ORDER BY fecha_objetivo, actualizada_en DESC NULLS LAST, id DESC
)
SELECT COUNT(*) AS dias_esperados,
       COUNT(*) FILTER (WHERE latest.estado = 'exitosa') AS dias_exitosos,
       COUNT(*) FILTER (WHERE latest.estado IS NULL) AS dias_sin_ejecucion,
       COUNT(*) FILTER (WHERE latest.estado IS NOT NULL AND latest.estado <> 'exitosa') AS dias_con_error
FROM expected
LEFT JOIN latest ON latest.fecha_objetivo = expected.fecha;

\echo '=== FECHAS SIN EJECUCION EXITOSA ==='
WITH expected AS (
    SELECT d::date AS fecha
    FROM generate_series(date '2026-01-01', date '2026-07-28', interval '1 day') AS d
), latest AS (
    SELECT DISTINCT ON (fecha_objetivo)
           fecha_objetivo,
           estado,
           filas_ventas,
           filas_compras,
           actualizada_en,
           mensaje
    FROM sabiogo_sync_runs
    WHERE fecha_objetivo BETWEEN date '2026-01-01' AND date '2026-07-28'
    ORDER BY fecha_objetivo, actualizada_en DESC NULLS LAST, id DESC
)
SELECT expected.fecha,
       latest.estado,
       latest.filas_ventas,
       latest.filas_compras,
       latest.actualizada_en,
       latest.mensaje
FROM expected
LEFT JOIN latest ON latest.fecha_objetivo = expected.fecha
WHERE latest.estado IS DISTINCT FROM 'exitosa'
ORDER BY expected.fecha;

\echo '=== STAGING 2026 POR MES, ORIGEN Y ESTADO ==='
WITH movimientos AS (
    SELECT 'VENTAS' AS tipo, fecha, origen, estado, subtot
    FROM stg_sabiogo_ventas
    WHERE fecha >= timestamp '2026-01-01'
      AND fecha < timestamp '2026-07-29'
    UNION ALL
    SELECT 'COMPRAS' AS tipo, fecha, origen, estado, subtot
    FROM stg_sabiogo_compras
    WHERE fecha >= timestamp '2026-01-01'
      AND fecha < timestamp '2026-07-29'
)
SELECT tipo,
       date_trunc('month', fecha)::date AS mes,
       COALESCE(origen, '<NULL>') AS origen,
       estado,
       COUNT(*) AS filas,
       COUNT(DISTINCT fecha::date) AS dias_con_filas,
       MIN(fecha)::date AS fecha_minima,
       MAX(fecha)::date AS fecha_maxima,
       ROUND(COALESCE(SUM(subtot), 0)::numeric, 2) AS subtot
FROM movimientos
GROUP BY tipo, date_trunc('month', fecha)::date, origen, estado
ORDER BY tipo, mes, origen, estado;

\echo '=== ESTADOS NO PROCESADOS EN 2026 ==='
SELECT 'VENTAS' AS tipo, estado, COUNT(*) AS filas
FROM stg_sabiogo_ventas
WHERE fecha >= timestamp '2026-01-01'
  AND fecha < timestamp '2026-07-29'
  AND estado <> 'procesado'
GROUP BY estado
UNION ALL
SELECT 'COMPRAS' AS tipo, estado, COUNT(*) AS filas
FROM stg_sabiogo_compras
WHERE fecha >= timestamp '2026-01-01'
  AND fecha < timestamp '2026-07-29'
  AND estado <> 'procesado'
GROUP BY estado
ORDER BY tipo, estado;

\echo '=== FACTS ==='
SELECT 'fact_ventas_sabiogo' AS fact,
       COUNT(*) AS filas,
       MIN(fecha)::date AS fecha_minima,
       MAX(fecha)::date AS fecha_maxima
FROM fact_ventas_sabiogo
UNION ALL
SELECT 'fact_costos_sabiogo' AS fact,
       COUNT(*) AS filas,
       MIN(fecha)::date AS fecha_minima,
       MAX(fecha)::date AS fecha_maxima
FROM fact_costos_sabiogo;

\echo '=== CARGAS API MAS RECIENTES ==='
SELECT tipo_carga,
       COUNT(*) AS cargas,
       MIN(fecha_carga) AS primera_carga,
       MAX(fecha_carga) AS ultima_carga,
       SUM(filas_insertadas) AS filas_insertadas,
       SUM(filas_duplicadas) AS filas_duplicadas,
       SUM(filas_error) AS filas_error
FROM logs_sabiogo_carga
WHERE archivo_nombre LIKE 'api_sync_%'
  AND fecha_carga >= timestamp '2026-01-01'
GROUP BY tipo_carga
ORDER BY tipo_carga;
