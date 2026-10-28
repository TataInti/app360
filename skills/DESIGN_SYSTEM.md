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

*Última actualización: Abril 2026 — App 360 v1.x*
*Generado con la skill `teach-impeccable` + revisión manual post-migración completa de templates.*
