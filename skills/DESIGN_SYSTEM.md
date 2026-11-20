# Design System — App 360 · VyP SRL

> **Para agentes de IA**: Este archivo describe las convenciones de estilo y diseño vigentes en el proyecto.
> Antes de modificar cualquier template, leer este archivo completo.
> Este skill fue generado con `teach-impeccable` y se aplica en conjunto con las skills de Impeccable
> (`/normalize`, `/harden`, `/arrange`, `/onboard`, `/extract`, `/polish`, `/critique`, `/colorize`, etc.).

---

## 1. Contexto del Proyecto (Design Context)

### Usuarios
Equipo interno de VyP SRL (operadores de caja, gerentes, administradores, directores comerciales).
Uso diario, en escritorio, dentro del negocio. El usuario necesita información clara y acción rápida:
cargar un gasto, registrar un movimiento, ver el estado de caja, revisar KPIs de rentabilidad.
**No hay usuarios finales externos.** La app es interna y operativa.

### Brand Personality — 3 palabras
**Confiable · Claro · Eficiente**

- Confiable: los datos deben verse sólidos, no improvisados. Jerarquía de información consistente.
- Claro: zero ambigüedad en labels, valores y estados. Sin decoración innecesaria.
- Eficiente: las acciones más frecuentes deben estar a la vista, sin navegar submenús.

### Dirección Estética
- Light mode exclusivo. Fondo blanco `#fff` + superficies gris muy claro `#f8fafc`.
- Sidebar oscuro (`#0f172a` → `#1e293b`) como ancla visual. El contenido es claro.
- Tipografía del sistema: `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
  No se usa Google Fonts ni Tailwind. Bootstrap 5.3.1 + CSS custom en `base.html`.
- Colores de acento semánticos:
  - Azul (#2563eb) = acción principal / datos neutros
  - Verde (#16a34a) = positivo / ingresos
  - Rojo (#dc2626) = negativo / alertas / gastos
  - Ámbar (#f59e0b) = advertencia / sobrante / descuentos
  - Violeta (#7c3aed) = porcentajes / métricas de rentabilidad
  - Cielo (#0ea5e9) = neto / flujo de caja
- Referencias: Metabase, Linear, Notion. Anti-referencia: Bootstrap por defecto (colores saturados `bg-danger/success/info text-white`).

### Principios de Diseño
1. **Consistencia sobre creatividad**: todos los paneles usan el mismo sistema de componentes.
2. **El dato es el protagonista**: sin decoración que compita con los números.
3. **Jerarquía explícita**: los KPIs más importantes van en hero, los secundarios en cards menores.
4. **Empty states útiles**: nunca mostrar una tabla vacía sin explicación y acción sugerida.
5. **Estado del sistema siempre visible**: loading shimmer mientras se cargan datos, nunca silencio.

---

## 2. Stack Técnico

| Herramienta | Versión | Uso |
|---|---|---|
| Bootstrap | 5.3.1 | Grid, modales, alertas |
| Bootstrap Icons | 1.10.5 | Iconografía en toda la app |
| Chart.js | 4.4.0 | Gráficos de barras, línea, dona |
| Tom Select | 2.3.1 | `<select>` con búsqueda (>10 opciones) |
| Flask/Jinja2 | — | Templates server-rendered que extienden `base.html` |

**No usar**: jQuery, Tailwind, librerías de componentes externas adicionales.

---

## 3. Sistema de Componentes — Referencia Completa

Los tokens y componentes comunes viven en `templates/base.html`; los patrones compartidos de paneles y filtros están en `static/css/paneles_normalizados.css`.
**Nunca duplicar estilos en `<style>` inline dentro de templates hijos.** Usar las clases del DS. Los paneles comerciales mantienen reglas de dominio en `static/css/comercial_paneles.css`, y cargan la capa normalizada después de sus estilos locales.

---

### 3.1 Panel Header — `.panel-header`

Encabezado estándar de cada página. Siempre al inicio del `{% block content %}`.

```html
<div class="panel-header">
    <div>
        <h1><i class="bi bi-[icon]"></i> Título de la Página</h1>
        <span>Subtítulo descriptivo breve en una línea</span>
    </div>
    <!-- Botones de acción opcionales a la derecha -->
    <div class="action-bar">
        <button class="btn btn-sm btn-outline-secondary">...</button>
        <button class="btn btn-sm btn-primary">...</button>
    </div>
</div>
```

**Reglas:**
- `<h1>` siempre con `font-size: 1.5rem`, `font-weight: 700`, `color: #0f172a`.
- El subtítulo usa el `<span>` directo (no un `<p>` ni un `.panel-subtitle`).
  En CSS: `font-size: 0.8rem`, `color: #6b7280`.
- **Jamás** usar `<div class="d-flex justify-content-between align-items-center mb-4">` como reemplazo de `.panel-header`.
- **Jamás** dos `<h1>` en la misma página (error semántico).
- La `action-bar` dentro del `panel-header` no lleva margen propio (el header lo gestiona).

---

### 3.2 Action Bar — `.action-bar`

Barra de botones de acción cuando está fuera del `panel-header` (ej: controles en medio de página).

```html
<div class="action-bar">
    <button class="btn btn-sm btn-outline-secondary">...</button>
    <button class="btn btn-sm btn-success">...</button>
    <button class="btn btn-sm btn-primary">...</button>
</div>
```

**Reglas:**
- Todos los botones en `.action-bar` usan **`btn-sm`** sin excepción.
- `gap: 0.5rem`, `flex-wrap: wrap`.
- Border-radius de botones: `0.5rem`.
- **No mezclar** tamaños de botones (`.btn` y `.btn-sm` juntos) dentro de la misma barra.

---

### 3.3 Period Bar / Filter Bar — `.period-bar` y `.dim-bar`

Barra de filtros de período y dimensiones. API completa:

```html
<div class="period-bar dim-bar">
    <!-- Grupo de pills de período -->
    <div class="period-pills">
        <button class="pp active" data-period="mes">Este mes</button>
        <button class="pp" data-period="trim">Trimestre</button>
        <button class="pp" data-period="año">Año</button>
    </div>

    <!-- Separador vertical opcional -->
    <span class="filter-sep"></span>

    <!-- Grupo de fechas personalizadas -->
    <div class="date-group">
        <div><label>Desde</label><input type="date" id="fechaDesde" class="form-control form-control-sm"></div>
        <div><label>Hasta</label><input type="date" id="fechaHasta" class="form-control form-control-sm"></div>
    </div>

    <!-- Separador -->
    <span class="filter-sep"></span>

    <!-- Select de dimensión (con Tom Select si tiene >10 opciones) -->
    <label>Sucursal</label>
    <select id="selSucursal" class="form-select form-select-sm">...</select>

    <!-- Botón aplicar -->
    <button class="pp pp-action" onclick="cargar()">Aplicar</button>
</div>
```

**Clases de pill `.pp`:**

| Clase | Uso |
|---|---|
| `.pp` | Pill base (inactivo, fondo blanco) |
| `.pp.active` | Pill activo (azul sólido) |
| `.pp-month` | Acceso rápido "Este Mes" (azul cielo suave) |
| `.pp-action` | Botón de confirmación / aplicar (verde) |

**Reglas:**
- **Nunca** usar `<div class="btn-group">` ni `btn-outline-primary/btn-primary` para toggles de período.
- El estado activo se maneja en JS como: `document.querySelectorAll('.pp').forEach(b => b.classList.toggle('active', b === clicked))`.
- `.dim-bar` agrega estilos compactos para los `<select>` y labels dentro de la barra. Siempre combinar ambas clases: `class="period-bar dim-bar"`.

---

### 3.4 KPI Cards

#### KPI Standard — `.kpi-card`

```html
<div class="kpi-grid">
    <div class="kpi-card accent-green">
        <span class="kpi-label">Ingresos</span>
        <span class="kpi-value" id="kpi-ingresos">$0</span>
        <span class="kpi-sub">Ventas del período</span>          <!-- opcional -->
        <span class="kpi-delta up"><i class="bi bi-arrow-up"></i>+12%</span>  <!-- opcional -->
    </div>
    <div class="kpi-card accent-red">
        <span class="kpi-label">Gastos</span>
        <span class="kpi-value" id="kpi-gastos">$0</span>
    </div>
</div>
```

**Anatomía:**
- `.kpi-label`: `font-size: 0.75rem`, uppercase, `color: #6b7280`.
- `.kpi-value`: `font-size: 1.5rem`, `font-weight: 700`, `color: #0f172a`.
- `.kpi-sub`: `font-size: 0.75rem`, `color: #9ca3af`.
- `.kpi-delta.up` / `.kpi-delta.down`: verde/rojo con icono de flecha.

**Colores de acento — clases para `border-left: 3px solid [color]`:**

| Clase | Color | Uso semántico |
|---|---|---|
| `accent-blue` | `#2563eb` | Datos neutros, saldos, conteos |
| `accent-green` | `#16a34a` | Ingresos, positivos |
| `accent-red` | `#dc2626` | Egresos, gastos, faltantes |
| `accent-amber` | `#f59e0b` | Advertencias, descuentos, sobrantes |
| `accent-purple` | `#7c3aed` | Porcentajes, márgenes, rentabilidad |
| `accent-sky` | `#0ea5e9` | Neto, caja neta, balance |

**Grid automático:**

```html
<div class="kpi-grid">          <!-- minmax(190px, 1fr) — para 4 KPIs standard -->
<div class="kpi-grid-secondary"> <!-- minmax(160px, 1fr) — para 6+ KPIs pequeños -->
```

#### KPI Hero — `.kpi-hero`

Para los **1-2 KPIs más importantes** de un panel (el que el usuario mira primero).

```html
<div class="kpi-grid-hero">   <!-- minmax(240px, 1fr) — normalmente 2 columnas -->
    <div class="kpi-hero accent-purple">
        <span class="kpi-label">Margen %</span>
        <span class="kpi-value" id="kpi-margen-pct">0 %</span>
        <span class="kpi-sub">Rentabilidad sobre ingresos</span>
    </div>
    <div class="kpi-hero accent-sky">
        <span class="kpi-label">Caja Neta</span>
        <span class="kpi-value" id="kpi-caja-neta">$0</span>
        <span class="kpi-sub">Ingresos − Egresos − Gastos</span>
    </div>
</div>
```

**Diferencias con `.kpi-card`:**
- `padding: 1.5rem` (más generoso).
- `kpi-value`: `font-size: 2.2rem`, `font-weight: 800`.
- `border-left: 4px solid` (más grueso que el 3px del standard).
- `box-shadow` más pronunciado.

**Regla de jerarquía:**
- Siempre usar **primero** `kpi-grid-hero` con máx. 2 KPIs, después `kpi-grid-secondary` con los restantes.
- **Nunca** poner 8 KPIs del mismo tamaño en la misma grilla (diseño plano sin jerarquía).

---

### 3.5 Chart Card — `.chart-card-v2`

```html
<div class="charts-grid">
    <div class="chart-card-v2">
        <h3><i class="bi bi-bar-chart"></i> Título del Gráfico</h3>
        <span class="chart-description">Qué muestra y cómo leerlo, en una línea.</span>
        <div class="chart-stage">
            <canvas id="miChart"></canvas>
        </div>
    </div>
</div>
```

**Reglas:**
- El título usa `<h3>` (no `<h5>`, `<h6>`, ni `<div class="card-header">`).
- El canvas va dentro de `.chart-stage` (300px) o `.chart-stage--compact` (260px).
  No usar `style="height:Xpx"` inline: la altura vive en `--chart-height`.
- `.charts-grid` usa `grid-template-columns: repeat(auto-fit, minmax(340px, 1fr))`.
- Para gráfico único ancho completo: `<div class="charts-grid" style="grid-template-columns:1fr">`.
- **No usar** `.chart-card`, `.chart-card-light`, `.panel-chart-card` (clases legacy, no migrar nuevo código a ellas).

**Config de Chart.js — usar `App360Charts.create()` (obligatorio):**

`static/js/app_charts.js` se carga globalmente desde `base.html`. Es la única
fuente de verdad para paleta, ejes, leyendas, tooltips y etiquetas de datos.

**Nunca llamar a `new Chart()` directamente.** `create()` aplica la base,
registra las etiquetas, destruye la instancia previa y hace merge profundo de
las opciones, de modo que un override parcial no borra los defaults.

```javascript
const C = window.App360Charts;

chart = C.create(canvas, {
    type: 'bar',
    data: {
        labels,
        datasets: [{
            label: 'Importe',
            data: values,
            backgroundColor: C.semantic.neutralSoft,
            borderColor: C.semantic.neutral,
            borderWidth: 1,
            borderRadius: 4
        }]
    },
    options: {
        plugins: {
            tooltip: { callbacks: { label: ctx => C.format.money(ctx.parsed.y) } }
        }
    }
});
```

**Lo que `create()` garantiza (no redefinir en el template):**

| Aspecto | Valor fijo |
|---|---|
| Animación | desactivada |
| `responsive` / `maintainAspectRatio` | `true` / `false` |
| Interacción | `mode: 'index'`, `intersect: false` |
| Leyenda | abajo, punto, 12px, color `--color-text-muted` |
| Tooltip | fondo `rgba(37,54,74,.94)`, radio 6, padding 10 |
| Ejes | grid `#e6ebf0`, ticks 12px muted, sin borde |
| Tipografía | `system-ui`, 12px |
| Etiquetas de datos | plugin `app360DataLabels` activo |

**Regla de leyenda (automática):**
- Dona/torta → siempre visible.
- Barra/línea con 1 dataset → oculta.
- Barra/línea con 2+ datasets → visible abajo.
- Un `legend.display` explícito en el template siempre gana.

**API disponible:**

| Miembro | Uso |
|---|---|
| `C.create(canvas, config)` | Punto único de creación |
| `C.palette` | Serie 1–10 para categorías |
| `C.colorAt(i)` | Color de serie con wrap automático |
| `C.semantic` | `positive`, `negative`, `neutral`, `warning`, `metric`, `flow`, `previous` (+ `*Soft`) |
| `C.tokens` | `ink`, `body`, `muted`, `faint`, `grid`, `border`, `fontFamily`, `tickSize` |
| `C.baseOptions({horizontal, stacked, percent, legend})` | Solo si necesitás opciones sueltas |
| `C.dataLabels` | Plugin de etiquetas (ya incluido por `create`) |
| `C.format` | `money`, `compactMoney`, `number`, `compactNumber`, `percent` |

**Opciones propias del template:**

| Clave | Efecto |
|---|---|
| `dataLabels: false` | Desactiva las etiquetas de datos |
| `percent: true` | Formatea el eje de valores como porcentaje |
| `options.indexAxis: 'y'` | Barras horizontales (ajusta los ejes solo) |

**Reglas de color:**
- Nunca escribir hex en un template. Usar `C.semantic` o `C.palette`.
- Verde = ingreso/positivo, rojo = egreso/negativo, ámbar = advertencia,
  violeta = porcentaje/rentabilidad, cielo = neto/flujo. No reasignar.
- Para series categóricas (productos, clientes, instrumentos) usar `C.palette`.

**Verificación automática:**

```bash
python scripts/verify_chart_consistency.py
```

Recorre los 9 paneles con gráficos en un navegador real y falla si dos
gráficos difieren en leyenda, tooltip, ejes, tipografía o animación.

---

### 3.6 Table Card — `.table-card`

```html
<div class="table-card">
    <div class="table-card-head">
        <h3><i class="bi bi-table"></i> Título de la Tabla</h3>
        <!-- Opcional: acciones a la derecha -->
        <div class="d-flex justify-content-between align-items-center">
            <h3>...</h3>
            <button class="btn btn-sm btn-outline-secondary">...</button>
        </div>
    </div>
    <div class="scroll-table">   <!-- opcional: agrega sticky header + max-height:420px -->
        <table class="table table-hover mb-0">
            <thead>
                <tr>
                    <th>Columna</th>
                    ...
                </tr>
            </thead>
            <tbody id="miTabla">
                <tr><td colspan="N" class="text-center">
                    <span class="loading-text">Cargando…</span>
                </td></tr>
            </tbody>
        </table>
    </div>
</div>
```

**Reglas:**
- `<thead>` **sin** `class="table-dark"` ni `class="table-success"` ni colores Bootstrap.
  Los estilos del thead están en el DS: fondo `#f8fafc`, texto uppercase `#6b7280`.
- `table class="table table-hover mb-0"` — el `mb-0` evita margen dentro del card.
- El título del `table-card-head` usa `<h3>` (consistente con `.chart-card-v2`).
- `.scroll-table` agrega sticky header (thead `position: sticky; top: 0; z-index: 2`) y scroll vertical de `max-height: 420px`. Usar cuando la tabla puede crecer.
- **No usar** `<div class="card"><div class="card-header"><h5>` para envolver tablas.

---

### 3.7 Skeleton Loading

**En espera de datos AJAX — dos variantes:**

```html
<!-- Durante carga de KPIs -->
<div id="skeleton" class="kpi-grid">
    <div class="skeleton skeleton-kpi"></div>  <!-- height: 86px -->
    <div class="skeleton skeleton-kpi"></div>
    <div class="skeleton skeleton-kpi"></div>
    <div class="skeleton skeleton-kpi"></div>
</div>
<div id="content" style="display:none">
    <!-- contenido real -->
</div>
```

```html
<!-- En fila de tabla mientras carga -->
<tbody id="miTabla">
    <tr>
        <td colspan="N" class="text-center">
            <span class="loading-text">Cargando datos…</span>
        </td>
    </tr>
</tbody>
```

**En JS (función `cargar()`):**
```javascript
async function cargar() {
    document.getElementById('skeleton')?.classList.remove('d-none');
    document.getElementById('content')?.style.display = 'none';

    const data = await fetch('/api/...').then(r => r.json());

    document.getElementById('skeleton')?.classList.add('d-none');
    document.getElementById('content').style.display = '';

    renderKpis(data);
}
```

**Reglas:**
- **Nunca** texto "Cargando..." sin clase (es invisible y sin feedback visual).
- Usar `.loading-text` en celdas de tabla (shimmer en el texto).
- Usar `.skeleton.skeleton-kpi` / `.skeleton.skeleton-chart` para bloques de espera completos.

---

### 3.8 Empty State — `.empty-state`

Para tablas o secciones sin datos tras la carga.

```html
<tr id="emptyRow" style="display:none">
    <td colspan="N">
        <div class="empty-state">
            <i class="bi bi-inbox empty-icon"></i>
            <div class="empty-title">Sin registros aún</div>
            <div class="empty-text">
                No hay entradas para el período seleccionado.
            </div>
            <!-- Opcional: CTA para crear -->
            <button class="btn btn-sm btn-primary" onclick="abrirModal()">
                <i class="bi bi-plus-circle"></i> Registrar primero
            </button>
        </div>
    </td>
</tr>
```

**Reglas:**
- Icono con `.empty-icon`: `font-size: 2.5rem`, `color: #d1d5db`.
- `.empty-title`: `font-size: 1rem`, `font-weight: 600`, `color: #374151`.
- `.empty-text`: `font-size: 0.85rem`, `color: #9ca3af`, `max-width: 320px`.
- Siempre incluir CTA cuando la acción "crear primero" tiene sentido (no en vistas de solo lectura).
- **Nunca** dejar una tabla vacía con solo `No hay registros` en texto plano.

---

### 3.9 Sidebar

El sidebar está completamente definido en `base.html`. **No modificar su estructura** salvo cambios de navegación.

**Comportamiento:**
- Ancho expandido: `220px`. Colapsado: `56px`.
- Transición: `width 0.25s cubic-bezier(.4,0,.2,1)`.
- Al colapsar: se ocultan `.link-text`, `.sidebar-section-title`, `.sidebar-sep`, `.sidebar-user`.
- Tooltips al hover en modo colapsado: se generan automáticamente en JS desde el contenido de `.link-text`.
  No hace falta agregar `data-tooltip` manualmente — el script los inserta.

**Colores del sidebar:**
```css
background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
/* Link hover: */ background: rgba(255,255,255,0.08);
/* Link activo: */ background: rgba(37,99,235,0.2); color: #93c5fd;
/* Logout: */ color: #fca5a5; background: rgba(239,68,68,0.08);
```

**Items de nav:**
```html
<a href="/ruta" class="{% if current.startswith('/ruta') %}active-link{% endif %}">
    <span class="nav-icon"><i class="bi bi-[icon]"></i></span>
    <span class="link-text">Nombre</span>
</a>
```

---

### 3.10 Login Page

Standalone — **no extiende `base.html`**.

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- Bootstrap + Bootstrap Icons -->
    <style>
        body { background: #f1f5f9; display: flex; ... }
        .login-shell { background: #fff; border-radius: 1rem; box-shadow: 0 1px 3px ...; }
        /* Ver login.html para detalles completos */
    </style>
</head>
<body>
    <main class="login-shell">
        <div class="login-brand">
            <i class="bi bi-grid-3x3-gap-fill"></i>
            <span>App 360 · VyP</span>
        </div>
        <h1 class="login-subtitle">{{ title }}</h1>  <!-- UNA sola h1 -->
        ...
    </main>
</body>
```

**Reglas:**
- Fondo light `#f1f5f9` (coherente con el look del app, no dark glassmorphism).
- Card blanco con `box-shadow` sutil (no `rgba(2,6,23,0.7)` ni blur effects).
- Botón sólido sin `linear-gradient`.
- **Un solo `<h1>`** — error semántico tener dos en la misma página.
- Siempre `lang="es"`, `charset="UTF-8"`, `viewport`.

---

### 3.11 Modal System — `.app-modal` y `window.App360UI`

Los modals, confirmaciones y toasts del proyecto usan Bootstrap 5.3.1 como base, pero la capa visual y de interacción vive en `base.html`.
**Todo modal nuevo debe usar el sistema `app-modal`.**

```html
<div class="modal fade app-modal app-modal--blue" id="modalEjemplo" tabindex="-1" aria-labelledby="modalEjemploTitle" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header app-modal__header">
                <div class="app-modal__title-group">
                    <span class="app-modal__eyebrow">Operacion</span>
                    <h5 class="modal-title" id="modalEjemploTitle">Registrar movimiento</h5>
                    <p class="app-modal__subtitle">Usar subtitulo solo cuando agrega contexto real.</p>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
            </div>
            <div class="modal-body">
                ...
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-sm btn-outline-secondary" data-bs-dismiss="modal">Cancelar</button>
                <button type="button" class="btn btn-sm btn-primary">Guardar</button>
            </div>
        </div>
    </div>
</div>
```

**Variantes permitidas:**

| Clase | Uso |
|---|---|
| `app-modal--blue` | Acción principal, formularios neutros |
| `app-modal--sky` | Historiales, detalle, trazabilidad |
| `app-modal--green` | Confirmaciones positivas o cierres exitosos |
| `app-modal--amber` | Ajustes manuales, revisiones, advertencias suaves |
| `app-modal--danger` | Confirmaciones destructivas |
| `app-modal--neutral` | Casos secundarios sin peso semántico |

**Reglas:**
- No usar `bg-primary`, `bg-warning`, `bg-info`, `text-white` ni headers Bootstrap saturados dentro del modal.
- El acento visual vive en la línea superior del modal y en `.app-modal__eyebrow`, no en un bloque de color sólido.
- Los botones del footer son siempre `btn-sm`.
- Mantener máximo 2 acciones en el footer: cancelar + confirmar. Si hay más acciones, replantear el flujo.
- Usar `modal-dialog-centered` por defecto. Sumar `modal-lg` o `modal-dialog-scrollable` solo cuando el contenido realmente lo requiera.
- Los labels dentro del modal usan la tipografía compacta del sistema; no mezclar tamaños arbitrarios.

**Tamaños recomendados:**
- Default: formularios medianos y confirmaciones con algo de contexto.
- `modal-lg`: tablas, historiales, comparación de datos.
- `modal-sm`: solo confirmaciones muy cortas. Evitarlo si el texto necesita explicación.

**API compartida JS (`window.App360UI`):**

```javascript
App360UI.notify('Pago registrado correctamente.', 'success');

const ok = await App360UI.confirm({
    variant: 'danger',
    title: 'Eliminar pago',
    subtitle: 'La baja queda registrada en el historial.',
    message: 'Esta accion elimina el pago seleccionado y actualiza el saldo actual.',
    confirmText: 'Eliminar',
});

if (ok) {
    ...
}

const motivo = await App360UI.prompt({
    variant: 'warning',
    title: 'Solicitar anulación',
    subtitle: 'El motivo queda guardado junto con la solicitud.',
    message: 'Explica por qué debe anularse este movimiento.',
    label: 'Motivo',
    multiline: true,
    required: true,
    confirmText: 'Solicitar',
});
```

**Reglas de uso:**
- `App360UI.notify()` reemplaza `alert()` para feedback no bloqueante.
- `App360UI.confirm()` reemplaza `confirm()` para acciones destructivas o sensibles.
- `App360UI.prompt()` reemplaza `prompt()` cuando el flujo necesita pedir un dato breve o una justificación.
- `App360UI.openModal(id)` y `App360UI.closeModal(id)` son la vía preferida para aperturas programáticas.
- No crear toasts ni confirm modals por template si el caso entra en el sistema global.

---

### 3.12 Formulario compacto

**Receta.** Usar una grilla de dos columnas para altas completas de pocos campos y tres cuando
los controles son breves y entran sin comprimir sus etiquetas. La etiqueta va arriba
del control y usa `--font-size-label` (12 px); el texto de ayuda ocupa una línea y
explica una sola cosa. La unidad pertenece al campo: `ARS` o `$` solo para importes,
`cajas` y `kg` para medidas que no son dinero. No anteponer `$` a cajas ni kilos.

Validar en el mismo formulario. Con `novalidate`, cada error aparece junto al campo,
con texto, `aria-invalid` y una relación `aria-describedby`; el color nunca reemplaza
el mensaje. El pie ofrece una sola primaria y «Cancelar» como secundaria.

**Ejemplo de marcado.**

```html
<form novalidate>
  <div class="app-form-grid app-form-grid--cols-3">
    <label class="app-field">
      <span class="app-field__label">Período</span>
      <input class="app-field__control" name="periodo" type="month" required>
    </label>
    <label class="app-field">
      <span class="app-field__label">Cajas</span>
      <span class="app-input-unit">
        <input class="app-input-unit__control" name="cajas" inputmode="numeric" aria-describedby="cajas-ayuda">
        <span class="app-input-unit__suffix" aria-hidden="true">cajas</span>
      </span>
      <small id="cajas-ayuda">Meta mensual de cajas.</small>
    </label>
    <label class="app-field">
      <span class="app-field__label">Kilos</span>
      <span class="app-input-unit">
        <input class="app-input-unit__control" name="kilos" inputmode="numeric">
        <span class="app-input-unit__suffix" aria-hidden="true">kg</span>
      </span>
    </label>
    <label class="app-field app-form-grid__full">
      <span class="app-field__label">Importe</span>
      <span class="app-input-unit">
        <span class="app-input-unit__prefix" aria-hidden="true">$</span>
        <input class="app-input-unit__control" name="importe" inputmode="decimal"
               aria-invalid="true" aria-describedby="importe-error">
        <span class="app-input-unit__suffix" aria-hidden="true">ARS</span>
      </span>
      <small id="importe-error" role="alert">Ingresá un importe mayor que cero.</small>
    </label>
  </div>
  <div class="app-actions">
    <button class="app-actions__secondary" type="button">Cancelar</button>
    <button class="app-actions__primary" type="submit">Guardar</button>
  </div>
</form>
```

Para dos columnas, cambiar `app-form-grid--cols-3` por `app-form-grid--cols-2`;
ambas variantes y `app-form-grid__full` están en la hoja común.

**Hoy.** S2–S4: hay etiquetas legacy de 16 px junto a otras de 12 y 10,9 px; las altas
de Compras llegan a 1.180 px a 1440 y a 1.106 px a 1366, con el botón al final del
formulario; Ventas distribuye ocho campos en dos columnas desbalanceadas. S15 registra
ayudas repetidas y encontró `$` en medidas no monetarias solo en Objetivos. La
implementación actual separa `ARS`, `cajas` y `kg` en `static/js/objetivos_comerciales.js:14-16`;
la maqueta también deja `$` solo en Importe. Evidencia: `templates/compras_orden_nueva.html:6-79`,
`templates/ventas_form.html:6-72` e informe de relevamiento §3, S2–S4 y S15.

**Referencia de código.** La grilla y los campos son `.app-form-grid`, `.app-field` y
`.app-input-unit` de `static/css/app_components.css:1-90` (PR #26, mergeado en main).
El formulario de línea de objetivos se arma en `static/js/objetivos_comerciales.js:377`.

**Decisión.** D1: la primaria usa `--color-action`. D3: las altas completas (Compra,
Venta y Lead) usan una página compacta; los formularios breves de una sola vez pueden
seguir en modal con esta grilla; las altas repetitivas pasan al panel lateral.

---

### 3.13 Panel lateral

**Receta.** Usar el ancho `--drawer-width-form` para altas repetitivas y fijar arriba la entidad
y el contexto que no cambian durante la carga. El panel acompaña la tabla y conserva
«Guardar» como única primaria; «Cancelar» es secundaria. «Guardar y agregar otro» se
ofrece solo en un alta repetitiva y ocupa el lugar de «Guardar» como primaria, no se
suman dos primarias.

Al abrir, mover el foco al primer control útil. Escape cierra el panel y devuelve el
foco al control que lo abrió. Si hay cambios sin guardar, pedir confirmación con el
modal global `#app360ConfirmModal` mediante `App360UI.confirm()` (ver §3.11); si se
confirma el cierre, devolver el foco al origen. Mantener cabecera, cuerpo y pie en
zonas separadas y verificar que las acciones sigan accesibles al desplazarse; las
clases CSS no implementan por sí solas la trampa de foco, Escape ni el retorno de foco.

**Ejemplo de marcado.**

```html
<aside class="app-drawer" role="dialog" aria-modal="true" aria-labelledby="alta-title">
  <header class="app-drawer__header">
    <h2 class="app-drawer__title" id="alta-title">Alta de objetivo</h2>
    <p class="app-drawer__description">T-Ana · noviembre 2026</p>
  </header>
  <div class="app-drawer__body">
    <form class="app-form-grid app-form-grid--cols-2">
      <label class="app-field">
        <span class="app-field__label">Medida</span>
        <select class="app-field__control" name="medida">
          <option>Importe</option>
          <option>Cajas</option>
        </select>
      </label>
      <label class="app-field">
        <span class="app-field__label">Meta</span>
        <input class="app-field__control" name="meta" inputmode="decimal">
      </label>
    </form>
  </div>
  <footer class="app-drawer__footer">
    <div class="app-actions">
      <button class="app-actions__secondary" type="button">Cancelar</button>
      <button class="app-actions__primary" type="button">Guardar</button>
    </div>
  </footer>
</aside>
```

**Hoy.** S4: el alta de arqueo deja «Guardar arqueo» y «Cancelar» fuera de la ventana
a 1366×768. S11: Tesorería mantiene formularios de movimiento y arqueo duplicados
entre panel y páginas. Evidencia: `templates/tesoreria_arqueos.html:179-254`,
`templates/tesoreria_panel.html:116-163` e informe de relevamiento §3, S4 y S11.

**Referencia de código.** `.app-drawer` y sus zonas están en
`static/css/app_components.css:205-260` (PR #26, mergeado en main). El modal global de
confirmación está en `templates/base.html:2442`; su API se conecta en
`templates/base.html:3124`. Objetivos implementa el drawer con el ancho del token
en `static/css/objetivos_comerciales.css:103-108` y confirma el descarte en
`static/js/objetivos_comerciales.js:740-748` (PR #27, mergeado en main).

**Decisión.** D3: el panel se reserva para altas repetitivas de Productos, Stock,
Ubicaciones y Campañas; el contexto del vendedor/período queda fijo. El manejo de
foco, Escape y confirmación de borradores es parte obligatoria del comportamiento al
implementar el patrón, no una capacidad que agregue el CSS por sí solo.

---

### 3.13.1 Panel de alta repetitiva (SIS-2B, corte 1)

**Receta.** Las altas repetitivas (Producto hoy; Stock, Ubicaciones y Campañas en cortes siguientes)
se cargan en `.app-drawer` con el mismo formulario que su página de alta. Los campos viven en un
parcial de Jinja compartido, para que la página `/products/new` y el panel no diverjan:
`templates/_products_form_campos.html` (campos de producto), incluido por `templates/product_form.html`
y `templates/products_list.html`. El pie es `templates/_drawer_pie.html`: «Guardar y agregar otro»
ocupa la única primaria (`app-actions__primary`) y «Guardar» pasa a secundaria; «Cancelar» es secundaria.
Con las unidades faltantes, ambas acciones quedan deshabilitadas y el aviso del campo indica dónde crearlas.

**Mecanismo.** `static/js/app_drawer_form.js` expone `App360DrawerForm.crear({...})`. Por cada panel:

- el formulario del panel es el propio `.app-drawer` (`<form id="…" class="app-drawer" novalidate hidden>`,
  con `action` del endpoint de alta y `role="dialog" aria-modal="true"`);
- los disparadores llevan `data-drawer-open="<id del panel>"` (delegación: sirven también para botones
  que aparecen después, como el de estado vacío);
- el aviso aria-live va en `[data-drawer-status]` dentro del panel;
- cada campo con error tiene `<small class="app-field__error" data-error-campo="<campo>" hidden>`;
- los botones de envío llevan `data-accion="guardar"` o `data-accion="agregar"`;
- la configuración toma `primerCampo`, `conservar` (campos que se repiten tras «agregar otro»),
  `textoGuardado(cuerpo)`, `alGuardar(cuerpo, accion)` y `mensajeDescarte`.

Comportamiento: al abrir, el foco va al primer campo; Escape y «Cancelar» cierran; con datos sin guardar,
la confirmación usa `App360UI.confirm()` (§3.11) y, si se cancela, el panel sigue abierto; al cerrar, el
foco vuelve al disparador. Mientras se guarda, la acción pulsada muestra «Guardando…» y todos los botones
quedan deshabilitados. El envío es `fetch` con JSON, `Accept: application/json` y `X-CSRFToken`.
Si el servidor responde 422 con `errors`, cada aviso se muestra junto a su campo con `aria-invalid` y
`aria-describedby`, y el foco va al primero. Una respuesta que no es JSON (sesión vencida o sin permiso)
se informa en el aviso sin cerrar el panel. El texto de los avisos se asigna con `textContent`.

**Contrato de la ruta JSON.** `POST /products/new` con `Accept: application/json` (y cuerpo JSON o
formulario): `201 {"ok": true, "id": …, "nombre": …}`; datos inválidos, `422 {"ok": false,
"errors": {"campo": "mensaje"}}` con los campos `name`, `business_unit_id` o `sku`. Sin sesión, la app
responde con su redirección habitual; sin permiso, 403 o redirección. El formulario HTML sin esa cabecera
conserva su redirect a la lista y el aviso con 400. Validación y persistencia son las mismas
(`crear_producto_desde_pedido` en `blueprints/products.py`).

**Lista.** Tras guardar, la región `[data-products-region]` se reemplaza con la tabla fresca de `/products`
(el panel no se cierra al agregar otro) y la fila nueva queda resaltada unos segundos
(`app-table__row--resaltada`). Los filtros no existen hoy: si aparecen, el refresco debe conservarlos.

**Alcance de este corte.** Solo PC (1440×900 y 1366×768). Sin cambios de modelos ni migraciones.
Para los cortes siguientes: replicar el parcial de campos, el pie y el bloque `<form class="app-drawer">`
de `templates/products_list.html`, y configurar `App360DrawerForm.crear` con el endpoint y los campos propios.

**Hoy.** Productos: la página `/products/new` y el panel comparten campos; el alta repetitiva ya no
requiere un recorrido de pantalla por producto.

**Referencia de código.** `static/js/app_drawer_form.js`; `static/css/app_components.css` (`.app-drawer`,
`.app-drawer__footer` pegado al pie, `.app-table__row--resaltada`); `templates/products_list.html`;
`templates/_products_form_campos.html`; `templates/_drawer_pie.html`; `blueprints/products.py`.
Patrón de referencia de foco y Escape: `static/js/objetivos_comerciales.js` (panel de objetivos).

**Decisión.** D3 (Inti): altas repetitivas en panel lateral. En «Guardar y agregar otro» se conservan la
unidad de negocio y la categoría (se repiten en una carga por lote) y se limpian SKU y nombre.

### 3.14 Tabla de resumen por entidad

**Receta.** Mostrar una entidad por fila y definir las columnas una sola vez con anchos explícitos.
Las filas de detalle repiten el orden de columnas de su entidad; los valores numéricos
se alinean a la derecha y usan cifras tabulares. La fila de total va en el pie de la
tabla y representa la suma real, no el promedio de porcentajes. Las filas expandibles
se abren con un botón que actualiza `aria-expanded` y referencia su detalle con
`aria-controls`. El total no se repite en tarjetas KPI.

**Ejemplo de marcado.**

```html
<table class="app-table">
  <colgroup><col width="40%"><col width="30%"><col width="30%"></colgroup>
  <thead class="app-table__head">
    <tr>
      <th class="app-table__head-cell" scope="col">Vendedor</th>
      <th class="app-table__head-cell app-table__numeric" scope="col">Meta</th>
      <th class="app-table__head-cell app-table__numeric" scope="col">Realizado</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th class="app-table__cell" scope="row">
        <button class="app-table__toggle" type="button" aria-expanded="false" aria-controls="detalle-ana">
          Ana <span class="app-table__chevron" aria-hidden="true">⌄</span>
        </button>
      </th>
      <td class="app-table__cell app-table__numeric">$ 1.500.000</td>
      <td class="app-table__cell app-table__numeric">$ 900.000</td>
    </tr>
    <tr class="app-table__expandable" id="detalle-ana" hidden>
      <td class="app-table__cell"><div class="app-table__detail">Producto X</div></td>
      <td class="app-table__cell app-table__numeric">$ 900.000</td>
      <td class="app-table__cell app-table__numeric">$ 500.000</td>
    </tr>
  </tbody>
  <tfoot>
    <tr class="app-table__total">
      <th class="app-table__cell" scope="row">Equipo</th>
      <td class="app-table__cell app-table__numeric">$ 1.500.000</td>
      <td class="app-table__cell app-table__numeric">$ 900.000</td>
    </tr>
  </tfoot>
</table>
```

**Hoy.** S8: el formato y la alineación numérica varían por pantalla. S9: Liquidaciones
muestra cuatro KPI de totales y no los lleva a una fila de total en la tabla.
Evidencia: `templates/rrhh_liquidaciones.html:35-39`,
`templates/rrhh_liquidaciones.html:219-232` e informe de relevamiento §3, S8–S9.

**Referencia de código.** `.app-table`, `.app-table__numeric`, `.app-table__total` y
la fila expandible están en `static/css/app_components.css:95-168` (PR #26, mergeado en
main). El cálculo del resumen por equipo se mantiene en el JS de Objetivos, integrado
con la fila total del template.

**Decisión.** D4: el total vive en la tabla y no se duplica en KPI. D6: Leads conserva
su kanban; esta receta no lo reemplaza por una tabla. D7 queda pendiente de decisión
del dueño para crear la vista de Comisiones y para renombrar uno de los dos ítems
«Tesorería» del menú; esta regla visual no decide producto ni navegación.

---

### 3.15 Estado punto + texto

**Receta.** En tablas, listas y avisos, mostrar un punto de `--state-dot-size` junto a un rótulo
legible. El punto es decorativo (`aria-hidden="true"`); el texto porta el significado
y permanece neutro. El tono comunica la variante, nunca reemplaza la palabra. Usar
`--color-positive` para `ok`, `--color-warning` para `warn`, `--state-error-ink` para
`error` y `--color-text-faint` para `neutral`; el punto conserva la forma de
`--radius-pill`.

| Texto visible | Variante | Ejemplo de uso |
|---|---|---|
| Cumplido, En ritmo | `ok` | Resultado positivo |
| Por debajo del ritmo esperado, No cumplido, Pendiente | `warn` | Requiere atención |
| Falta, Rechazado | `error` | Error o rechazo explícito |
| Sin meta, No iniciado, Inactivo, Anulado | `neutral` | Vacío o cierre normal |

**Ejemplo de marcado.**

```html
<span class="app-status app-status--ok">
  <span class="app-status__dot" aria-hidden="true"></span>Cumplido
</span>
<span class="app-status app-status--neutral">
  <span class="app-status__dot" aria-hidden="true"></span>Sin meta
</span>
```

«Sin meta» no es cero: la meta y el avance se muestran como «—», nunca como 0 %.
Los estados desconocidos usan el tono neutral y conservan un rótulo visible; no se
muestran claves internas ni píldoras saturadas.

**Hoy.** S10: Tesorería y Accesos usan píldoras de color para estados y permisos.
Objetivos distingue «Sin meta» como un estado separado. Evidencia:
`templates/tesoreria_movimientos.html:504-507`, `templates/admin/admin_accesos.html:39-47`,
`static/js/objetivos_comerciales.js:19-27` e informe de relevamiento §3, S10.

**Referencia de código.** Las cuatro variantes de punto viven en
`static/css/app_components.css:171-204` (PR #26, mergeado en main). El mapa de estados
de `App360Status.statusDot()` está en `static/js/app_status.js:5-61` (PR #25, mergeado
en main).

**Decisión.** D5: usar punto + texto, con tono de estado en el punto y texto neutro;
los cierres normales quedan neutrales. D7 queda pendiente de decisión del dueño para
resolver si Leads separa «etapa» de «estado» o los unifica; esta guía no cambia el
vocabulario del producto.

---

### 3.16 Acciones

**Receta.** Ubicar las acciones de pantalla arriba a la derecha y dejar una sola primaria en la
pantalla activa. Al abrir un panel lateral, la primaria de la página pasa a secundaria
y el panel recibe la única primaria. «Guardar» permanece deshabilitado mientras no
haya cambios. Borrar y anular son acciones secundarias y siempre piden confirmación
con el sistema global de §3.11.

**Ejemplo de marcado (panel abierto).** La primaria de cabecera pasa a secundaria y
la acción principal queda en el pie del panel.

```html
<header class="app-page-head">
  <h1 class="app-page-head__title">Objetivos</h1>
  <div class="app-page-head__actions">
    <div class="app-actions">
      <button class="app-actions__secondary" type="button">Exportar</button>
      <button class="app-actions__secondary" type="button">Agregar objetivo</button>
    </div>
  </div>
</header>
<div class="app-actions">
  <button class="app-actions__secondary" type="button">Cancelar</button>
  <button class="app-actions__primary" type="submit" disabled>Guardar</button>
</div>
```

Para borrar o anular, mantener el control secundario y confirmar con
`App360UI.confirm({variant: 'danger', ...})`, que usa `#app360ConfirmModal`. Al abrir
un drawer, no dejar la primaria de cabecera activa en paralelo.

**Hoy.** S1 y S5: conviven varios colores y ubicaciones de primarias. S6: Compras,
Gastos y Tesorería duplican acciones; Accesos llega a siete «Guardar» visibles. S7:
el relevamiento no encontró seguimiento transversal de cambios en `templates/`.
Evidencia:
`templates/compras_overview.html:15-16`, `templates/compras_overview.html:123`,
`templates/admin/admin_accesos.html:52-54`
e informe de relevamiento §3, S1 y S5–S7.

**Referencia de código.** La cabecera y las variantes de acción están en
`static/css/app_components.css:267-318` (PR #26, mergeado en main). La confirmación
compartida está en `templates/base.html:2442` y `templates/base.html:3124`.

**Decisión.** D1: toda primaria toma `--color-action`. D3: al abrir el panel, la acción
principal queda en el panel; «Guardar y agregar otro» reemplaza a «Guardar» en altas
repetitivas y no crea una segunda primaria. D7 queda pendiente de decisión del dueño
para fijar los valores cerrados de «Moneda» y «Estado» de Ventas; el patrón de acciones
no define esas opciones de producto.

---

### 3.17 Números es-AR

**Receta.** Para valores visibles, usar `App360Format` como formateador común: importe sin centavos
por defecto, porcentaje entero cuando alcanza y «—» para vacío o no disponible. Los
porcentajes reciben una proporción (0,62 representa 62 %). Para cajas, kilos y otros
conteos, usar `formatNumber`; no anteponer `$`. Se habilitan decimales solo cuando la
unidad o la operación los necesita de verdad. En tablas, alinear cifras a la derecha
con cifras tabulares.

**Ejemplo de salida.**

```javascript
App360Format.formatARS(1500);                       // "$ 1.500"
App360Format.formatARS(null);                       // "—"
App360Format.formatPercent(0.62);                   // "62 %"
App360Format.formatNumber(1234.56, {decimales: 2}); // "1.234,56"
App360Format.formatARS(1234.56, {decimales: 2});    // "$ 1.234,56"
```

**Ejemplo de marcado.** La celda usa la alineación tabular de la tabla y muestra el
resultado ya formateado.

```html
<td class="app-table__cell app-table__numeric">$ 1.500</td>
```

**Hoy.** S8: se midieron seis formatos; hay `$250000.50`, cifras con coma y punto
mezclados y celdas numéricas sin alineación uniforme. S15 confirma que `$` se reserva
para dinero, no cajas ni kilos. Evidencia:
`templates/rrhh_liquidaciones.html:219-232`,
`static/js/objetivos_comerciales.js:30-35` e informe de relevamiento §3, S8 y S15.

**Referencia de código.** `App360Format.formatARS`, `formatNumber` y `formatPercent`
están en `static/js/app_format.js:1-51` (PR #25, mergeado en main). La alineación tabular está en
`static/css/app_components.css:120-124` (PR #26, mergeado en main).

**Decisión.** Mantener el formato es-AR en toda la app: pesos sin centavos por defecto,
porcentajes enteros y vacío como «—»; los decimales se piden explícitamente cuando el
dato los requiere. D7 queda pendiente de decisión del dueño para las opciones de
Moneda y Estado de Ventas; el formateador numérico no las elige.

### 3.18 Tipo de movimiento — `.app-tipo`

**Receta.** Para el tipo de un movimiento de caja (Ingreso o Egreso), usar un chip propio con
fondo suave y texto en negrita. `.app-tipo--ingreso` pinta el texto con `--color-positive-ink`
sobre `--color-positive-soft`, y `.app-tipo--egreso` lo pinta con `--state-error-ink` sobre
`--color-negative-soft`. Ambos pares superan 4,5:1 para texto. El monto va al lado con signo
(«+» para ingreso, «−» para egreso) en el mismo color (`.app-tipo__monto--ingreso` y
`--egreso`), alineado a la derecha con cifras tabulares. La fila activa lleva un borde izquierdo
de 3 px en `--color-positive` (`.app-tipo-fila--ingreso`) o en `--color-negative`
(`.app-tipo-fila--egreso`). La fila anulada (`.app-tipo-fila--anulado`) pasa el chip y el monto a
gris `--color-text-muted` y tachado, igual que el resto de la fila.

**Ejemplo de marcado.**

```html
<span class="app-tipo app-tipo--ingreso">Ingreso</span>
<span class="app-tipo__monto app-tipo__monto--ingreso">+ $ 1.500,00</span>
<span class="app-tipo app-tipo--egreso">Egreso</span>
<span class="app-tipo__monto app-tipo__monto--egreso">− $ 120,00</span>
```

**Alcance.** El tipo no es un estado: Activo, Anulado y Pend. anulación siguen con
`app-status` (§3.15), en su propia columna. Tesorería usa este componente en Movimientos y en el
panel («Últimos Movimientos»).

**Referencia de código.** Estilos en `static/css/app_components.css` (bloque «Tipo de
movimiento»). Marcado en `TesoreriaForms.tipoHtml`, `montoHtml` y `claseFila` de
`static/js/tesoreria_forms.js`. Los importes siguen a `App360Format`.

---

## 4. Patrones Prohibidos (Anti-Patterns)

Los siguientes patrones Bootstrap por defecto están **explícitamente prohibidos** en este proyecto.
Si aparecen en un template, deben migrarse al DS.

### ❌ KPIs con colores Bootstrap saturados
```html
<!-- PROHIBIDO -->
<div class="card bg-danger text-white">
<div class="card bg-success text-white">
<div class="card bg-info text-white">
<div class="card bg-warning text-dark">
<div class="card border-left-success">     <!-- variante "border-left" también prohibida -->
```
```html
<!-- CORRECTO -->
<div class="kpi-card accent-red">
<div class="kpi-card accent-green">
<div class="kpi-card accent-blue">
<div class="kpi-card accent-amber">
```

### ❌ Tabla con cabecera oscura Bootstrap
```html
<!-- PROHIBIDO -->
<table class="table">
    <thead class="table-dark">
<table class="table table-striped">
    <thead class="table-success">
```
```html
<!-- CORRECTO — el .table-card aplica estilos al thead automáticamente -->
<div class="table-card">
    <div class="scroll-table">
        <table class="table table-hover mb-0">
            <thead>
```

### ❌ Card container para gráfico
```html
<!-- PROHIBIDO -->
<div class="card">
    <div class="card-header"><h5>Gráfico</h5></div>
    <div class="card-body"><canvas id="chart"></canvas></div>
</div>
```
```html
<!-- CORRECTO -->
<div class="chart-card-v2">
    <h3>Gráfico</h3>
    <div style="height:300px"><canvas id="chart"></canvas></div>
</div>
```

### ❌ Botones de período con btn-group
```html
<!-- PROHIBIDO -->
<div class="btn-group">
    <button class="btn btn-primary">Mes</button>
    <button class="btn btn-outline-primary">Trim</button>
</div>
```
```html
<!-- CORRECTO -->
<div class="period-bar dim-bar">
    <div class="period-pills">
        <button class="pp active" data-period="mes">Mes</button>
        <button class="pp" data-period="trim">Trim</button>
    </div>
</div>
```

### ❌ Header de página sin panel-header
```html
<!-- PROHIBIDO -->
<h1 class="mb-4">Título</h1>
<div class="d-flex justify-content-between align-items-center mb-4">
    <h1>Título</h1>
    <div>...</div>
</div>
```
```html
<!-- CORRECTO -->
<div class="panel-header">
    <div>
        <h1><i class="bi bi-icon"></i> Título</h1>
        <span>Subtítulo descriptivo</span>
    </div>
    ...
</div>
```

### ❌ Headers de modal Bootstrap legacy
```html
<!-- PROHIBIDO -->
<div class="modal-header bg-primary text-white">
<div class="modal-header bg-warning text-dark">
<div class="modal-header bg-info text-white">
```
```html
<!-- CORRECTO -->
<div class="modal fade app-modal app-modal--blue">
    <div class="modal-header app-modal__header">
        <div class="app-modal__title-group">
            <span class="app-modal__eyebrow">Operacion</span>
            <h5 class="modal-title">Titulo</h5>
            <p class="app-modal__subtitle">Contexto breve</p>
        </div>
    </div>
</div>
```

### ❌ `alert()`, `confirm()` y `prompt()` nativos del navegador
```javascript
// PROHIBIDO
alert('Error al guardar');
if (!confirm('¿Eliminar registro?')) return;
const motivo = prompt('Motivo de la anulación:');
```
```javascript
// CORRECTO
App360UI.notify('Error al guardar', 'danger');

const ok = await App360UI.confirm({
    variant: 'danger',
    title: 'Eliminar registro',
    message: 'Esta accion no se puede deshacer.',
    confirmText: 'Eliminar',
});

if (!ok) return;

const motivo = await App360UI.prompt({
    title: 'Solicitar anulación',
    label: 'Motivo',
    multiline: true,
    required: true,
});
```

### ❌ Estilos inline en templates hijos
```html
<!-- PROHIBIDO -->
<style>
    .mi-kpi-card { border-left: 4px solid #dc2626; }
    .mi-tabla { background: #0f172a; }
</style>
```
```
CORRECTO: extender el DS en base.html si el componente es reutilizable,
o usar clases existentes.
```

### ❌ Texto de carga sin feedback visual
```html
<!-- PROHIBIDO -->
<tr><td colspan="5" class="text-center">Cargando...</td></tr>
```
```html
<!-- CORRECTO -->
<tr><td colspan="5" class="text-center">
    <span class="loading-text">Cargando datos…</span>
</td></tr>
```

### ❌ Formulario operativo a todo el ancho

Una alta extendida a todo el contenido obliga a recorrer la página para guardar.
Usar `app-form-grid--cols-2` o `app-form-grid--cols-3` según la longitud de los
controles y mantener las etiquetas arriba.

### ❌ Primaria duplicada

No repetir «Guardar» o «Nuevo» en cabecera, pie y filas de la misma pantalla. Al abrir
un drawer, la cabecera pierde la primacía y el panel queda con una sola acción primaria.

### ❌ Píldoras saturadas como portadoras del estado

No usar `badge bg-success`, `badge bg-warning` ni otras píldoras de color en tablas y
listas. El estado se expresa con punto decorativo y texto visible (§3.15).

### ❌ Importes con `toFixed(2)` o `toLocaleString()` sueltos

No construir formatos monetarios por pantalla. Usar `App360Format` (§3.17), con
decimales explícitos solo cuando el dato los necesita; las medidas que no son dinero
no llevan `$`.

### ❌ Recarga completa que descarta borradores

No recargar la página o la lista para actualizar una fila si hay borradores o cambios
abiertos: conservarlos y actualizar solo la entidad afectada. S14 registra
`location.reload()` en `templates/admin/admin_modulo.html:511`,
`templates/admin/admin_modulo.html:537` y `templates/admin/admin_modulo.html:609`; el
informe aclara que allí no se reprodujo el descarte de borradores, porque las altas
usan modales. No atribuirle una pérdida no observada; aplicar esta regla donde sí haya
edición abierta.

---

## 5. Guía de Migración Rápida

Cuando se encuentra un template antiguo, aplicar este checklist en orden:

### Paso 1 — `/harden` (metadatos)
- [ ] `<html lang="es">`
- [ ] `<meta charset="UTF-8">`
- [ ] `<meta name="viewport" content="width=device-width, initial-scale=1">`
- [ ] Un solo `<h1>` por página

### Paso 2 — `/normalize` (componentes)
- [ ] Reemplazar header con `.panel-header`
- [ ] Reemplazar `card bg-X text-white` con `.kpi-card.accent-*`
- [ ] Reemplazar `btn-group` períodos con `.period-bar > .period-pills > .pp`
- [ ] Reemplazar `card > card-body > canvas` con `.chart-card-v2`
- [ ] Reemplazar `card > card-header > table-dark` con `.table-card + .scroll-table`
- [ ] Eliminar bloques `<style>` inline en templates hijos
- [ ] Reemplazar botones de acciones con `.action-bar btn-sm`

### Paso 3 — `/arrange` (jerarquía)
- [ ] Si hay 5+ KPIs iguales: separar en hero (2 max) + secondary
- [ ] Si el gráfico más importante no está primero: reordenar
- [ ] Asegurar que el bloque más crítico está arriba del fold

### Paso 4 — `/onboard` (empty states)
- [ ] Agregar `.empty-state` con icono + título + texto + CTA en toda tabla vacía
- [ ] Cambiar `Cargando...` por `<span class="loading-text">Cargando…</span>`
- [ ] Agregar skeleton loading en fetch() si el panel tiene KPIs

### Paso 5 — `/polish` (detalles finales)
- [ ] Confirmar consistencia de íconos (Bootstrap Icons en todos lados)
- [ ] Confirmar que todos los `btn-sm` en barras de acción
- [ ] Confirmar subtítulo en `.panel-header`

---

## 6. Estructura de Archivos de Templates

```
templates/
├── base.html                  ← Design System completo (CSS + layout + sidebar)
├── login.html                 ← Standalone (no extiende base)
│
├── [Paneles Estratégicos - ya migrados al DS]
│   ├── bi_dashboard.html       ← kpi-grid-hero + kpi-grid-secondary + charts-grid
│   ├── dashboard_comercial.html
│   ├── dashboard_financiero.html
│   └── panel_ejecutivo.html
│
├── [Módulos Operativos - migrados]
│   ├── gastos_panel.html
│   ├── tesoreria_panel.html
│   ├── tesoreria_arqueos.html
│   ├── tesoreria_movimientos.html
│   ├── cta_cte_friar.html
│   ├── compras_overview.html
│   ├── ventas_list.html
│   ├── rrhh_panel.html
│   └── rrhh_liquidaciones.html
│
└── admin/
    ├── admin_dashboard.html
    ├── admin_accesos.html
    └── admin_modulo.html
```

**Templates pendientes de revisión futura:**
- `rrhh_adelantos.html`, `rrhh_empleados.html`, `rrhh_ausentismo.html`
- `compras_panel.html`, `compras_detail.html`, `compras_orden_nueva.html`
- `stock_list.html`, `stock_form.html`, `products_list.html`, `product_form.html`
- `leads_list.html`, `lead_form.html`, `lead_detail.html`, `campaigns_list.html`
- `objetivos_ventas.html`, `ventas_form.html`, `venta_detail.html`
- `sabiogo_admin.html`, `locations_list.html`, `location_form.html`

---

## 7. Relación con las Skills de Impeccable

Este proyecto usa las **skills del agente Impeccable** para decisiones de diseño.
Son el marco teórico; este archivo es la aplicación concreta al proyecto.

| Skill | Qué resuelve | Cómo se aplica aquí |
|---|---|---|
| `/normalize` | Llevar templates al DS | Migrar `card bg-X`, `table-dark`, `btn-group` a las clases del §3 |
| `/harden` | Robustez técnica | `lang`, `viewport`, `charset`, un solo `<h1>` |
| `/arrange` | Jerarquía visual | Hero KPIs (§3.4) → secondary KPIs; gráfico principal arriba |
| `/onboard` | Primeras experiencias | Empty states (§3.8) + skeleton loading (§3.7) |
| `/extract` | Consolidar componentes | Nuevos patrones reutilizables van a `base.html`, nunca en templates hijos |
| `/polish` | Calidad final | Íconos consistentes, `btn-sm` uniforme, subtítulos en headers |
| `/critique` | Auditoría de calidad | Evaluar con escala de Nielsen; referirse a §4 (anti-patterns) |
| `/colorize` | Uso de color | Solo los 6 acentos del §3.4; nunca añadir colores ad-hoc |
| `/distill` | Simplificación | Si un template tiene `<style>` inline, extraer o eliminar |
| `/teach-impeccable` | Setup inicial | Generó este archivo; actualizar cuando cambien las convenciones |

**Para usar una skill de Impeccable en este proyecto:**
1. Leer el `SKILL.md` correspondiente.
2. Aplicar sus instrucciones **en el contexto de este DS**: las clases y tokens ya están definidas, no inventar nuevas.
3. Si la skill sugiere un patrón que no existe en este DS, agregar la sección correspondiente a `base.html` y documentarla en este archivo.

---

## 8. Paleta de Colores Completa

Los valores viven en `:root` de `templates/base.html`. **Nunca escribir hex en
un template**: usar `var(--color-*)`.

```
/* Superficies */
--color-surface:          #ffffff
--color-surface-subtle:   #f3f6fa   (filtros, encabezados de tabla)
--color-surface-muted:    #f8fafc   (thead, inputs)
--color-surface-sunken:   #eff4f8

/* Textos */
--color-text-primary:     #25364a   (títulos, valores de KPI)
--color-text-body:        #334155   (contenido general)
--color-text-muted:       #58677a   (labels, subtítulos)
--color-text-faint:       #8a97a6   (kpi-sub, empty-text)

/* Bordes */
--color-border:           #dce3eb
--color-border-soft:      #e2e8f0
--color-border-control:   #bcc9d6

/* Acción e interacción */
--color-action:           #234e70   (acento global)
--color-action-hover:     #1b3d59
--color-action-soft:      #eaf0f5
--color-focus:            #3d7aa9
--color-hover:            #edf2f7

/* Acentos semánticos (código de color operativo) */
--color-positive:         #16a34a   (ingreso, positivo)
--color-positive-ink:     #15803d   (texto verde sobre fondos suaves: ≥ 4,5:1; §3.18)
--color-negative:         #dc2626   (egreso, negativo)
--color-warning:          #f59e0b   (advertencia)
--color-metric:           #7c3aed   (porcentajes, rentabilidad)
--color-flow:             #0ea5e9   (neto, flujo de caja)

/* Estados */
--state-attention-bg/ink: #fff2dc / #7b5016
--state-active-bg/ink:    #eaf4ef / #286149
--state-error-bg/border/ink: #fff3f0 / #d7a8a2 / #8c3027

/* Tipografía */
--font-size-body: 14px   --font-size-label: 12px   --font-size-note: 13px
--font-size-section: 18px   --font-size-title: 28px   --font-size-page: 24px
--font-weight-strong: 650   --font-weight-page: 700

/* Forma */
--radius-badge: 4px   --radius-control: 6px   --radius-table: 7px
--radius-panel: 8px   --radius-pill: 999px

/* Controles y espaciado */
--control-height: 38px   --control-height-touch: 44px   --control-height-compact: 26px
--space-control: 12px   --space-section: 28px   --content-max: 1500px

/* Gráficos */
--chart-height: 300px   --chart-height-tall: 380px   --chart-height-mobile: 240px
--chart-grid: #e6ebf0

/* Sidebar (sin cambios) */
--sidebar-from:   #0f172a
--sidebar-to:     #1e293b
--sidebar-link:   #cbd5e1
--sidebar-active-bg: rgba(37,99,235,0.2)
--sidebar-active-text: #93c5fd
```

**Alias heredados**: `--app-surface-0/1/2`, `--app-border-soft/strong`,
`--app-ink-strong/ink/ink-muted` apuntan a los tokens nuevos. Se conservan para
no romper estilos existentes; el código nuevo usa `--color-*`.

**Excepción documentada**: las pills de período (`.pp`) mantienen 26px de alto
aunque `--control-height` sea 38px. Son filtros compactos, no botones de acción.

### 8.1 Normalización transversal de paneles y filtros

`static/css/paneles_normalizados.css` es la capa común para encabezados, filtros,
controles de período/dimensiones y métricas de panel. Carga desde `base.html`; los
paneles comerciales con CSS propio la cargan después de `comercial_paneles.css`.

- Encabezados `.panel-header` y `.com-heading` comparten escala de título,
  subtítulo, espaciado y alineación.
- Filtros `.period-bar` y `.com-filter` comparten superficie sutil, borde,
  radio, etiquetas y espaciado desde tokens; inputs respetan controles estándar.
- Filtros compactos conservan su rol y opciones, pero los colores, bordes y foco
  heredan tokens de tema.
- Métricas comerciales (`.com-metrics`) usan la misma superficie, borde,
  tipografía y grid de KPI que el resto de los paneles.
- No alterar contenido, acciones, filtros, tablas, datos ni gráficos por motivo
  de normalización visual.

Validación visual/técnica: `python scripts/verify_chart_consistency.py` y los
selectores de tests de paneles disponibles en `tests/`.

---

*Última actualización: 20 de noviembre de 2026 — App 360 v1.x*
*Generado con la skill `teach-impeccable` + revisión manual post-migración completa de templates.*
