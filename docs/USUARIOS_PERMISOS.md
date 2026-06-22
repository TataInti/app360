# Permisos y Capacidades por Rol

> Documento de referencia funcional sobre roles y módulos.
> No versionar listados reales de usuarios ni datos operativos concretos del entorno.

---

El campo `role` se almacena en la tabla `users` y se carga en `session["role"]` al hacer login.

---

## ACCESS_MAP completo

```
┌─────────────┬────────────────────────────────────────────────────────────────────────┐
│    Rol       │  Módulos permitidos                                                    │
├─────────────┼────────────────────────────────────────────────────────────────────────┤
│ admin       │  [all]  — acceso total a todos los módulos y funciones de administración│
│ manager     │  [all]  — alias operativo de admin                                      │
│ gerente     │  [all]  — alias de admin (reservado para futura granularidad)           │
├─────────────┼────────────────────────────────────────────────────────────────────────┤
│ sales       │  crm, ventas, dashboard_comercial, comercial, objetivos                 │
│ purchases   │  compras, dashboard, gastos                                             │
│ hr          │  rrhh, adelantos, ausentismo, dotacion, empleados                       │
│ operations  │  compras, stock, locations, products, dashboard                        │
│ finance     │  tesoreria, arqueos, movimientos, gastos, bi, panel                    │
│ caja        │  tesoreria, arqueos, movimientos, gastos                               │
│ director    │  tesoreria, arqueos, movimientos, gastos, bi, panel,                   │
│             │  dashboard, rrhh, adelantos, compras                                   │
└─────────────┴────────────────────────────────────────────────────────────────────────┘
```

---

## Capacidades por rol

### admin / manager / gerente

- Acceso a **todos** los módulos y rutas.
- Acceso a `/admin` — ABM de catálogos (categorías de gasto, proveedores, instrumentos, empleados, productos, ubicaciones, etapas del pipeline).
- Acceso a `/admin/accesos` — gestión de permisos individuales por usuario (si está implementado).
- **Anulación de movimientos**: directa, 1 solo paso. No requiere autorización de tercero.
- **Edición de arqueos**: permitida (solo del día actual, requiere justificación).
- **Autorizar / rechazar** solicitudes de anulación pendientes de otros usuarios.

### sales (usuario: ventas)

- CRM: leads, interacciones, campañas, etapas.
- Ventas: registro y listado de ventas.
- Dashboard Comercial: visualización.
- Comercial: panel y gestión de objetivos de venta.
- **No tiene acceso** a tesorería, finanzas, compras, RRHH, stock ni administración.

### hr (usuario: rrhh)

- RRHH: panel, empleados, adelantos, ausentismo, dotación.
- **No tiene acceso** a finanzas, ventas, compras ni administración.

### caja (usuario: tesoreria)

- Tesorería: panel, registro de movimientos de caja.
- Arqueos: apertura y cierre de arqueos.
- Movimientos: alta de movimientos de ingreso y egreso.
- Gastos: visualización.
- **Anulación de movimientos**: requiere flujo de 2 pasos — el usuario solicita la anulación con motivo, y un `admin`/`manager`/`gerente` debe autorizarla desde la misma pantalla.
- **No puede** editar arqueos, acceder a RRHH, ventas ni administración.

### director (usuario: direccion)

- Acceso de solo lectura/consulta a: tesorería, arqueos, movimientos, gastos, BI/análisis, panel ejecutivo, dashboard financiero, RRHH (panel y adelantos), compras.
- **No puede** crear ni editar registros (sin acceso a rutas POST/PUT).
- **No tiene acceso** a ventas, stock, CRM ni administración.
- En la UI, la variable `canEdit` es `false` para este rol — los botones de acción no se renderizan.

---

## Flujo de anulación de movimientos

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Rol         │  Acción disponible          │  Resultado                 │
├─────────────┼─────────────────────────────┼────────────────────────────┤
│ admin/       │  Botón "Anular" con motivo  │  Anulación inmediata       │
│ manager/     │                             │  estado → "anulado"        │
│ gerente      │                             │                            │
├─────────────┼─────────────────────────────┼────────────────────────────┤
│ caja         │  Botón "Solicitar anulación"│  estado → "pendiente_      │
│              │  con motivo obligatorio     │  anulacion"                │
│              │                             │  Requiere autorización     │
├─────────────┼─────────────────────────────┼────────────────────────────┤
│ director     │  Sin botón de acción        │  Solo lectura              │
└─────────────┴─────────────────────────────┴────────────────────────────┘

Autorizar/Rechazar solicitudes pendientes: solo admin / manager / gerente.
```

---

## Protección de rutas

| Mecanismo                | Descripción                                                               |
|--------------------------|---------------------------------------------------------------------------|
| `protect_blueprint(bp, module)` | Guard en `before_request` de cada blueprint. Redirige si el rol no tiene el módulo en su ACCESS_MAP. |
| `@admin_required`        | Decorador en rutas `/admin/*`. Verifica `role in ["admin", "manager", "gerente"]`. |
| `require_admin()`        | Helper en tesorería para edición de arqueos y autorización de anulaciones. |
| CSRF (`Flask-WTF`)       | Activo en todas las rutas web. Los fetch JS deben incluir `X-CSRFToken` desde la meta tag `csrf-token`. |
| JWT (`/api/*`)           | Las rutas de la API REST usan Bearer token. Los blueprints `/api/` están exentos de CSRF. |

---

## Dependencias técnicas del sistema de acceso

```
session["role"]
    └─> ACCESS_MAP  (security.py)
           └─> module_allowed(module, role)
                  └─> protect_blueprint()  →  before_request en cada blueprint
                  └─> can_access()         →  Jinja template context (app.py)
                        └─> sidebar links se ocultan si can_access() es False

session["user_id"]
    └─> requerido por anulación de movimientos y edición de arqueos
    └─> se setea en login junto a session["role"]
```

- `can_access` se inyecta en el contexto Jinja vía `app.py` → disponible en todos los templates como función de template.
- Los módulos con subvistas (ej: `rrhh` engloba `adelantos`, `ausentismo`, `dotacion`, `empleados`) se controlan con llaves separadas en ACCESS_MAP.
- El rol `caja` difiere del comportamiento de `ACCESS_MAP` en un punto específico: las escrituras destructivas (anulaciones) requieren autorización de un nivel superior, aunque el módulo esté permitido.

---

## Gestión de usuarios

Usuarios se crean/actualizan con el script:

```bash
# Crear usuarios caja y director (genera contraseñas aleatorias)
python scripts/setup_users.py

# Regenerar contraseñas
python scripts/setup_users.py --reset
```

Para crear un usuario con rol distinto, editar `USERS` en [scripts/setup_users.py](../scripts/setup_users.py) o usar directamente el modelo `User` en un contexto de app.

> La gestión de permisos por módulo está disponible en `/admin/accesos` (roles `admin`, `manager`, `gerente`).
> Alta/baja de usuarios y cambios de rol se hacen por script (`setup_users.py`) o directamente en BD — no hay UI de creación de usuarios.
