# Plan: quitar `'unsafe-inline'` de la CSP de App360

Estado: propuesta (solo documento, sin cambios de código). Base: `main` = 723a6ec (PR #53).
Los totales del inventario coinciden con los del PR #53.

## 0. Punto de partida

CSP actual (`app.py`, `add_security_headers`):

```
default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:;
font-src 'self' https://cdn.jsdelivr.net
```

Hechos que condicionan el plan:

- Un nonce o hash en `script-src` **no cubre** atributos `onclick=`/`onchange=`. Los 67 manejadores
  hay que convertirlos (`addEventListener` con `data-*`); no se usa `'unsafe-hashes'` porque
  deja la superficie abierta.
- Los scripts externos de `cdn.jsdelivr.net` (Bootstrap, Chart.js, Tom Select) siguen permitidos por
  origen; no se tocan aquí (SRI o autoalojarlos es un trabajo aparte).
- Solo 4 plantillas mezclan Jinja dentro del `<script>` (`admin/admin_modulo` 5 expresiones,
  `cta_cte_friar` 1, `tesoreria_arqueos` 1, `tesoreria_movimientos` 1). El resto del JS en línea es
  JS puro, movible tal cual a `static/js/`.
- Ya existen estáticos en `static/js/` (p. ej. `app_format.js`, `app_charts.js`) y CI con pruebas de
  Python y sintaxis JS (`.github/workflows/ci.yml`).
- CSRF activo: el endpoint de reportes debe ir exento (`csrf.exempt`) y sin sesión requerida.

## 1. Inventario por plantilla

Columnas: bloques `<script>` en línea / líneas de JS en línea / `<style>` / atributos `style="…"` /
manejadores `on*=`. Totales: **25 / 6 780 / 13 / 39 / 67**. Riesgo: B = JS puro corto o solo CSS;
M = lógica de pantalla sin Jinja; A = muchos manejadores, Jinja dentro del script o plantilla base.

| plantilla | script | líneas JS | style | style= | on*= | riesgo |
|---|---|---|---|---|---|---|
| `cambiar_clave.html` | 0 | 0 | 0 | 1 | 0 | B |
| `login.html` | 0 | 0 | 1 | 0 | 0 | B |
| `tesoreria/_modal_arqueo.html` | 0 | 0 | 1 | 0 | 0 | B |
| `tesoreria/_modal_movimiento.html` | 0 | 0 | 1 | 0 | 1 | B |
| `venta_detail.html` | 1 | 6 | 0 | 0 | 0 | B |
| `ventas_list.html` | 1 | 6 | 0 | 0 | 0 | B |
| `compras_detail.html` | 1 | 7 | 0 | 0 | 0 | B |
| `campaigns_list.html` | 1 | 51 | 0 | 0 | 0 | B |
| `products_list.html` | 1 | 51 | 0 | 0 | 0 | B |
| `stock_list.html` | 1 | 51 | 0 | 0 | 0 | B |
| `locations_list.html` | 1 | 67 | 0 | 0 | 0 | B |
| `dashboard_financiero.html` | 1 | 73 | 1 | 1 | 0 | M |
| `compras_overview.html` | 1 | 106 | 0 | 1 | 0 | M |
| `criterio_clientes.html` | 1 | 110 | 1 | 1 | 0 | M |
| `panel_ejecutivo.html` | 1 | 259 | 1 | 0 | 0 | M |
| `leads_list.html` | 1 | 278 | 1 | 0 | 0 | M |
| `bi_dashboard.html` | 1 | 408 | 1 | 0 | 0 | M |
| `tesoreria_panel.html` | 1 | 292 | 1 | 0 | 0 | M |
| `rrhh_panel.html` | 1 | 211 | 0 | 14 | 4 | M |
| `rrhh_adelantos.html` | 1 | 212 | 1 | 0 | 7 | M |
| `rrhh_ausentismo.html` | 1 | 452 | 0 | 13 | 4 | M |
| `rrhh_liquidaciones.html` | 1 | 306 | 0 | 3 | 5 | M |
| `gastos_panel.html` | 1 | 304 | 1 | 2 | 1 | M |
| `tesoreria_arqueos.html` | 1 | 462 | 0 | 1 | 5 | A (1 Jinja) |
| `tesoreria_movimientos.html` | 1 | 602 | 0 | 1 | 5 | A (1 Jinja) |
| `sabiogo_admin.html` | 1 | 532 | 0 | 0 | 11 | A |
| `cta_cte_friar.html` | 1 | 594 | 1 | 0 | 11 | A (1 Jinja) |
| `admin/admin_modulo.html` | 1 | 602 | 0 | 1 | 13 | A (5 Jinja) |
| `base.html` | 1 | 738 | 1 | 0 | 0 | A (global, todas las pantallas) |

Las líneas de JS son las del bloque en línea (el recuento cuenta saltos de línea del contenido).
`base.html` es el bloque mayor y afecta a toda pantalla: se deja al final de los scripts.

## 2. Política objetivo

Dos fases, para no depender de eliminar todos los `style="…"` de una vez.

**Fase de scripts** (`unsafe-inline` fuera de `script-src`):

```
default-src 'self';
script-src 'self' 'nonce-{N}' https://cdn.jsdelivr.net;
style-src  'self' 'unsafe-inline' https://cdn.jsdelivr.net;   # se mantiene mientras haya style="…"
img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net;
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self';
report-uri /csp-report
```

- `{N}`: nonce aleatorio por petición (`secrets.token_urlsafe(16)`), generado en un `before_request`,
  guardado en `g.csp_nonce`, expuesto a Jinja con un `context_processor` y usado en `after_request`.
  Sirve solo para los pocos bloques que deban quedar en línea; el resto pasa a
  `static/js/<pantalla>.js` (preferido: cacheable y sin nonce).
- Los datos de Jinja que hoy se interpolan dentro del script pasan a `data-*` en el DOM o a un
  `<script type="application/json" id="…">` (no se ejecuta, no requiere nonce) que lee el `.js`.
- `object-src`, `base-uri`, `form-action` y `frame-ancestors` se agregan ya en Report-Only; se
  verifican con `git grep` (no debería haber `<object>`, `<base>` ni formularios a otro origen).
- Con nonce no se emite `'unsafe-inline'` en `script-src`.

**Fase de estilos** (opcional, posterior): `style="…"` (39) → clases en `static/css/`; `<style>` (13)
→ archivos CSS; luego `style-src 'self' https://cdn.jsdelivr.net`. Chart.js y Tom Select aplican
estilos por CSSOM (permitido) pero Bootstrap JS puede escribir `style=`; se vigila con Report-Only
antes de quitar. Si aparecen avisos, `'unsafe-inline'` queda solo en `style-src` (riesgo mucho menor que
en scripts).

## 3. Tandas (de menor a mayor riesgo)

Regla común: un PR por tanda, sin cambiar comportamiento ni textos. Antes de cada una se anota el
estado de la pantalla (captura + consola sin errores) y después se compara. Prueba común: suite `pytest`
existente + sintaxis JS de CI + consola del navegador sin avisos CSP con la política nueva en
Report-Only (sección 4).

| # | Tanda | Qué se mueve | Cobertura de pruebas actual | Cómo se mide que no se rompió |
|---|---|---|---|---|
| T0 | Infraestructura (sin mover UI) | nonce por petición, `context_processor`, endpoint `/csp-report`, cabecera `Content-Security-Policy-Report-Only` con la política objetivo, junto a la CSP actual | `tests/test_cabeceras_cache_seguridad.py` (ampliar con 3 asserts: ambas cabeceras presentes, nonce distinto en dos peticiones, `/csp-report` responde 204 sin sesión) | Cabecera vigente intacta; la app abre igual; llegan reportes |
| T1 | Solo CSS: `login`, `cambiar_clave`, `tesoreria/_modal_arqueo`, `tesoreria/_modal_movimiento` (3 `<style>`, 1 `style=`, 1 `on*`) | `<style>`→`static/css`; `onclick` del modal→listener | pruebas de tesorería; `tesoreria_forms.js` | Captura antes/después; abrir y cerrar el modal |
| T2 | JS mínimo (≤ 7 líneas): `venta_detail`, `ventas_list`, `compras_detail` | script → `static/js/<pantalla>.js` | `tests/test_compras_secuencia_navegador.py` (compras); resto manual | Consola sin errores; la acción del script responde igual |
| T3 | Listados chicos (≤ 70 líneas, sin handlers): `campaigns_list`, `products_list`, `stock_list`, `locations_list` | script → estático | `tests/test_campanas_panel_json.py` y pruebas de listados | Captura; filtrar/ordenar/paginar iguales |
| T4 | Paneles sin handlers: `dashboard_financiero`, `compras_overview`, `criterio_clientes`, `panel_ejecutivo`, `leads_list`, `bi_dashboard`, `tesoreria_panel` (+ sus `<style>` y `style=`) | script/estilos → estático | `test_dashboards_v2.py`, `test_comercial_paneles.py`, `scripts/verify_chart_consistency.py` | `verify_chart_consistency.py` igual que antes; gráficos con los mismos números |
| T5 | RRHH y gastos (handlers y muchos `style=`): `rrhh_panel`, `rrhh_adelantos`, `rrhh_ausentismo`, `rrhh_liquidaciones`, `gastos_panel` | script→estático; `on*=` (21) → `data-action` + delegación; `style=` → clases | pruebas de RRHH/gastos existentes | Recorrido por pantalla: cada botón/selector ejecuta igual (lista de handlers por pantalla en el PR) |
| T6 | Tesorería con Jinja: `tesoreria_arqueos`, `tesoreria_movimientos` | script→estático; 1 expresión Jinja por pantalla → `data-*`; 10 handlers | `test_arqueos_turno.py` y pruebas de tesorería | Crear/cerrar arqueo y registrar movimiento con datos sintéticos, resultado idéntico |
| T7 | Muchos handlers: `sabiogo_admin`, `cta_cte_friar`, `admin/admin_modulo` | script→estático; 35 handlers; 6 expresiones Jinja → JSON/`data-*` | `test_admin_importes_friar.py`, `test_admin_dashboard_static.py` | Recorrido de cada pestaña y acción con usuario de prueba |
| T8 | `base.html` (738 líneas, global) | script→`static/js/base.js` (o dividido); `<style>`→`static/css` | todas las pruebas; es transversal | Barrido de pantallas de T1–T7 + login/menú; consola limpia |
| T9 | Activar la política de la fase de scripts como `Content-Security-Policy` | cambio de una línea en `app.py` | test de cabeceras | 7 días en Report-Only con 0 avisos de `script-src`; vuelta atrás: restaurar la línea |
| T10 | (opcional) Estilos | 13 `<style>` + 39 `style=` residuales → CSS; quitar `'unsafe-inline'` de `style-src` | `test_app_components_css.py`, capturas | Report-Only de estilos sin avisos antes de activar |

Los `<style>` y `style=` de cada pantalla se mueven en la tanda de esa pantalla si es barato; si no,
quedan para T10. Dentro de una tanda: de menos a más handlers.

## 4. Habilitar primero en Report-Only

1. T0 agrega `Content-Security-Policy-Report-Only` **además** de la cabecera vigente (la actual no
   cambia: nada se bloquea). Se controla con una variable de entorno (p. ej. `CSP_REPORT_ONLY=1`; solo
   el nombre) para apagarla sin cambiar código.
2. `report-uri /csp-report` (compatible con todos los navegadores). Endpoint `POST` exento de CSRF, sin
   sesión, acepta `application/csp-report` y `application/json`, cuerpo ≤ 8 KB, con el `limiter`
   existente, responde `204`.
3. **Sin exponer datos**: se guardan solo `effective-directive`, `blocked-uri` reducido a origen (sin
   ruta ni query), `document-uri` reducido a ruta sin query ni fragmento (IDs numéricas → `:id`),
   `source-file` (ruta estática), línea/columna y un contador. Se descartan `script-sample`, `referrer`,
   `original-policy`, IP y user-agent (a lo sumo la familia del navegador). No se asocia a usuario.
   Destino: log propio (`csp.log`, mismos permisos que los demás logs) o tabla de agregados por
   (directiva, ruta, origen); retención 30 días.
4. Lectura: un script de resumen agrupa por directiva y ruta y lista pantallas con avisos. Criterio de
   avance de cada tanda: 0 avisos nuevos de `script-src` en esa pantalla tras recorrerla.
5. Ruido esperado: extensiones del navegador (`chrome-extension`, `moz-extension`) se filtran. Al inicio
   aparecerán los bloques en línea y los 67 `on*=` como línea base: esa lista es el tablero de progreso.
6. T9 solo tras 7 días con 0 avisos de `script-src` de pantallas reales; despliegue con la rutina
   habitual (backup, `app360.service`, verificación) y vuelta atrás de una línea.

## 5. Estimación de pasos por tanda

Un «paso» = una acción verificable (mover un bloque, probar una pantalla, etc.).

| Tanda | Pasos | Detalle |
|---|---|---|
| T0 | 6 | nonce y `context_processor`; endpoint y sanitizado; cabecera Report-Only; 3 asserts; revisión; despliegue |
| T1 | 5 | 3 `<style>`, 1 `style=`, 1 handler; capturas |
| T2 | 4 | 3 scripts + verificación |
| T3 | 5 | 4 scripts + verificación |
| T4 | 10 | 7 pantallas + datos Jinja→JSON + comparar gráficos |
| T5 | 12 | 5 pantallas, 21 handlers, 30 `style=`; recorrido |
| T6 | 8 | 2 pantallas, 10 handlers, Jinja→`data-*`; prueba con datos sintéticos |
| T7 | 14 | 3 pantallas, 35 handlers, 6 Jinja; recorrido |
| T8 | 8 | dividir `base.js`, barrido global |
| T9 | 4 | 7 días de observación, cambio de cabecera, despliegue, vigilancia |
| T10 | 10 | `<style>` y `style=` residuales y quitar `unsafe-inline` de estilos |

Total ≈ 86 pasos (≈ 76 sin T10), en 10–11 PR pequeños. T1–T3 se pueden hacer en paralelo (archivos
disjuntos). T8 y T9 son secuenciales; `base.html` es zona de colisión con otros PR de UI: coordinar
antes de tocarlo.

## 6. Riesgos y mitigaciones

- Handlers dentro de cadenas JS (`innerHTML` con `onclick=`): buscarlos también en los strings del JS,
  no solo en el HTML estático; incluirlos en el inventario de cada tanda.
- Orden de carga: los scripts movidos usan `defer` o van al final del `<body>`, manteniendo la posición
  respecto de Bootstrap/Chart.js.
- Caché de estáticos: versionar con `?v=` o nombre con hash para que no se use una copia vieja.
- Nonce y caché: las respuestas HTML ya llevan `Cache-Control: no-store`, el nonce no se reutiliza.
- Vuelta atrás: cada tanda es un PR independiente y revertible sin afectar la política vigente.
