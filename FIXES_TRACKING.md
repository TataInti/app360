# Control de Correcciones UI/UX - App360
**Fecha inicio:** 24 enero 2026  
**Estado:** En progreso

---

## FASE 1: Rutas Web Faltantes ✅
**Tiempo estimado:** 45 min

### 1.1 Compras - Ruta `/compras`
- [x] Ya existía en `blueprints/compras.py` (línea 21-28)
- [x] Template `compras_panel.html` existe

### 1.2 RRHH - Rutas faltantes
- [x] Agregar ruta `/rrhh` → `rrhh_panel.html`
- [x] Agregar ruta `/rrhh/dotacion` → `rrhh_dotacion.html`
- [x] Agregar ruta `/rrhh/empleados` → `rrhh_empleados.html`

### 1.3 Gastos - Ruta `/gastos`
- [x] Crear template `gastos_panel.html`
- [x] Agregar ruta en `blueprints/gastos.py`

---

## FASE 2: Limpiar Menú de Navegación ⏳
**Tiempo estimado:** 30 min

### 2.1 Cambios en `templates/base.html`
- [ ] Eliminar "Ausentismo" duplicado
- [ ] Eliminar "Asistencia" (redundante)
- [ ] Eliminar "Clima" 
- [ ] Mover "Objetivos" a sección Comercial

### 2.2 Estructura final esperada
```
RRHH:
├── Panel RRHH
├── Empleados
├── Dotación
├── Adelantos
└── Ausentismo

Comercial:
├── Dashboard Comercial
├── Ventas
├── Leads/CRM
└── Objetivos de Venta
```

---

## FASE 3: Tesorería - Funcionalidad ⏳
**Tiempo estimado:** 1 hora

### 3.1 Botones en `tesoreria_panel.html`
- [ ] Modal "Nuevo Arqueo" funcional
- [ ] Modal "Registrar Movimiento" funcional
- [ ] Conectar con API endpoints

### 3.2 Vistas diferenciadas
- [ ] Crear `tesoreria_movimientos.html` (filtrado a movimientos)
- [ ] Crear `tesoreria_arqueos.html` (filtrado a arqueos)
- [ ] Actualizar rutas en `blueprints/tesoreria.py`

---

## FASE 4: BI - Tabs Faltantes ⏳
**Tiempo estimado:** 30 min

### 4.1 Corregir `bi_dashboard.html`
- [ ] Verificar HTML de `#tab-gastos`
- [ ] Verificar HTML de `#tab-leads`
- [ ] Corregir JavaScript de tabs
- [ ] Probar visualización

---

## FASE 5: Objetivos de Venta - Refactoring ⏳
**Tiempo estimado:** 1.5 horas

### 5.1 Mover a módulo Comercial
- [ ] Renombrar `rrhh_objetivos.html` → `objetivos_ventas.html`
- [ ] Agregar ruta en `blueprints/comercial.py` o `ventas.py`
- [ ] Adaptar lógica a vendedores

### 5.2 Funcionalidad
- [ ] Objetivos por vendedor
- [ ] Cuota mensual
- [ ] % cumplimiento
- [ ] Ranking vendedores

---

## FASE 6: UX Menú - Scroll ⏳
**Tiempo estimado:** 20 min

### 6.1 Corregir en `base.html`
- [ ] Agregar `event.preventDefault()` donde corresponda
- [ ] Mantener visible ítem seleccionado
- [ ] Guardar estado scroll en localStorage

---

## FASE 7: Limpieza Final ⏳
**Tiempo estimado:** 15 min

### 7.1 Eliminar código muerto
- [ ] Eliminar rutas `/rrhh/clima`
- [ ] Eliminar rutas `/rrhh/asistencia`

### 7.2 Actualizar `security.py`
- [ ] ACCESS_MAP: eliminar `clima`, `asistencia`
- [ ] MODULE_ROUTES: agregar `compras`, `gastos`
- [ ] MODULE_ROUTES: mover `objetivos` a comercial

---

## Progreso General

| Fase | Estado | Completado |
|------|--------|------------|
| Fase 1 | ✅ Completada | 100% |
| Fase 2 | ⏳ Pendiente | 0% |
| Fase 3 | ⏳ Pendiente | 0% |
| Fase 4 | ⏳ Pendiente | 0% |
| Fase 5 | ⏳ Pendiente | 0% |
| Fase 6 | ⏳ Pendiente | 0% |
| Fase 7 | ⏳ Pendiente | 0% |

---

## Commits Realizados
| Fecha | Commit | Descripción |
|-------|--------|-------------|
| - | - | - |

---

## Notas
- Orden de ejecución: 1 → 2 → 3 → 4 → 6 → 7 → 5
- Fase 5 es refactoring complejo, puede dejarse para el final
