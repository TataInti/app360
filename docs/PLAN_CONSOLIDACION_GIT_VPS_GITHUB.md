# Plan de Consolidación Git — Local / VPS / GitHub

Última actualización: 2026-03-04
Fuente de verdad definida: **VPS productivo**
Objetivo final: `main` en GitHub debe reflejar exactamente la versión definitiva desplegable/recuperable.

---

## 1) Objetivo operativo

Eliminar drift entre:
- repositorio local,
- repositorio en VPS (`/var/www/app360`),
- repositorio remoto GitHub (`origin/main`).

Al final del proceso, los 3 deben converger a un mismo commit SHA.

---

## 2) Reglas de seguridad

1. No forzar push sin backup y sin comparar SHAs.
2. No ejecutar scripts de DB destructivos durante consolidación de código.
3. Congelar cambios funcionales mientras se reconcilia estado Git.
4. Registrar cada decisión de reconciliación (qué se conserva y por qué).

---

## 3) Prerrequisitos

- SSH directo al VPS operativo.
- Permisos de lectura/escritura en GitHub remoto.
- Worktree local con herramientas git disponibles.
- Confirmación de rama objetivo: `main`.

---

## 4) Fase 1 — Diagnóstico de divergencia

## 4.1 Local

```bash
git fetch --all --prune
git status --short
git remote -v
git branch --show-current
git rev-parse HEAD
git rev-list --left-right --count origin/main...main
git log --oneline --decorate -n 30
```

## 4.2 VPS

```bash
ssh <user>@<host> "cd /var/www/app360 && git remote -v && git branch --show-current && git rev-parse HEAD && git status --short"
ssh <user>@<host> "cd /var/www/app360 && git fetch --all --prune && git rev-list --left-right --count origin/main...HEAD"
```

## 4.3 GitHub

Validar en web/API:
- rama default = `main`
- último commit SHA de `main`
- PRs abiertos que puedan introducir cambios pendientes

Resultado esperado:
- matriz de estado: `LOCAL_SHA`, `VPS_SHA`, `GITHUB_SHA`, con flags de dirty tree.

---

## 5) Fase 2 — Congelación y respaldo

1. Congelar cambios nuevos hasta cerrar consolidación.
2. En local, exportar parche de trabajo no reconciliado (si existe):

```bash
git diff > /tmp/app360_pre_consolidacion.patch
```

3. En VPS, verificar que no haya cambios locales sin commit (`git status --short`).

Si VPS tiene cambios sin commit:
- revisar archivo por archivo,
- commitear en VPS o extraer patch antes de continuar.

---

## 6) Fase 3 — Alineación con VPS como fuente de verdad

Escenarios:

### Escenario A: VPS ya coincide con `origin/main`

- Alinear local a `origin/main` (rebase/fast-forward).
- Resolver y commitear solo cambios locales aprobados.

### Escenario B: VPS está adelantado respecto a GitHub

1. Extraer cambios faltantes en local (desde remote/patch/cherry-pick).
2. Crear commit(s) de reconciliación en local `main`.
3. Push a `origin/main`.

### Escenario C: GitHub adelantado pero VPS es la verdad operativa

1. Revisar commits en GitHub no desplegados.
2. Decidir explícitamente:
   - integrar en VPS y luego consolidar, o
   - revertir en GitHub mediante commit de rollback (evitar force push).

Regla recomendada:
- Preferir commits de reconciliación/revert antes que `push --force`.

---

## 7) Fase 4 — Verificación de convergencia

Comprobar SHAs iguales:

```bash
# Local
git rev-parse HEAD

# GitHub (referencia local remota)
git rev-parse origin/main

# VPS
ssh <user>@<host> "cd /var/www/app360 && git rev-parse HEAD"
```

Esperado: los 3 valores son idénticos.

Además:

```bash
git rev-list --left-right --count origin/main...main
ssh <user>@<host> "cd /var/www/app360 && git rev-list --left-right --count origin/main...HEAD"
```

Esperado: `0 0` en ambos casos.

---

## 8) Fase 5 — Validación runtime en VPS

```bash
ssh <user>@<host> "sudo systemctl restart app360 && sudo systemctl status app360 --no-pager"
ssh <user>@<host> "curl -fsS http://127.0.0.1:5000/api/health"
```

Opcional seguro (tests aislados):

```bash
ssh <user>@<host> "cd /var/www/app360 && sudo -u www-data bash scripts/deploy.sh"
```

Nota: `deploy.sh` corre tests en SQLite temporal y no debería tocar datos productivos por sí mismo.

---

## 9) Evidencia de cierre (obligatoria)

Registrar en ticket/acta:
- SHA definitivo consolidado.
- fecha/hora de consolidación.
- resultado de health check.
- confirmación de `0 0` en divergencia local/VPS contra `origin/main`.
- lista de decisiones tomadas (reconciliaciones/reverts).

---

## 10) Plan de rollback

Si algo falla luego de consolidar:
1. checkout al SHA estable previo (local/VPS).
2. reinicio de servicio en VPS.
3. si fue cambio de DB, aplicar rollback vía release versionada o restore planificado.

Comando base de rollback de código (VPS):

```bash
ssh <user>@<host> "cd /var/www/app360 && git checkout <sha_estable> && sudo systemctl restart app360"
```

---

## 11) No hacer

- No usar `git push --force` en `main` salvo incidente crítico documentado.
- No mezclar limpieza técnica con cambios funcionales de negocio durante consolidación.
- No asumir que GitHub está bien sin comparar SHAs con VPS.

---

## 12) Ejecución real (2026-03-04)

Resultado del diagnóstico ejecutado:

- `LOCAL_SHA`: `d0bc297aaad47fe5aee330a7a6cca1ac4f902413`
- `GITHUB_MAIN_SHA` (ls-remote): `d0bc297aaad47fe5aee330a7a6cca1ac4f902413`
- `VPS_SHA` (`/var/www/app360`): `d0bc297aaad47fe5aee330a7a6cca1ac4f902413`

Divergencia:

- Local vs `origin/main`: `0 0`
- VPS vs `origin/main`: `0 0`

Conclusión:

- La versión de código ya está consolidada entre local, VPS y GitHub en `main`.
- No se detectaron PRs abiertos en GitHub al momento del chequeo.

Hallazgo operativo en VPS:

- Existen 2 archivos `untracked` en `/var/www/app360`:
   - `backup_antes_migracion_20260207_200948.sql` (0 bytes)
   - `qlalchemy import create_engine, inspect` (archivo residual)

Acción recomendada:

- Eliminar/archivar estos `untracked` para mantener el árbol limpio del servidor y evitar confusión en futuros mantenimientos.

Actualización de cierre:

- Los archivos `untracked` fueron eliminados en VPS.
- Verificación posterior:
   - `git status --short` (VPS) = limpio
   - `VPS_HEAD = d0bc297aaad47fe5aee330a7a6cca1ac4f902413`
   - `origin/main...HEAD = 0 0`
