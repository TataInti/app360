# Plan de Limpieza Profunda (Intermedia) — App360

Última actualización: 2026-03-04
Estado: Propuesto para ejecución por fases

---

## 1) Objetivo

Reducir ruido técnico y riesgo operativo eliminando artefactos no necesarios y revisando legacy con evidencia, sin comprometer despliegue, migraciones ni recuperación.

Alcance elegido: **Intermedia**
- Sí: basura local regenerable + revisión documentada de candidatos legacy.
- No: refactors estructurales agresivos ni reescrituras funcionales.

---

## 2) Principios de seguridad

1. **No borrar primero, clasificar primero**.
2. Todo candidato debe pasar por evidencia de no uso (búsqueda de referencias + impacto runtime/deploy).
3. En caso de duda: **conservar** y marcar como “pendiente de deprecación”.
4. Ejecutar limpieza en rama de trabajo o commit atómico reversible.

---

## 3) Fases de ejecución

## Fase A — Inventario y baseline

Checklist:
- [ ] `git fetch --all --prune`
- [ ] `git status --short`
- [ ] snapshot de árbol actual (`find`/listados)
- [ ] registrar baseline en issue/nota interna

Resultado esperado:
- Lista clasificada de candidatos por categoría con decisión preliminar.

## Fase B — Limpieza segura (eliminación directa)

### B.1 Candidatos de borrado directo (regenerables/locales)

- `__pycache__/` (raíz y subcarpetas)
- `.pytest_cache/`
- `frontend/dist/`
- `frontend/node_modules/`
- `logs/` (contenido local no histórico requerido)
- `backups/db-sync/` (dumps temporales locales)
- `instance/` (DBs locales: validar que no se necesiten)
- `.DS_Store`
- `.env.local_backup*` y `.env.*_backup*` temporales

Condición para ejecutar:
- Deben estar ignorados por `.gitignore` o ser inequívocamente locales.

### B.2 Validación post-Fase B

- [ ] `git status --short` no debe mostrar borrados críticos inesperados
- [ ] backend levanta (`python app.py` o script local)
- [ ] frontend levanta (`npm run dev`)

## Fase C — Revisión legacy/documentación/scripts

### C.1 Candidatos a revisar (NO borrar automáticamente)

- `api/v1/` (estructura vacía)
- `docs/Plan integracion.md` (formato bitácora)
- `frontend/README.md` (template genérico)
- Scripts históricos de migración/arranque:
  - `scripts/migrate_to_postgres.py`
  - `scripts/migrate_to_postgres.sh`
  - `scripts/run_app.sh`

### C.2 Criterio de decisión

Para cada archivo/carpeta:
1. ¿Tiene referencias en docs, scripts de deploy o systemd/nginx?
2. ¿Se usa en flujo operativo actual?
3. ¿Existe reemplazo formal?

Decisiones posibles:
- **Mantener** (en uso)
- **Deprecar** (documentar como legado)
- **Archivar** (mover a `docs/_legacy/` o equivalente)
- **Eliminar** (sin referencias ni uso)

## Fase D — Cierre

- [ ] Commit de limpieza con mensaje claro
- [ ] Actualización de `docs/MANUAL_DEVELOPER.md` si cambió operación
- [ ] Registro de lo eliminado y justificación

---

## 4) Comandos de apoyo (referencia)

Detectar cachés/artefactos:

```bash
find . -type d -name "__pycache__"
find . -name ".DS_Store"
```

Detectar referencias antes de eliminar candidatos legacy:

```bash
grep -R "migrate_to_postgres\|run_app.sh\|Plan integracion" -n .
```

---

## 5) Riesgos y mitigaciones

- Riesgo: borrar datos locales aún útiles en `instance/`.
  - Mitigación: backup previo o confirmación explícita antes de borrar.
- Riesgo: eliminar scripts usados por operación informal del equipo.
  - Mitigación: validación por referencias + aprobación funcional.
- Riesgo: ruido por archivos ignorados ya existentes.
  - Mitigación: consolidar `.gitignore` y ejecutar limpieza periódica.

---

## 6) Entregables de la limpieza

1. Repo sin basura local ni artefactos regenerables.
2. Lista de legacy clasificada con decisión trazable.
3. Documentación operativa actualizada.
