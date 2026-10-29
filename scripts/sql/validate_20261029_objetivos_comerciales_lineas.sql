DO $$
DECLARE
    current_revision text;
    missing_columns integer;
BEGIN
    IF (SELECT count(*) FROM alembic_version) <> 1 THEN
        RAISE EXCEPTION 'alembic_version debe tener una sola fila';
    END IF;

    SELECT version_num INTO current_revision FROM alembic_version;
    IF current_revision <> '20261029_objetivos_comerciales_lineas' THEN
        RAISE EXCEPTION 'revision inesperada: %', current_revision;
    END IF;

    IF to_regclass('public.comercial_objetivos') IS NULL THEN
        RAISE EXCEPTION 'Falta comercial_objetivos';
    END IF;

    SELECT count(*) INTO missing_columns
    FROM (VALUES
        ('dimension_tipo'),
        ('dimension_valor'),
        ('meta_importe'),
        ('meta_cajas'),
        ('meta_kilos')
    ) AS expected(column_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'comercial_objetivos'
          AND column_name = expected.column_name
    );
    IF missing_columns <> 0 THEN
        RAISE EXCEPTION 'Faltan columnas nuevas de objetivos: %', missing_columns;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM comercial_objetivos
        WHERE dimension_tipo NOT IN ('empresa', 'rubro', 'subrubro', 'marca', 'producto')
           OR trim(dimension_valor) = ''
           OR meta_importe < 0
           OR meta_cajas < 0
           OR meta_kilos < 0
           OR (meta_importe = 0 AND meta_cajas = 0 AND meta_kilos = 0)
    ) THEN
        RAISE EXCEPTION 'Hay líneas comerciales sin slice o sin meta positiva';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM comercial_objetivos
        WHERE medida IS NOT NULL
          AND (
              dimension_tipo <> 'empresa'
              OR dimension_valor <> empresa
              OR (medida = 'importe' AND (meta_importe <> meta OR meta_cajas <> 0 OR meta_kilos <> 0))
              OR (medida = 'cajas' AND (meta_cajas <> meta OR meta_importe <> 0 OR meta_kilos <> 0))
              OR (medida = 'kilos' AND (meta_kilos <> meta OR meta_importe <> 0 OR meta_cajas <> 0))
          )
    ) THEN
        RAISE EXCEPTION 'Hay objetivos legacy sin convertir a línea empresa+medida';
    END IF;
END $$;
