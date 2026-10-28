\set ON_ERROR_STOP on

DO $$
BEGIN
    IF (SELECT count(*) FROM alembic_version) <> 1 THEN
        RAISE EXCEPTION 'alembic_version debe tener exactamente una fila';
    END IF;

    IF (SELECT version_num FROM alembic_version) <> '20261021_comercial_cliente_criterio' THEN
        RAISE EXCEPTION 'La revision Alembic no es 20261021_comercial_cliente_criterio';
    END IF;

    IF to_regclass('public.comercial_vendedores') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_vendedores';
    END IF;
    IF to_regclass('public.comercial_vendedor_aliases') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_vendedor_aliases';
    END IF;
    IF to_regclass('public.comercial_objetivos') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_objetivos';
    END IF;
    IF to_regclass('public.comercial_objetivo_vinculos') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_objetivo_vinculos';
    END IF;
    IF to_regclass('public.comercial_cliente_criterio') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_cliente_criterio';
    END IF;
    IF to_regclass('public.ix_comercial_cliente_criterio_criterio') IS NULL THEN
        RAISE EXCEPTION 'Falta ix_comercial_cliente_criterio_criterio';
    END IF;

    IF to_regclass('public.goals') IS NULL OR to_regclass('public.movimientos_caja') IS NULL THEN
        RAISE EXCEPTION 'Falta una tabla preexistente requerida';
    END IF;
END
$$;

SELECT
    (SELECT version_num FROM alembic_version) AS revision,
    (SELECT count(*) FROM comercial_vendedores) AS vendedores,
    (SELECT count(*) FROM comercial_vendedor_aliases) AS alias_vendedores,
    (SELECT count(*) FROM comercial_objetivos) AS objetivos,
    (SELECT count(*) FROM comercial_objetivo_vinculos) AS vinculos_objetivos,
    (SELECT count(*) FROM comercial_cliente_criterio) AS criterios_clientes,
    (SELECT count(*) FROM goals) AS objetivos_legacy,
    (SELECT count(*) FROM movimientos_caja) AS movimientos;
