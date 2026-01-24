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

## FASE 2: Limpiar Menú de Navegación ✅
**Tiempo estimado:** 30 min

### 2.1 Cambios en `templates/base.html`
- [x] Eliminar "Ausentismo" duplicado
- [x] Eliminar "Asistencia" (redundante)
- [x] Eliminar "Clima" 
- [x] Mover "Objetivos" a sección Comercial

### 2.2 Estructura final implementada
```
RRHH:
├── Panel RRHH
├── Empleados
├── Dotación
├── Adelantos
└── Ausentismo

Comercial:
├── Leads
├── Nuevo Lead
├── Ventas
├── Nueva Venta
├── Campañas
└── Objetivos de Venta  ← (movido desde RRHH)
```

---

## FASE 3: Tesorería - Funcionalidad ✅
**Tiempo estimado:** 1 hora

### 3.1 Botones en `tesoreria_panel.html`
- [x] Modal "Nuevo Arqueo" funcional
- [x] Modal "Registrar Movimiento" funcional
- [x] Conectar con API endpoints

### 3.2 Vistas diferenciadas
- [x] Crear `tesoreria_movimientos.html` (filtrado a movimientos)
- [x] Crear `tesoreria_arqueos.html` (filtrado a arqueos)
- [x] Actualizar rutas en `blueprints/tesoreria.py`

---

## FASE 4: BI - Tabs Faltantes ✅
**Tiempo estimado:** 30 min

### 4.1 Corregir `bi_dashboard.html`
- [x] Verificar HTML de `#tab-gastos` - OK
- [x] Verificar HTML de `#tab-leads` - OK
- [x] Problema identificado: Faltaba Bootstrap JS en base.html
- [x] Agregado: `bootstrap.bundle.min.js` en base.html

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

## FASE 6: UX Menú - Scroll ✅
**Tiempo estimado:** 20 min

### 6.1 Corregir en `base.html`
- [x] Guardar posición de scroll del sidebar en localStorage
- [x] Restaurar posición de scroll al cargar página
- [x] Mantener visible el área del menú donde se hizo clic

---

## FASE 7: Limpieza Final ✅
**Tiempo estimado:** 15 min

### 7.1 Eliminar código muerto
- [x] Limpiar links viejos en rrhh_panel.html (asistencia, clima, objetivos)
- [x] Rutas API se mantienen para uso futuro

### 7.2 Actualizar `security.py`
- [x] ACCESS_MAP: eliminar `clima`, `asistencia`, agregar `dotacion`, `empleados`
- [x] ACCESS_MAP: mover `objetivos` a rol sales
- [x] MODULE_ROUTES: agregar `empleados`, `dotacion`, limpiar rutas muertas

---

## Progreso General

| Fase | Estado | Completado |
|------|--------|------------|
| Fase 1 | ✅ Completada | 100% |
| Fase 2 | ✅ Completada | 100% |
| Fase 3 | ✅ Completada | 100% |
| Fase 4 | ✅ Completada | 100% |
| Fase 5 | ⏳ Pendiente | 0% |
| Fase 6 | ✅ Completada | 100% |
| Fase 7 | ✅ Completada | 100% |

---

## Commits Realizados
| Fecha | Commit | Descripción |
|-------|--------|-------------|
| - | - | - |

---

## Notas
- Orden de ejecución: 1 → 2 → 3 → 4 → 6 → 7 → 5
- Fase 5 es refactoring complejo, puede dejarse para el final
