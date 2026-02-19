# Prioridad operativa: Local First + Control de cambios DB

Fecha de vigencia: 2026-02-12
Estado: ACTIVO (prioridad máxima)

## Objetivo

Desde este punto, el desarrollo se hace primero en entorno local. La base local es la fuente de trabajo para cambios de esquema y datos, y todo cambio debe quedar auditado en GitHub antes de replicarse en VPS.

## Reglas obligatorias

1. Todo cambio de base de datos se hace primero en local.
2. No se aplican cambios manuales directos en VPS sin pasar por GitHub.
3. Cada cambio de DB debe tener:
   - Migración/versionado de esquema (Alembic o SQL versionado).
   - Release de DB versionada para replicación (archivo SQL + checksum).
4. La interfaz se valida localmente antes de publicar.
5. El despliegue a VPS usa release versionada desde el repositorio.

## Flujo estándar (obligatorio)

### 1) Trabajar local (backend + frontend)

Backend:

```bash
source /Users/intipalaciofernandez/venvs/app360/bin/activate
python app.py
```

Frontend (validación visual local):

```bash
cd frontend
npm install
npm run dev
```

BI / Inteligencia (React) consume la API del backend. Para entorno local:

- Backend corre típicamente en `http://127.0.0.1:5001`
- Frontend en `http://localhost:5173`

Nota: si se usa extensión Live Server para archivos estáticos, mantener como referencia principal la app React en `npm run dev`.

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

### 3) Generar release de base para GitHub

```bash
bash scripts/create_local_db_release.sh
```

Salida esperada:

- `backups/db-releases/<release_tag>/db.sql`
- `backups/db-releases/<release_tag>/db.sql.sha256`
- `backups/db-releases/<release_tag>/release_meta.txt`

### 4) Control de cambios en GitHub

Commit mínimo recomendado:

- Código backend/frontend.
- Migraciones SQL/Alembic.
- Carpeta de release DB (`backups/db-releases/<release_tag>`).
- Actualización de documentación.

Ejemplo:

```bash
git add .
git commit -m "db: cambios locales + release <release_tag>"
git push origin <branch>
```

### 5) Replicar en VPS desde release versionada

```bash
bash scripts/apply_db_release_to_vps.sh <release_tag>
```

Este script valida SHA256 y aplica el SQL sobre la `DATABASE_URL` del VPS tomada desde `/var/www/app360/.env`.

## Checklist previo a merge/deploy

- [ ] Funcionalidad validada en local (UI + backend).
- [ ] Migraciones aplican sin error en local.
- [ ] Release DB generada y versionada en Git.
- [ ] Documentación actualizada.
- [ ] Cambios subidos a GitHub.

## Alcance de prioridad

Esta política reemplaza cualquier flujo ad-hoc previo para cambios de base de datos.

Si hay urgencia productiva, primero se documenta excepción en PR/issue y luego se regulariza el flujo con release versionada.
