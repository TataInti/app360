# Plan: ABM Control de Accesos por Usuario

**TL;DR**: Agregar una sección ABM en `/admin` (Flask/Jinja) donde admin/gerente gestionen permisos de acceso por módulo para cada usuario. Nuevo modelo `UserModulePermission`, lógica aditiva (permisos individuales suman al rol base), enforcement backend + UI.

## Decisiones acordadas

- **UI**: Flask/Jinja admin existente
- **Módulos**: Los 12 del sidebar (dashboard, panel ventas, panel ejecutivo, BI, productos, ubicaciones, stock, CRM, compras, RRHH, tesorería, gastos)
- **Lógica aditiva**: Permisos individuales **suman** al rol. No pueden restringir lo heredado del rol.
- **Niveles**: `view` (solo lectura), `edit` (lectura+escritura), sin entrada = el rol decide
- **Tesorería**: Usuarios con rol `caja` deben ver `gastos` para acceder a conceptos creados en administración (guard de gastos debe usar módulo `gastos`).

---

## Fase 1: Modelo de datos

### 1. Crear modelo `UserModulePermission` — nuevo `models/core/user_permission.py`

- Campos: `id` (PK), `user_id` (FK→users.id, NOT NULL), `module` (String 50, NOT NULL), `access_level` (String 10, NOT NULL, valores: 'view'/'edit')
- Constraint UNIQUE en (`user_id`, `module`)
- INDEX en `user_id`
- Usar patrón idéntico a `models/core/user.py` (hereda `db.Model`, sin base class extra)

### 2. Registrar modelo — modificar `models/core/__init__.py`

- Agregar import y export de `UserModulePermission`

### 3. Migración Alembic — `migrations/versions/{fecha}_add_user_module_permissions.py`

- Seguir patrón idempotente con `_table_exists()` (como en migración de arqueo_detalle)
- Crear tabla `user_module_permissions`
- Crear unique constraint `uq_user_module_perm` en (user_id, module)
- Crear index en `user_id`

---

## Fase 2: Lógica de acceso (backend)

### 4. Agregar constante `MANAGED_MODULES` en `security.py`

- Dict con módulo → label display. Ejemplo: `{"dashboard": "Panel Tesorería", "crm": "CRM / Ventas", ...}`
- Reusar para UI y validación

### 5. Crear función `get_user_module_access(module, user_id, role)` en `security.py`

- Retorna `'edit'`, `'view'`, o `'none'`
- Lógica:
  1. Si `role` tiene `"all"` en ACCESS_MAP → retorna `'edit'`
  2. Si `module` está en `ACCESS_MAP[role]` → retorna `'edit'` (acceso heredado del rol)
  3. Buscar `UserModulePermission` para `(user_id, module)` → si existe, retornar su `access_level`
  4. Default: `'none'`

### 6. Modificar `module_allowed(module, role)` en `security.py`

- Ampliar para aceptar `user_id` opcional
- Si `user_id` se proporciona → llamar a `get_user_module_access()`, retornar True si != 'none'
- Si solo `role` (backwards compat) → lógica actual sin cambios

### 7. Actualizar contexto Jinja en `app.py`

- Cambiar `"can_access": module_allowed` → wrapper lambda que pase `session.get("user_id")` automáticamente

### 8. Enforcement de "view" en blueprint guards

- Para módulos con acceso `'view'`, permitir GET pero bloquear POST/PUT/DELETE
- Modificar `protect_blueprint()` en `security.py`: si `get_user_module_access()` retorna `'view'` y el método HTTP es POST/PUT/DELETE → retornar 403
- Alternativa: agregar decorador `@edit_required(module)` para rutas de escritura

---

## Fase 3: API de administración

### 9. Agregar endpoints REST en `blueprints/admin.py`

- `GET /api/admin/accesos` → lista usuarios activos con sus permisos efectivos (combinando rol + individuales)
  - Retorna: `[{id, username, role, permissions: {module: effective_level, ...}, role_modules: [...]}, ...]`
- `PUT /api/admin/accesos/<int:user_id>` → guarda permisos individuales para un usuario
  - Body: `{permissions: {module: "view"|"edit"|"none", ...}}`
  - Solo guarda entradas donde el módulo NO está ya en ACCESS_MAP del rol del usuario (las heredadas se ignoran)
  - Validar que `module` esté en MANAGED_MODULES
  - Proteger con `@admin_required`

---

## Fase 4: UI de administración (Jinja Template)

### 10. Crear template `templates/admin/admin_accesos.html`

- Tabla con filas = usuarios, columnas = módulos
- Cada celda: radio buttons o select con opciones "Sin acceso" / "Ver" / "Editar"
- Módulos heredados del rol → celda muestra "Editar ✓" con badge "rol" y deshabilitado
- Módulos no heredados → celda con selector activo
- Header de tabla: nombres de módulos (de MANAGED_MODULES)
- Botón "Guardar cambios" por fila o global
- Feedback visual al guardar (toast/alert)

### 11. Agregar ruta web en `blueprints/admin.py`

- `GET /admin/accesos` → renderiza `admin_accesos.html` con datos precargados
- Proteger con `@admin_required`

### 12. Agregar link en `admin_dashboard.html`

- Nueva card/sección "Control de Accesos" en el dashboard de admin
- Icono de seguridad/shield
- Badge con cantidad de usuarios

### 13. Agregar link en sidebar (`templates/base.html`)

- Bajo sección "Configuración", agregar enlace "Control de Accesos" → `/admin/accesos`
- Condición: `session.get('role') in ['admin', 'manager', 'gerente']`

---

## Archivos

| Acción    | Archivo                                                    |
|-----------|------------------------------------------------------------|
| Crear     | `models/core/user_permission.py`                           |
| Crear     | `migrations/versions/{fecha}_add_user_module_permissions.py`|
| Crear     | `templates/admin/admin_accesos.html`                       |
| Modificar | `models/core/__init__.py`                                  |
| Modificar | `security.py`                                              |
| Modificar | `app.py`                                                   |
| Modificar | `blueprints/admin.py`                                      |
| Modificar | `templates/admin/admin_dashboard.html`                     |
| Modificar | `templates/base.html`                                      |

---

## Verificación

1. `flask db upgrade` → tabla `user_module_permissions` existe
2. `GET /api/admin/accesos` → retorna usuarios con permisos efectivos correctos
3. `PUT /api/admin/accesos/<id>` → persiste y se refleja en GET
4. User rol `sales` → módulos crm/ventas como "heredado" no editable
5. Permiso `view` aditivo → GET permitido, POST/PUT/DELETE → 403
6. UI funcional → tabla, radio buttons, guardar con feedback
7. Admin-only: usuarios sin rol admin/gerente rechazados en `/admin/accesos`
8. Sidebar actualizado con `can_access()` respetando permisos individuales

---

## Consideraciones

1. **Performance**: Query simple por user_id+module en cada request. Aceptable en fase inicial; si genera carga, cachear en `flask.g`.
2. **React SPA**: Los endpoints REST quedan listos para cuando la SPA los consuma.
3. **Roles admin/manager/gerente** tienen "all" → en su ABM todo aparece como heredado, nada editable.
4. **CSRF**: la UI de accesos envía `X-CSRFToken` para `PUT /api/admin/accesos/<id>`; sin ese header el backend responde 400 y en UI se ve como "error de red".
