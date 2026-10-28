# Tokens de diseño comercial

> **Estado: aprobado y aplicado a todo el sitio (octubre 2026).**
> Los valores viven en `:root` de `templates/base.html` y en
> `static/js/app_charts.js`. Este documento registra el origen y las
> correcciones aplicadas. Para el uso vigente ver `skills/DESIGN_SYSTEM.md` §8.

Este documento describe los valores que originalmente usaban **Panel de ventas** y
**Seguimiento de clientes**, y que hoy son la base del sistema de diseño de APP360.
Los componentes heredan la familia tipográfica y parte de la base de Bootstrap desde
la aplicación.

La implementación de los paneles comerciales está acotada a
`static/css/comercial_paneles.css` y a los gráficos de
`static/js/comercial_paneles.js`. El resto del sitio consume los mismos tokens
desde `base.html` y `static/js/app_charts.js`.

## Color

| Rol | Valor actual | Uso |
|---|---|---|
| Texto principal | `#25364a` | Texto y títulos |
| Texto secundario | `#58677a` | Notas y etiquetas |
| Acento | `#234e70` | Acciones principales, enlaces y selección |
| Borde | `#dce3eb` | Separadores y contornos |
| Superficie | `#ffffff` | Fondo de tabla, panel y detalle |
| Superficie suave | `#f3f6fa` | Filtros y encabezados de tabla |
| Borde de control | `#bcc9d6` | Campos y botones |
| Foco de teclado | `#3d7aa9` | Indicador `:focus-visible` |
| Hover de control | `#edf2f7` | Fondo al pasar el puntero |
| Etiqueta de dato | fondo `rgba(255,255,255,.94)`, texto `#25364a`, borde `#dce3eb` o color de serie | Etiquetas fuera de las series; el texto conserva alto contraste |
| Atención | fondo `#fff2dc`, texto `#7b5016` | Señales que requieren revisión |
| Activo | fondo `#eaf4ef`, texto `#286149` | Estado de actividad reciente |
| Error | fondo `#fff3f0`, borde `#d7a8a2`, texto `#8c3027` | Error con opción de reintento |
| Gráficos, serie 1–10 | `#234e70`, `#4f8095`, `#769b82`, `#a97c3f`, `#9b7180`, `#667b91`, `#7a8a4f`, `#bf8065`, `#7d8fa3`, `#7f7c55` | Series de barras, líneas y mix |

### Correcciones aplicadas a la paleta de series

| Posición | Valor original | Valor final | Motivo |
|---|---|---|---|
| 4 | `#c59557` | `#a97c3f` | 2.70:1 sobre blanco, no alcanzaba 3:1 (WCAG 1.4.11) |
| 7 | `#96a66b` | `#7a8a4f` | 2.64:1 sobre blanco |
| 9 | `#667b91` | `#7d8fa3` | Repetía el color de la posición 6 |
| 10 | `#9d9a73` | `#7f7c55` | 2.88:1 sobre blanco |

Contraste final de la serie sobre `#ffffff`: 8.76, 4.33, 3.10, 3.73, 4.14,
4.36, 3.77, 3.24, 3.32 y 4.28 — todas ≥ 3:1.

### Contraste de estados

| Rol | Combinación | Ratio | AA texto normal |
|---|---|---:|---|
| Texto principal | `#25364a` sobre `#ffffff` | 11.4:1 | ✓ |
| Texto secundario | `#58677a` sobre `#ffffff` | 5.6:1 | ✓ |
| Atención | `#7b5016` sobre `#fff2dc` | 6.4:1 | ✓ |
| Activo | `#286149` sobre `#eaf4ef` | 5.9:1 | ✓ |
| Error | `#8c3027` sobre `#fff3f0` | 7.1:1 | ✓ |
| Acento | `#234e70` sobre `#ffffff` | 8.8:1 | ✓ |

## Tipografía

| Uso | Tamaño actual | Peso / detalle |
|---|---:|---|
| Texto base y cuerpo de tabla | 14 px | Normal |
| Título principal | 28 px escritorio; 25 px hasta 600 px | 650 |
| Título de sección | 18 px | 650 |
| Subtítulo de gráfico | 16 px | 650 |
| Etiqueta de tabla y campo | 12 px | 650 |
| Nota y subtítulo auxiliar | 13 px | Normal |
| Texto auxiliar pequeño | 12 px | Normal |
| Etiqueta de dato en gráfico | 11 px | 600; valores compactos, fondo claro y sin superposición |
| Métrica principal | `clamp(22px, 2.3vw, 30px)` | 650, números tabulares |

## Espaciado y forma

| Elemento | Valor actual |
|---|---:|
| Unidad de control | 38 px de alto; 44 px en móvil |
| Espacio de controles en filtros | 12 px; relleno 16 px (12 px en móvil) |
| Separación de secciones | 28 px arriba y 20 px de relleno superior |
| Relleno de celdas | 12 × 10 px; 10 × 8 px bajo 1100 px |
| Bordes | 1 px |
| Radios | 4 px en insignias; 6 px en controles/errores; 7 px en tablas; 8 px en filtros |
| Gráficos | 290–300 px; gráficos apilados 380 px; móvil 240–320 px según el bloque |
| Ancho máximo de contenido | 1500 px |

Las etiquetas de línea priorizan los valores finales y puntos de mayor magnitud. Cuando no hay espacio suficiente, se omiten para mantener la lectura y los valores completos siguen disponibles en la tabla de cada gráfico. Las etiquetas permanecen dentro del área de trazado.

## Nombres semánticos aplicados

Los roles se expresan como variables de tema en `templates/base.html`:

```css
:root {
  --color-text-primary: #25364a;
  --color-text-muted: #58677a;
  --color-action: #234e70;
  --color-border: #dce3eb;
  --color-surface: #ffffff;
  --color-surface-subtle: #f3f6fa;
  --color-focus: #3d7aa9;
  --font-size-body: 14px;
  --font-size-label: 12px;
  --font-size-note: 13px;
  --font-size-section: 18px;
  --radius-control: 6px;
  --radius-panel: 8px;
}
```

La paleta de estado y los colores de gráficos fueron revisados en contraste
(ver tablas arriba). La paleta de series ya no contiene colores repetidos.

## Alcance de la aplicación

| Superficie | Archivo | Estado |
|---|---|---|
| Paneles comerciales | `static/css/comercial_paneles.css` | Consume `var(--color-*)` con fallback |
| Gráficos (11 templates, 21 canvas) | `static/js/app_charts.js` | Fuente única de paleta y opciones |
| Design system global | `templates/base.html` `:root` | Tokens + alias `--app-*` |
| Login | `templates/login.html` | `:root` local (no extiende `base.html`) |
| Admin | `templates/admin/admin_dashboard.html` | Clases `.admin-module--*` |
