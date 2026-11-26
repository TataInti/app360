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
│             │  dashboard, rrhh, adelantos, compras  — SOLO LECTURA (nivel «view»)    │
│ direccion   │  dashboard, dashboard_comercial, panel, bi                             │
└─────────────┴────────────────────────────────────────────────────────────────────────┘
```

Son **11 roles** en `ACCESS_MAP` (`security.py`): `admin`, `manager`, `gerente`, `sales`, `purchases`, `hr`, `operations`, `finance`, `caja`, `director` y `direccion`. Un rol que no figura en el mapa no accede a ningún módulo y cae en `/sin-acceso`. `director` (con «r» final, solo lectura sobre tesorería, compras, gastos y RRHH) y `direccion` (solo paneles) son dos roles distintos.

### Nivel de acceso: «edit» y «view»

`get_user_module_access(modulo, user_id, rol)` devuelve el nivel de un usuario en un módulo:

- `admin`, `manager`, `gerente` (`all`): «edit» en todo.
- Un módulo que viene del rol: «edit», salvo que el rol esté en `ROLES_SOLO_LECTURA` (hoy solo `director`), en cuyo caso es «view».
- Un módulo que el rol no trae: el nivel de la excepción por usuario («view» o «edit»), o «none».

Con nivel «view» el servidor deja pasar las lecturas (GET) y rechaza toda escritura (POST, PUT, PATCH, DELETE) con **403**: en la API, JSON `{"error": "Sin permiso de edición en el módulo"}`; en una pantalla, un aviso «Tu acceso a esta sección es solo lectura.». Lo hace `protect_blueprint` (pantallas y `/api/<módulo>` con sesión) y `jwt_modulo(..., 'edit')` (API REST con Bearer); `jwt_o_sesion` solo se usa en lecturas.

Las plantillas leen el nivel con `access_level('modulo')` y `can_edit('modulo')` (contexto Jinja, `app.py`): con nivel «view» no se dibujan los botones de alta, edición, aprobación, pago, anulación ni «Generar».

---

## Capacidades por rol

### admin / manager / gerente

- Acceso a **todos** los módulos y rutas.
- Acceso a `/admin` — ABM de catálogos (categorías de gasto, proveedores, instrumentos, empleados, productos, ubicaciones, etapas del pipeline).
- Acceso a `/admin/accesos` — excepciones de módulo por usuario (ver más abajo).
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
- Gastos: alta y consulta.
- **Anulación de movimientos**: requiere flujo de 2 pasos — el usuario solicita la anulación con motivo, y un `admin`/`manager`/`gerente` debe autorizarla desde la misma pantalla.
- **No puede** editar arqueos, acceder a RRHH, ventas ni administración.

### director

- **Solo lectura, en el servidor y en la pantalla.** Ve tesorería (movimientos, arqueos, instrumentos, portadores, cta cte Friar), gastos, BI, panel ejecutivo, dashboard financiero, RRHH (panel, empleados, adelantos, liquidaciones, ausentismo) y compras.
- **Ninguna escritura funciona**: alta de movimientos y arqueos, pagos y liquidaciones de la cta cte Friar, órdenes de compra, cambios de estado y recepciones, registro de gastos, adelantos (solicitar, aprobar, pagar), liquidaciones, ausentismo, asistencia, fichadas, turnos y empleados. Pantalla web y API (sesión o Bearer) responden 403.
- Las pantallas no muestran los botones de acción (Registrar, Nuevo arqueo, Nuevo registro, Registrar gasto, Nueva solicitud, Aprobar, Subir fichadas, Generar liquidación, Nuevo pago/liquidación Friar, justificar, solicitar anulación). Exportar a Excel y filtrar siguen disponibles.
- **No tiene acceso** a ventas, stock, CRM ni administración.
- Antes de este cambio la pantalla de tesorería ocultaba los botones (`canEdit`) pero el servidor aceptaba las escrituras; hoy el servidor las rechaza.
- Una excepción por usuario (Administración › Accesos) se suma: puede dar «Editar» en un módulo que el rol no trae, y los módulos del rol siguen en «view».

### direccion

- Paneles de consulta: `dashboard`, `dashboard_comercial`, `panel` (panel ejecutivo) y `bi`. No tiene tesorería, compras, RRHH, ventas ni administración.

---

## Administración › Accesos (excepciones por usuario)

Pantalla `/admin/accesos` (solo `admin`, `manager`, `gerente`). Tabla usuario × 12 módulos (`MANAGED_MODULES`: dashboard, dashboard_comercial, panel, bi, products, locations, stock, crm, compras, rrhh, tesoreria, gastos). Cada celda se guarda en `user_module_permissions` con nivel «view» o «edit» y rige desde el siguiente request.

- Las excepciones **se SUMAN al rol**: dan acceso a un módulo que el rol no trae. Los módulos del rol aparecen fijos («Editar · del rol»; en `director`, el nivel real es «view»).
- **«Sin acceso» no resta**: solo borra la excepción del usuario y **no quita lo que el rol ya da** (medido con `sales` + crm «Sin acceso» y `hr` + rrhh «Sin acceso»: siguen entrando). La opción de quitar un módulo a un usuario todavía no está construida.
- Solo se pueden conceder los 12 módulos de la lista; no están `ventas`, `comercial`, `objetivos`, `arqueos`, `movimientos`, `admin` (SabioGo) ni Administración.
- Los cambios de accesos no quedan en `user_audit_log` (medido: 0 filas tras guardar).
- Los módulos del rol salen del código (`ACCESS_MAP`); cambiarlos exige un commit y un despliegue.

### ventas / comercial / objetivos frente a crm

Son nombres de módulo distintos en el servidor:

- `crm` protege leads, campañas e interacciones (`blueprints/crm.py`).
- `ventas` protege las pantallas de ventas (`/ventas`, `/ventas/nuevo`, criterio de clientes).
- `comercial` protege `/comercial/*` (objetivos, salón, performance, seguimiento). `objetivos` figura en `ACCESS_MAP` de `sales` y en `MODULE_ROUTES`, pero la pantalla `/comercial/objetivos` la guarda `comercial`.
- `ventas` y `comercial` están en `ACCESS_MAP["sales"]` y **no** en `MANAGED_MODULES`: no se pueden dar como excepción. Una excepción sobre `crm` abre leads y campañas, pero el menú también muestra Ventas, Nueva venta y Objetivos (usa `can_access('crm')`) y el servidor las rechaza (302). Es un desajuste conocido de menú, sin cambios en este corte.

## Cómo se mide el acceso (barrido)

La matriz rol × ruta se obtiene con un barrido reproducible sobre una instancia local con SQLite y datos sintéticos (nunca producción): un usuario por rol, cuatro usuarios con excepciones, y las 258 reglas de `app.url_map` con cada método (GET, POST, PUT, PATCH, DELETE), con sesión web real y con Bearer para `/api/*`. Las escrituras se envían con cuerpo vacío: 200/400/404/500 significan «pasó la guardia» y 302/401/403 «la guardia cortó». El barrido se ejecuta antes y después de cada cambio de permisos y se comparan las celdas; en este corte solo cambiaron 34 celdas, todas escrituras de `director` (de «pasa la guardia» a 403). La prueba automática equivalente es `tests/test_director_solo_lectura.py`.

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
| `protect_blueprint(bp, module)` | Guard en `before_request` de cada blueprint. Redirige si el rol no tiene el módulo en su ACCESS_MAP; con nivel «view» rechaza POST/PUT/PATCH/DELETE con 403. |
| `jwt_modulo(módulo, 'edit')` / `jwt_o_sesion(módulo)` | Escrituras (y lecturas con sesión) de la API REST (`api_rest.py`): exigen JWT, el módulo y, en escrituras, nivel «edit». |
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
## Cabeceras de seguridad y caché

Las pone la app en cada respuesta (`app.py`, `add_security_headers`):

- `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection`, `Referrer-Policy: strict-origin-when-cross-origin` y la CSP (todavía con `'unsafe-inline'`: quitarlo es un pendiente que exige mover el JS y los estilos en línea de `templates/`).
- `Strict-Transport-Security` si `PREFERRED_URL_SCHEME` es https. En producción lo emite nginx; la app puede duplicarlo y nginx oculta el de la app para dejar uno solo.
- `Cache-Control: no-store` y `Pragma: no-cache` en todo lo que no sea `/static/...`: HTML, JSON, redirecciones, errores y descargas. Si una ruta fija su propio `Cache-Control` se respeta; el «no-cache» por omisión de `send_file` se reemplaza por `no-store`. Los estáticos conservan el caché de Flask y se versionan con `asset()` (`?v=`).
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()` en las respuestas HTML (ninguna pantalla usa esas capacidades).

Las pone nginx: TLS, HSTS y la cabecera `X-Forwarded-For`. nginx debe sobrescribir `X-Forwarded-For` con `$remote_addr` (un único valor); el despliegue de ese cambio va aparte.

IP del cliente: la app confía en un solo proxy (`ProxyFix` con `x_for=1`) y toma el último valor de `X-Forwarded-For`, nunca el primero que manda el cliente. Después, `REMOTE_ADDR` se sanea: si no es una IP válida queda `invalida` (así no entra texto arbitrario al límite por IP, al bloqueo cuenta+IP ni a la auditoría). Todo se trunca además a 45 caracteres. La app no debe exponerse directo a Internet: sin nginx delante, el cliente elegiría su IP. Casos cubiertos en `tests/test_ip_cliente_proxy.py`.

Chequeo de esquema en el despliegue: `scripts/chequeo_esquema_usuarios_c4.sql` verifica que `alembic_version` tenga exactamente 1 fila (`alembic_una_fila`) y que existan las tablas, columnas e índice de C4; la revisión vigente se lista solo como dato informativo (`revision_actual_informativa`), por lo que sigue sirviendo cuando la cabeza de Alembic es posterior a C4.

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

Todas las mutaciones de cuentas pasan primero por `services.usuarios_admin.bloquear_mutaciones_usuarios()`. En PostgreSQL usa el advisory xact lock bigint `714360036043`; en SQLite no hace nada. Debe tomarse antes de cualquier `FOR UPDATE` y es la primitiva común para los cortes de recuperación, desbloqueo y MFA. Los deadlocks (`40P01`) y errores de serialización (`40001`) reintentan una vez la operación completa; si vuelve a fallar, la API devuelve 409 `OPERACION_CONCURRENTE` sin mostrar detalles SQL.

Las cuentas existentes conservan rol por defecto en `setup_users.py`, `setup_database.py` y `setup_comercial.py`. `--forzar-roles` habilita expresamente aplicar los roles preset. Las claves existentes se regeneran solo con sus opciones explícitas (`--reset`, `--reset-admin-password` o `--reset-claves`), apagadas por defecto.
