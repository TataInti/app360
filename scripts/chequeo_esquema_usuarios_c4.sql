-- Chequeo de esquema de administración de usuarios (C4). Solo lectura.
-- Uso (despliegue, después de «flask db upgrade» y antes de reiniciar gunicorn):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/chequeo_esquema_usuarios_c4.sql
-- Resultado esperado: una fila con todas las columnas booleanas en «t». Si alguna es «f», no reiniciar la app
-- nueva: falta la migración 20261120_usuarios_c4_auditoria_bloqueo o quedó a medias.
-- La columna alembic_una_fila solo exige que alembic_version tenga exactamente 1 fila; no compara la
-- revisión porque la cabeza puede ser posterior a C4 (el orden de la cadena no se deduce del texto).
-- revision_actual_informativa muestra la revisión vigente a modo de dato (no es una comprobación).
-- Que C4 esté aplicado lo prueban las demás columnas (tabla, columnas e índice de C4).
-- Verificación complementaria tras el arranque: GET /api/health debe responder 200 (si falta algo, 503
-- con «faltantes» en el cuerpo).
SELECT
    (SELECT count(*) FROM alembic_version) = 1 AS alembic_una_fila,
    (SELECT string_agg(version_num, ',') FROM alembic_version) AS revision_actual_informativa,
    to_regclass('public.user_login_attempts') IS NOT NULL AS tabla_pares,
    EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'failed_login_count') AS usuarios_contador,
    EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'failed_login_window_start') AS usuarios_ventana,
    EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'locked_until') AS usuarios_bloqueo,
    EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'user_audit_log' AND column_name = 'clave_agrupacion') AS auditoria_agrupacion,
    EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'user_audit_log' AND column_name = 'repeticiones') AS auditoria_repeticiones,
    EXISTS (SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = 'ix_user_audit_log_agrupacion') AS indice_agrupacion;
