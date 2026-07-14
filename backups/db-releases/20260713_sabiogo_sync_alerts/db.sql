BEGIN;

DO $release_check$
DECLARE
    revision_count integer;
    valid_revision_count integer;
BEGIN
    SELECT COUNT(*) INTO revision_count FROM alembic_version;
    SELECT COUNT(*) INTO valid_revision_count
    FROM alembic_version
    WHERE version_num IN (
        '20260410_instrumento_portador_m2m',
        '20260713_sabiogo_sync_runs'
    );

    IF revision_count <> 1 OR valid_revision_count <> 1 THEN
        RAISE EXCEPTION 'Revision Alembic inesperada para release 20260713_sabiogo_sync_alerts';
    END IF;
END
$release_check$;

CREATE TABLE IF NOT EXISTS sabiogo_sync_runs (
    id SERIAL PRIMARY KEY,
    execution_id VARCHAR(36) NOT NULL,
    fecha_objetivo DATE NOT NULL,
    estado VARCHAR(20) NOT NULL,
    mensaje VARCHAR(500),
    filas_ventas INTEGER,
    filas_compras INTEGER,
    iniciada_en TIMESTAMP WITH TIME ZONE NOT NULL,
    finalizada_en TIMESTAMP WITH TIME ZONE,
    actualizada_en TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_sabiogo_sync_runs_execution_id UNIQUE (execution_id)
);

CREATE INDEX IF NOT EXISTS idx_sabiogo_sync_run_fecha_estado
    ON sabiogo_sync_runs (fecha_objetivo, estado);
CREATE INDEX IF NOT EXISTS ix_sabiogo_sync_runs_estado
    ON sabiogo_sync_runs (estado);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sabiogo_sync_runs_execution_id
    ON sabiogo_sync_runs (execution_id);
CREATE INDEX IF NOT EXISTS ix_sabiogo_sync_runs_fecha_objetivo
    ON sabiogo_sync_runs (fecha_objetivo);

UPDATE alembic_version
SET version_num = '20260713_sabiogo_sync_runs'
WHERE version_num = '20260410_instrumento_portador_m2m';

COMMIT;
