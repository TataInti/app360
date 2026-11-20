-- Chequeo de esquema de administración de usuarios (C4). Solo lectura.
-- Uso (despliegue, después de «flask db upgrade» y antes de reiniciar gunicorn):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/chequeo_esquema_usuarios_c4.sql
-- Resultado esperado: una fila con todas las columnas en «t». Si alguna es «f», no reiniciar la app
-- nueva: falta la migración 20261120_usuarios_c4_auditoria_bloqueo o quedó a medias.
-- Verificación complementaria tras el arranque: GET /api/health debe responder 200 (si falta algo, 503
-- con «faltantes» en el cuerpo).
SELECT
    (SELECT version_num FROM alembic_version) = '20261120_usuarios_c4_auditoria_bloqueo' AS revision_c4,
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
