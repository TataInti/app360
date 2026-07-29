# Prioridad operativa: Local First + Control de cambios DB

Estado: ACTIVO (prioridad máxima)

## Objetivo

El desarrollo se hace primero en entorno local. La base local es la fuente de trabajo para cambios de esquema y datos, y todo cambio debe quedar auditado en GitHub antes de replicarse en VPS.

## Reglas obligatorias

1. Todo cambio de base de datos se hace primero en local.
2. No se aplican cambios manuales directos en VPS sin pasar por GitHub.
3. Cada cambio de DB debe tener:
   - Migración Alembic forward-only.
   - Validación de revisión inicial/final y controles de aceptación.
4. La interfaz se valida localmente antes de publicar.
5. El despliegue a VPS usa exclusivamente código y migraciones versionadas.

## Flujo estándar (obligatorio)

### 1) Trabajar local (backend)

Backend:

```bash
cd <repo_root>
source .venv/bin/activate
bash scripts/dev_backend.sh
```

Validación visual local:

```bash
open http://127.0.0.1:5001
```

Para entorno local:

- Backend corre típicamente en `http://127.0.0.1:5001`
- La interfaz actual se sirve desde Flask/Jinja en esa misma URL

Nota: este repositorio no incluye hoy una SPA React/Vite separada; si se reincorpora, la documentación de arranque debe actualizarse en el mismo cambio.

### 2) Aplicar cambios de DB localmente

- Ejecutar migraciones.
- Validar funcionalidad de pantallas afectadas contra la DB local.
- Ejecutar pruebas necesarias.

Si después de un restore/sync la app no “ve” tablas (errores tipo `relation ... does not exist`), suele ser un tema de privilegios del rol de la app. Reaplicar permisos:

```bash
bash scripts/fix_local_db_privileges.sh
```

Este script también corrige ownership de vistas materializadas SabioGo. Si al refrescar aparece `must be owner of materialized view ...`, volver a ejecutarlo.

Si en SabioGo “no se ve nada” aun con datos cargados, revisar estados de staging: las facts/BI filtran por `estado='procesado'`. El refresh de facts promueve `cargado/pendiente` a `procesado`, pero si venís de un dump viejo puede quedar desalineado.

### 3) Validar el camino de migración

```bash
flask db heads
flask db current
flask db upgrade
```

Importante:

- Debe existir una única cabecera Alembic.
- La migración se prueba contra una copia aislada del esquema/datos productivos.
- Los backups operativos o temporales nunca quedan dentro del working tree.
- `create_local_db_release.sh` está bloqueado: un dump `--clean` no es una migración.

### 4) Control de cambios en GitHub

Commit mínimo recomendado:

- Código backend/frontend.
- Migraciones SQL/Alembic.
- SQL de validación asociado, si corresponde.
- Actualización de documentación.

Ejemplo:

```bash
git add .
git commit -m "db: cambios locales + release <release_tag>"
git push origin <branch>
```

### 5) Replicar en VPS con migración segura

```bash
EXPECTED_GIT_SHA=<sha_completo> \
PROD_SSH_HOST=<host> \
MAINTENANCE_CONFIRMED=true \
bash scripts/apply_db_migrations_to_vps.sh \
  <revision_actual> \
  <revision_objetivo> \
  <sql_de_validacion>
```

El flujo:

1. exige checkout limpio y commit exacto;
2. exige confirmación de que las escrituras están pausadas;
3. valida una sola revisión actual y una sola cabecera objetivo;
4. crea backup custom + SHA256;
5. restaura el backup en una base temporal;
6. aplica Alembic forward-only;
7. ejecuta controles SQL y conserva el manifiesto.

No reinicia Gunicorn.

## Checklist previo a merge/deploy

- [ ] Funcionalidad validada en local (UI + backend).
- [ ] Migraciones aplican sin error en local.
- [ ] Upgrade validado desde la revisión real de producción.
- [ ] SQL de aceptación validado.
- [ ] Documentación actualizada.
- [ ] Cambios subidos a GitHub.

## Alcance de prioridad

Esta política reemplaza cualquier flujo ad-hoc previo para cambios de base de datos.

Si hay urgencia productiva, primero se documenta excepción en PR/issue y luego se regulariza el flujo con release versionada.
