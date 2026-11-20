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

Bloqueo por cuenta (D6): 10 intentos fallidos dentro de una ventana de 15 minutos bloquean la cuenta durante 15 minutos. La ventana empieza en el primer fallo y se reinicia al vencer. Durante el bloqueo, todo intento (también con la clave correcta) recibe el mismo mensaje y el mismo código HTTP que una clave incorrecta. Un acierto fuera del bloqueo reinicia el contador. Los usuarios inexistentes y las cuentas desactivadas no tienen estado. El límite por IP existente no cambia.

Riesgo a validar: alguien puede bloquear a una persona real adivinando su usuario. El bloqueo dura 15 minutos y un administrador o gerente puede levantarlo con «Desbloquear» en Administración > Usuarios; esa acción queda auditada como `user_unlocked`.

Visor de auditoría: `/admin/usuarios/auditoria` (admin, manager y gerente; enlace «Ver auditoría completa» desde Administración > Usuarios). Filtra por usuario (actor o destino), acción y rango de fechas (días de Argentina, incluidos); pagina de 50 y ordena del más nuevo al más viejo. La API `GET /api/admin/usuarios/auditoria` acepta `q`, `accion`, `desde` y `hasta` (AAAA-MM-DD) y `pagina`; sin parámetros devuelve las últimas 50 acciones, como antes. Los parámetros inválidos responden 400 JSON.

Retención (D10): 2 años. Hoy no se purga nada. La purga es manual con `scripts/purgar_auditoria_usuarios.py --antes-de AAAA-MM-DD`: sin `--ejecutar` solo simula; para borrar hay que repetir la misma fecha en `--confirmar`. No hay tarea programada y no se corre contra producción sin autorización de Inti.

### Recuperación de clave y correo de contacto (C5)

Correo de contacto (opcional): el alta y la acción «Editar correo» de cada fila guardan un correo de referencia. Se guarda en minúsculas, sin espacios, con formato nombre@dominio.tld en caracteres ASCII y hasta 254 caracteres. No se repite entre usuarios sin distinguir mayúsculas. Vacío lo borra. No se envía ningún correo: es un dato de contacto para el administrador. La auditoría guarda el correo enmascarado («a***@dominio») y nunca aparece en logs.

Para el administrador (admin, manager o gerente): «Generar enlace de recuperación» pide la vigencia (de 5 a 1440 minutos; 30 por defecto) y muestra el enlace una sola vez, con botón «Copiar». Emitir el enlace tiene este efecto: la clave actual deja de funcionar, se cierran las sesiones web y los JWT de esa cuenta, y la cuenta queda sin clave utilizable hasta que la persona canjee el enlace o el administrador genere otro enlace o restablezca la clave (decisión D2). Un enlace nuevo revoca el anterior. No se genera un enlace para la propia cuenta: para eso está «Cambiar mi clave». Límite: 5 enlaces cada 10 minutos por administrador. «Revocar enlace» invalida el vigente y deja la cuenta sin clave hasta un nuevo enlace o un restablecimiento. Restablecer la clave (C3) revoca los enlaces vigentes.

Para la persona: abre el enlace completo en el navegador (el código va después del #), elige una clave nueva de al menos 12 caracteres con la misma política de «Cambiar mi clave» y la repite. El enlace sirve una sola vez, vence según su vigencia y no sirve si fue revocado o si la cuenta está desactivada. Al canjearlo entra con la clave nueva sin pasar por el cambio de clave temporal; las sesiones anteriores siguen cerradas. Si la clave no cumple la política, el enlace no se consume.

Respuesta uniforme: un enlace inexistente, vencido, usado, revocado o de cuenta desactivada recibe la misma página y el mismo mensaje. Límite de canjes: 5 intentos cada 10 minutos por IP (por proceso de la aplicación).

Auditoría: user_email_changed, user_recovery_issued, user_recovery_revoked, user_recovery_redeemed y recovery_failed (los fallos se agrupan por IP, motivo, cuenta y minuto). Purga manual: scripts/purgar_auditoria_usuarios.py también borra los enlaces usados o vencidos anteriores a la fecha, con simulación por defecto.

Riesgo a validar: quien recibe un enlace puede fijar la clave de la cuenta. Por eso el enlace se muestra una sola vez, se entrega por un canal seguro y se revoca al restablecer la clave.

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
