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
# Crear usuarios caja y director. Las claves nuevas se generan al azar y no se muestran.
python scripts/setup_users.py

# Ver una sola vez las claves generadas en esta corrida (no se guardan en ningún archivo)
python scripts/setup_users.py --mostrar-claves

# Regenerar las claves de usuarios existentes (pide confirmación escrita)
python scripts/setup_users.py --reset
```

Las cuentas existentes conservan su clave en cada corrida: solo `--reset` la cambia.

Para crear un usuario con rol distinto, editar `USERS` en [scripts/setup_users.py](../scripts/setup_users.py) o usar directamente el modelo `User` en un contexto de app.

> La gestión de permisos por módulo está disponible en `/admin/accesos` (roles `admin`, `manager`, `gerente`).
> Alta, desactivación y reactivación de usuarios: pantalla **Administración > Usuarios** (`/admin/usuarios`), solo para `admin`, `manager` y `gerente`. La clave temporal vence a las 72 horas y se muestra una sola vez. Cada acción queda en la tabla `user_audit_log`. Cambio de rol: solo roles de la lista; nadie cambia su propio rol y el último administrador activo no pasa a un rol sin administración. El rol rige desde la siguiente acción. Restablecimiento de clave: clave temporal de 72 horas que se muestra una sola vez; corta las sesiones y los JWT previos y obliga a cambiarla al ingresar. Reactivar una cuenta con el script suma la versión de token y queda auditado. `setup_users.py` sigue disponible para cargas por consola.

## Jerarquía de Administración de Usuarios (C3)

La API es la fuente de verdad para las acciones; la pantalla refleja los permisos y no los reemplaza.

- `admin` y `manager` (alias legacy) pueden administrar cualquier cuenta.
- `gerente` puede administrar cuentas cuyo rol actual no sea `admin` ni `manager`. Puede administrar a otro `gerente`.
- `gerente` no puede asignar los roles `admin` ni `manager`, tanto al crear como al cambiar una cuenta.
- La limitación se aplica a cambios de rol, restablecimiento de clave, desactivación y reactivación. El servidor responde 403 con código `JERARQUIA_INSUFICIENTE` y el mensaje «Esta cuenta la administra un administrador. Pedile a un administrador que haga este cambio.»
- Para `gerente`, los selectores no ofrecen `admin` ni `manager` y las acciones de filas `admin`/`manager` quedan deshabilitadas con explicación. El servidor vuelve a validar cada operación.
- El conteo del último administrador sigue considerando las cuentas activas `admin`, `manager` y `gerente`.

`services.usuarios_admin.puede_administrar(actor, objetivo, rol_nuevo=None)` concentra la regla reutilizable de jerarquía y devuelve `(ok, codigo, mensaje)`. `objetivo=None` permite validar altas. No reemplaza las reglas propias de cada acción, como no actuar sobre sí mismo, mantener un administrador activo o exigir que la cuenta esté activa. Está pensada para que los cortes de recuperación, desbloqueo y MFA reusen la misma decisión.

## Escrituras simultáneas y scripts

El reset de clave y `/cambiar-clave` bloquean la fila del usuario y vuelven a leerla tras obtener el bloqueo. Si el reset ocurre primero, el cambio propio valida la clave temporal vigente y limpia `must_change_password` y su vencimiento; si el cambio propio ocurre primero, el reset final deja la clave temporal y el cambio obligatorio. Los incrementos de `token_version` quedan serializados también con desactivación y reactivación.

Las cuentas existentes conservan rol por defecto en `setup_users.py`, `setup_database.py` y `setup_comercial.py`. `--forzar-roles` habilita expresamente aplicar los roles preset. Las claves existentes se regeneran solo con sus opciones explícitas (`--reset`, `--reset-admin-password` o `--reset-claves`), apagadas por defecto.
