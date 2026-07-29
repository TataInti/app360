\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'categoria_gasto'
          AND column_name = 'naturaleza'
    ) THEN
        RAISE EXCEPTION 'Falta categoria_gasto.naturaleza';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'categoria_gasto'
          AND column_name = 'incluye_resultado'
    ) THEN
        RAISE EXCEPTION 'Falta categoria_gasto.incluye_resultado';
    END IF;

    IF to_regclass('public.categoria_movimiento_audit') IS NULL THEN
        RAISE EXCEPTION 'Falta categoria_movimiento_audit';
    END IF;

    IF to_regclass('public.web_checkins') IS NOT NULL THEN
        RAISE EXCEPTION 'La release introdujo web_checkins fuera de alcance';
    END IF;

    IF (
        SELECT count(*)
        FROM categoria_gasto
        WHERE upper(trim(nombre)) = 'EFECTIVO IVA'
          AND naturaleza = 'ingreso'
          AND incluye_resultado IS TRUE
    ) <> 1 THEN
        RAISE EXCEPTION 'EFECTIVO IVA no quedo como ingreso incluido';
    END IF;

    IF (
        SELECT count(*)
        FROM categoria_gasto
        WHERE upper(trim(nombre)) = 'SUELDOS'
          AND naturaleza = 'egreso'
          AND incluye_resultado IS TRUE
    ) <> 1 THEN
        RAISE EXCEPTION 'SUELDOS no quedo como egreso incluido';
    END IF;
END
$$;

SELECT
    (SELECT version_num FROM alembic_version) AS revision,
    (SELECT count(*) FROM movimientos_caja) AS movimientos,
    (SELECT count(*) FROM categoria_gasto) AS conceptos,
    (
        SELECT count(*)
        FROM categoria_gasto
        WHERE naturaleza IS NULL
    ) AS conceptos_pendientes;
