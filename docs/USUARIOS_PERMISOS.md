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

### Registro de accesos, bloqueo por cuenta y auditoría (C4)

Registro de accesos: cada login correcto y cada login fallido queda en `user_audit_log` (acciones `login_ok` y `login_failed`), tanto en la pantalla como en `/api/login`. Se guarda el usuario tal como se escribió (hasta 80 caracteres imprimibles), la IP y un motivo genérico: `clave_incorrecta`, `usuario_inexistente`, `cuenta_inactiva`, `cuenta_bloqueada` o `clave_temporal_vencida`. La clave no se guarda en ningún campo, log ni pantalla. Los fallos de la misma IP, motivo, cuenta y minuto se agrupan en una sola fila con el contador en `repeticiones`: una ráfaga de nombres inexistentes ocupa una fila por minuto y por IP. Si la escritura de auditoría falla, el login responde igual y queda un evento de seguridad.

Bloqueo de inicio de sesión: 10 fallos en 15 minutos desde la misma IP bloquean ese par (cuenta, IP) por 15 minutos; no bloquean a la misma cuenta desde otra IP. Además, 40 fallos de una cuenta en 15 minutos, sumando todas las IP, activan el bloqueo global por 15 minutos. Ambos son ventanas fijas y un intento durante un bloqueo no lo extiende. Se usan `users.failed_login_count`, `failed_login_window_start` y `locked_until` para el tope global; `user_login_attempts` guarda los pares. Si la tabla llega a 50 000 pares, no se crean pares nuevos y esos fallos cuentan solo para el tope global.

Un ingreso correcto desde una IP desbloqueada reinicia el contador de ese par y, si el tope global no está activo, también el global. «Desbloquear» limpia el tope global y todos los pares de esa cuenta; la acción queda auditada como `user_unlocked`. La lista muestra «Bloqueada» si hay un bloqueo global o al menos una IP bloqueada, con la cantidad de IP vigentes.

El bloqueo solo rige para **nuevos inicios de sesión**: no corta sesiones web ni JWT ya emitidos. Cortarlos permitiría que un atacante expulsara a usuarios legítimos. La IP efectiva es `request.remote_addr` después de `ProxyFix`; depende de que Nginx sea el único acceso de red y escriba `X-Forwarded-For`. Gunicorn escucha solo en `127.0.0.1`; si se expusiera directamente, no se debe confiar en esa cabecera.

El limitador por IP preexistente usa memoria por worker (no un contador compartido): con varios workers, el límite efectivo se multiplica. Los pares sin actividad por más de un día se purgan oportunistamente, hasta 100 por escritura de login. La auditoría conserva la retención de 2 años; no hay tarea programada y la purga manual sigue siendo `scripts/purgar_auditoria_usuarios.py --antes-de AAAA-MM-DD` (simulación por defecto; para borrar hay que repetir la fecha con `--confirmar`). No se corre contra producción sin autorización de Inti.

Visor de auditoría: `/admin/usuarios/auditoria` (admin, manager y gerente; enlace «Ver auditoría completa» desde Administración > Usuarios). Filtra por usuario (actor o destino), acción y rango de fechas (días de Argentina, incluidos); pagina de 50 y ordena del más nuevo al más viejo. La API `GET /api/admin/usuarios/auditoria` acepta `q`, `accion`, `desde` y `hasta` (AAAA-MM-DD) y `pagina`; sin parámetros devuelve las últimas 50 acciones, como antes. Los parámetros inválidos responden 400 JSON.

Retención (D10): 2 años. Hoy no se purga nada. La purga es manual con `scripts/purgar_auditoria_usuarios.py --antes-de AAAA-MM-DD`: sin `--ejecutar` solo simula; para borrar hay que repetir la misma fecha en `--confirmar`. No hay tarea programada y no se corre contra producción sin autorización de Inti.
