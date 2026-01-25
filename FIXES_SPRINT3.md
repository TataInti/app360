# Sprint 3 - Correcciones de Errores en Producción
**Fecha inicio:** 25 enero 2026  
**Estado:** ✅ Completado  
**URL Producción:** https://vyp.app360.com.ar

---

## Resumen de Errores Detectados

| # | Módulo | URL | Problema | Tipo | Estado |
|---|--------|-----|----------|------|--------|
| 1 | Operaciones | /products/new | CSRF token faltante | CSRF | ✅ |
| 2 | Operaciones | /locations/new | CSRF token missing | CSRF | ✅ |
| 3 | Comercial | /campaigns/new | CSRF token missing | CSRF | ✅ |
| 4 | Compras | /compras | Migration no aplicada | Backend | ⚠️ VPS |
| 5 | RRHH | /rrhh | Tarjeta encuestas/clima | UI | ✅ |
| 6 | RRHH | /rrhh/empleados | Method not allowed (POST) | Ruta | ✅ |
| 7 | Tesorería | /tesoreria | Modal sin CSRF | JS/API | ✅ |
| 8 | Tesorería | /tesoreria/arqueos | Fetch sin CSRF | API | ✅ |
| 9-12 | Admin | /admin/* | Botones sin CSRF | JS | ✅ |

---

## Correcciones Realizadas

### ✅ CSRF Token en Formularios
Archivos corregidos:
- `templates/location_form.html` - Token agregado
- `templates/product_form.html` - Token agregado
- `templates/campaigns_list.html` - Token agregado
- `templates/rrhh_empleados.html` - Token agregado

### ✅ CSRF en Fetch API
Archivos corregidos:
- `templates/tesoreria_panel.html` - X-CSRFToken en movimientos y arqueos
- `templates/tesoreria_arqueos.html` - X-CSRFToken en POST
- `templates/admin/admin_modulo.html` - X-CSRFToken en POST, PUT, DELETE, PATCH

### ✅ Ruta RRHH Empleados
- `blueprints/rrhh.py` - Agregado método POST a `/rrhh/empleados`

### ✅ UI RRHH Panel
- `templates/rrhh_panel.html` - Removida tarjeta "Encuestas y clima"

---

## ⚠️ Acción Requerida en VPS

Para el error del Panel de Compras, ejecutar en VPS:
```bash
cd /var/www/app360
source venv/bin/activate
flask db upgrade
```

---
- [ ] Verificar que la migración se aplicó en VPS: `flask db upgrade`
- [ ] Revisar logs del servidor: `journalctl -u gunicorn -n 50`
- [ ] Si la tabla no tiene las columnas nuevas, recrear migración

### 3.3 Verificación
- [ ] Acceder a /compras sin error
- [ ] Listar órdenes de compra

---

## FASE 4: RRHH - Tarjeta Encuestas/Clima ⏳
**Tiempo estimado:** 15 min  
**Archivos afectados:** `templates/rrhh_panel.html`

### 4.1 Corrección
- [ ] Eliminar o comentar la sección de tarjeta de encuestas/clima
- [ ] Verificar que no haya referencias rotas

### 4.2 Verificación
- [ ] Panel RRHH sin la tarjeta

---

## FASE 5: RRHH Empleados - Method Not Allowed ⏳
**Tiempo estimado:** 30 min  
**Archivos afectados:** `blueprints/rrhh.py`

### 5.1 Diagnóstico
La ruta no acepta método POST.

### 5.2 Correcciones
- [ ] Buscar ruta de creación de empleados
- [ ] Agregar `methods=["GET", "POST"]` a la ruta
- [ ] O crear ruta separada para POST
- [ ] Agregar CSRF token al formulario

### 5.3 Verificación
- [ ] Test crear empleado

---

## FASE 6: Tesorería - Modales No Funcionan ⏳
**Tiempo estimado:** 1 hora  
**Archivos afectados:** `templates/tesoreria_panel.html`, `templates/tesoreria_arqueos.html`, `blueprints/tesoreria.py`

### 6.1 Diagnóstico Modal Arqueo (Panel)
- [ ] Revisar JS del modal en tesoreria_panel.html
- [ ] Verificar que el formulario llama al endpoint correcto
- [ ] Verificar que incluye CSRF token

### 6.2 Diagnóstico Modal Arqueos (Lista)
El error "Error de conexión" sugiere:
- [ ] Endpoint API no existe o tiene error
- [ ] CSRF token no se envía en fetch
- [ ] URL incorrecta en JavaScript

### 6.3 Correcciones
- [ ] Agregar CSRF token a las peticiones fetch
- [ ] Verificar endpoint `/api/tesoreria/arqueos` existe y funciona
- [ ] Revisar headers de Content-Type

### 6.4 Patrón para agregar CSRF a fetch:
```javascript
fetch(url, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
    },
    body: JSON.stringify(data)
})
```

### 6.5 Verificación
- [ ] Modal panel tesorería funciona
- [ ] Modal arqueos guarda correctamente

---

## FASE 7: Admin - Botones No Funcionan ⏳
**Tiempo estimado:** 1 hora  
**Archivos afectados:** `templates/admin/admin_modulo.html`, `blueprints/admin.py`

### 7.1 Diagnóstico
Los botones de "Nuevo" en todos los módulos admin no producen acción.
Posibles causas:
- [ ] JavaScript con error de sintaxis
- [ ] Modal no se encuentra (ID incorrecto)
- [ ] Función `abrirModalNuevo` no definida o con error

### 7.2 Correcciones
- [ ] Revisar función `abrirModalNuevo()` en admin_modulo.html
- [ ] Verificar que el modal existe en el HTML
- [ ] Agregar CSRF token a las peticiones POST de la API
- [ ] Revisar consola del navegador para errores JS

### 7.3 Patrón de corrección API calls:
```javascript
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

fetch(url, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
    },
    body: JSON.stringify(data)
})
```

### 7.4 Verificación por módulo
- [ ] Admin/Gastos: Crear categoría y proveedor
- [ ] Admin/Tesorería: Crear instrumento de pago
- [ ] Admin/RRHH: Crear turno
- [ ] Admin/Stock: Crear ubicación, producto, unidad

---

## Orden de Ejecución Recomendado

| Prioridad | Fase | Razón |
|-----------|------|-------|
| 1 | Fase 3 | Panel Compras es crítico - error 500 |
| 2 | Fase 1 | CSRF afecta múltiples formularios |
| 3 | Fase 2 | Productos es funcionalidad core |
| 4 | Fase 5 | RRHH empleados es funcionalidad core |
| 5 | Fase 6 | Tesorería modales |
| 6 | Fase 7 | Admin módulos |
| 7 | Fase 4 | UI cleanup (menor prioridad) |

---

## Progreso General

| Fase | Estado | Completado |
|------|--------|------------|
| Fase 1 | ⏳ Pendiente | 0% |
| Fase 2 | ⏳ Pendiente | 0% |
| Fase 3 | ⏳ Pendiente | 0% |
| Fase 4 | ⏳ Pendiente | 0% |
| Fase 5 | ⏳ Pendiente | 0% |
| Fase 6 | ⏳ Pendiente | 0% |
| Fase 7 | ⏳ Pendiente | 0% |

---

## Notas Técnicas

### CSRF Token en Flask
El token CSRF debe estar presente en:
1. Meta tag en `<head>`: `<meta name="csrf-token" content="{{ csrf_token() }}">`
2. Formularios HTML: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
3. Peticiones AJAX: Header `X-CSRFToken`

### Verificar en VPS
```bash
# Ver logs de Gunicorn
journalctl -u gunicorn -n 100

# Aplicar migraciones
cd /var/www/app360
source venv/bin/activate
flask db upgrade

# Reiniciar servicio
sudo systemctl restart gunicorn
```

---

## Commits Realizados
| Fecha | Commit | Descripción |
|-------|--------|-------------|
| - | - | - |
