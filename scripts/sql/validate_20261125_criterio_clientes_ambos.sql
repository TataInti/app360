\set ON_ERROR_STOP on

DO $$
BEGIN
    IF (SELECT count(*) FROM alembic_version) <> 1 THEN
        RAISE EXCEPTION 'alembic_version debe tener exactamente una fila';
    END IF;
    IF (SELECT version_num FROM alembic_version) <> '20261125_criterio_clientes_ambos' THEN
        RAISE EXCEPTION 'La revision Alembic no es 20261125_criterio_clientes_ambos';
    END IF;
    IF to_regclass('public.comercial_cliente_criterio') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_cliente_criterio';
    END IF;
    IF (SELECT character_maximum_length FROM information_schema.columns
        WHERE table_name = 'comercial_cliente_criterio' AND column_name = 'criterio') < 5 THEN
        RAISE EXCEPTION 'La columna criterio no admite AMBOS';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_comercial_cliente_criterio_tipo'
          AND pg_get_constraintdef(oid) LIKE '%AMBOS%'
    ) THEN
        RAISE EXCEPTION 'El CHECK del criterio no admite AMBOS';
    END IF;
END
$$;

SELECT
    (SELECT version_num FROM alembic_version) AS revision,
    (SELECT count(*) FROM comercial_cliente_criterio) AS criterios_clientes,
    (SELECT count(*) FROM comercial_cliente_criterio WHERE criterio = 'AMBOS') AS ambos;
