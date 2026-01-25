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

## FASE 5: Objetivos de Venta - Refactoring ✅
**Tiempo estimado:** 1.5 horas

### 5.1 Mover a módulo Comercial
- [x] Crear `objetivos_ventas.html` con nuevo diseño
- [x] Agregar ruta web `/comercial/objetivos` en `blueprints/comercial.py`
- [x] Agregar 6 endpoints API en `blueprints/comercial.py`:
  - GET/POST `/api/comercial/objetivos`
  - PUT/DELETE `/api/comercial/objetivos/<id>`
  - GET `/api/comercial/vendedores`
  - GET `/api/comercial/ranking`
- [x] Actualizar enlace menú en `base.html`
- [x] Actualizar MODULE_ROUTES en `security.py`

### 5.2 Funcionalidad
- [x] Objetivos por vendedor (employee_id → Goal)
- [x] Filtro por periodo (mes/año)
- [x] % cumplimiento con progress bars
- [x] Ranking vendedores con medallas (🥇🥈🥉)
- [x] KPIs: Activos, Cumplidos, En Progreso, Promedio
- [x] CRUD completo con modales

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
| Fase 5 | ✅ Completada | 100% |
| Fase 6 | ✅ Completada | 100% |
| Fase 7 | ✅ Completada | 100% |

**🎉 TODAS LAS FASES COMPLETADAS 🎉**

---

# ═══════════════════════════════════════════════════════════════════════
# SPRINT 2 - Administración de Variables por Módulo
# ═══════════════════════════════════════════════════════════════════════

**Fecha inicio:** 24 enero 2026  
**Estado:** En progreso

## Resumen de Correcciones y Nuevas Funcionalidades

### Correcciones
- Panel de Compras no visible (verificar link en menú)

### Nuevas Funcionalidades
- Menú de administración de catálogos/variables por módulo
- Solo accesible para usuarios con rol `admin`
- Excepto módulo BI (solo visualización)

---

## FASE 8: Verificar Panel de Compras ✅
**Tiempo estimado:** 15 min

### 8.1 Diagnóstico
- [x] Error: modelo `PurchaseOrder` no tenía campo `created_at`
- [x] Modelo corregido: agregado `created_at`, `supplier`, relaciones `items` y `receipts`
- [x] Modelo `PurchaseReceipt` corregido: `order_id` en lugar de `purchase_order_id`
- [x] Migración aplicada

### 8.2 Verificación
- [x] Panel de compras funciona correctamente (status 200)
- [x] Template renderiza sin errores

---

## FASE 9-10: Blueprint Admin + APIs ✅
**Tiempo estimado:** 2 horas

### 9.1 Arquitectura Implementada
- [x] Blueprint `admin.py` creado con rutas `/admin/<modulo>`
- [x] Decorador `@admin_required` verificando rol admin/manager/gerente
- [x] Estructura API REST genérica para CRUD de catálogos

### 9.2 Catálogos Implementados

| Módulo | Catálogos | Estado |
|--------|-----------|--------|
| **Gastos** | Categorías, Proveedores | ✅ |
| **Tesorería** | Instrumentos de Pago | ✅ |
| **RRHH** | Turnos | ✅ |
| **Stock/Core** | Ubicaciones, Productos, Unidades | ✅ |

### 9.3 APIs CRUD Genéricas
- [x] `GET /api/admin/<modulo>/<entidad>` → Listar
- [x] `POST /api/admin/<modulo>/<entidad>` → Crear
- [x] `PUT /api/admin/<modulo>/<entidad>/<id>` → Editar
- [x] `DELETE /api/admin/<modulo>/<entidad>/<id>` → Eliminar
- [x] `PATCH /api/admin/<modulo>/<entidad>/<id>/toggle` → Activar/Desactivar

---

## FASE 11: Templates de Administración ✅
**Tiempo estimado:** 2 horas

### 11.1 Templates Creados
- [x] `templates/admin/admin_dashboard.html` - Panel con KPIs por módulo
- [x] `templates/admin/admin_modulo.html` - Vista genérica con tabs por entidad

### 11.2 Características
- [x] Tabs dinámicos para cada entidad del módulo
- [x] Tabla CRUD con contador de registros
- [x] Modal genérico para crear/editar (campos dinámicos)
- [x] Botones de toggle activo/inactivo
- [x] Confirmación de eliminación

---

## FASE 12: Integración en Menú Principal ✅
**Tiempo estimado:** 30 min

### 12.1 Cambios en base.html
- [x] Sección "Configuración" visible solo para rol admin/manager/gerente
- [x] Link a `/admin` con icono engranaje
- [x] Estilo active-link cuando está en /admin/*

### 12.2 Actualizar security.py
- [x] MODULE_ROUTES: agregada ruta `admin: /admin`

---

## FASE 13: Testing y Validación ✅
**Tiempo estimado:** 45 min

### 13.1 Tests Ejecutados
- [x] Admin Dashboard: 200 ✅
- [x] Admin Gastos: 200 ✅
- [x] Admin Tesorería: 200 ✅
- [x] Admin RRHH: 200 ✅
- [x] Admin Stock: 200 ✅
- [x] Panel Compras: 200 ✅

---

## Progreso General Sprint 2

| Fase | Estado | Completado |
|------|--------|------------|
| Fase 8 | ✅ Completada | 100% |
| Fase 9-10 | ✅ Completada | 100% |
| Fase 11 | ✅ Completada | 100% |
| Fase 12 | ✅ Completada | 100% |
| Fase 13 | ✅ Completada | 100% |

**🎉 SPRINT 2 COMPLETADO 🎉**

---

## Catálogos Implementados

### Gastos
| Entidad | Campos | Tabla DB |
|---------|--------|----------|
| CategoriaGasto | nombre, descripcion, activo | categoria_gasto |
| Proveedor | nombre, cuit, email, telefono, direccion, activo | proveedor |

### Tesorería
| Entidad | Campos | Tabla DB |
|---------|--------|----------|
| InstrumentoPago | nombre, descripcion, activo | instrumentos_pago |

### RRHH
| Entidad | Campos | Tabla DB |
|---------|--------|----------|
| Turno | nombre, descripcion, hora_inicio, hora_fin, dias_semana, activo | turnos |

### Stock/Core
| Entidad | Campos | Tabla DB |
|---------|--------|----------|
| Location | name, address | locations |
| Product | name, sku, price, category | products |
| BusinessUnit | name, code | business_units |

---

## Orden de Ejecución Sugerido
1. **Fase 8** → Verificar/corregir Panel Compras
2. **Fase 9** → Diseño arquitectura
3. **Fase 10** → Blueprint admin.py + APIs
4. **Fase 11** → Templates
5. **Fase 12** → Integración menú
6. **Fase 13** → Testing

---

## Commits Realizados Sprint 2
| Fecha | Commit | Descripción |
|-------|--------|-------------|
| - | - | - |
