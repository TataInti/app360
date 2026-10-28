/* ══════════════════════════════════════════════════════════════════
   App360Charts — fuente única de verdad para gráficos Chart.js
   Ver skills/DESIGN_SYSTEM.md §3.5 y docs/tokens_diseno_comercial.md

   Uso:
     App360Charts.mount(canvas, { type, data, options })
     App360Charts.baseOptions({ horizontal, stacked, percent })
     App360Charts.palette / App360Charts.semantic
     App360Charts.format.money / compactMoney / number / percent
   ══════════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  /* ── Paleta de series ────────────────────────────────────────────
     Serie 1–10 del doc comercial. Correcciones aplicadas:
     - posición 9 (índice 8) repetía #667b91 → #7d8fa3
     - #c59557 (2.70:1), #96a66b (2.64:1) y #9d9a73 (2.88:1) no
       alcanzaban 3:1 sobre blanco (WCAG 1.4.11) → variantes oscuras
       de la misma familia: #a97c3f (3.73:1), #7a8a4f (3.77:1),
       #7f7c55 (4.28:1). */
  const palette = [
    '#234e70', // 8.76:1
    '#4f8095', // 4.33:1
    '#769b82', // 3.10:1
    '#a97c3f', // 3.73:1
    '#9b7180', // 4.14:1
    '#667b91', // 4.36:1
    '#7a8a4f', // 3.77:1
    '#bf8065', // 3.24:1
    '#7d8fa3', // 3.32:1
    '#7f7c55'  // 4.28:1
  ];

  /* ── Colores semánticos ──────────────────────────────────────────
     Código de color operativo: no cambiar por decoración. */
  const semantic = {
    positive: '#16a34a',
    positiveSoft: 'rgba(22,163,74,.22)',
    negative: '#dc2626',
    negativeSoft: 'rgba(220,38,38,.22)',
    neutral: '#234e70',
    neutralSoft: 'rgba(35,78,112,.22)',
    warning: '#f59e0b',
    warningSoft: 'rgba(245,158,11,.22)',
    metric: '#7c3aed',
    metricSoft: 'rgba(124,58,237,.22)',
    flow: '#0ea5e9',
    flowSoft: 'rgba(14,165,233,.22)',
    previous: '#8496a8',
    previousSoft: 'rgba(132,150,168,.4)'
  };

  /* ── Tokens de gráfico ─────────────────────────────────────────── */
  const tokens = {
    ink: '#25364a',
    body: '#334155',
    muted: '#58677a',
    faint: '#8a97a6',
    grid: '#e6ebf0',
    surface: '#ffffff',
    border: '#dce3eb',
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    tickSize: 12,
    labelSize: 10
  };

  /* ── Formateadores ─────────────────────────────────────────────── */
  const number = value => value == null
    ? '—'
    : Number(value).toLocaleString('es-AR', { maximumFractionDigits: 1 });

  const money = value => value == null
    ? '—'
    : Number(value).toLocaleString('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 });

  const compactPart = value => Number(value).toLocaleString('es-AR', { maximumFractionDigits: 1 });

  function compactNumber(value) {
    const n = Number(value), abs = Math.abs(n);
    if (abs >= 1e9) return `${compactPart(n / 1e9)} mil M`;
    if (abs >= 1e6) return `${compactPart(n / 1e6)} M`;
    if (abs >= 1e3) return `${compactPart(n / 1e3)} mil`;
    return number(n);
  }

  function compactMoney(value) {
    const n = Number(value), abs = Math.abs(n), sign = n < 0 ? '−' : '';
    if (abs >= 1e9) return `${sign}$${compactPart(abs / 1e9)} mil M`;
    if (abs >= 1e6) return `${sign}$${compactPart(abs / 1e6)} M`;
    if (abs >= 1e3) return `${sign}$${compactPart(abs / 1e3)} mil`;
    return money(n);
  }

  const percent = value => value == null
    ? '—'
    : `${Number(value).toLocaleString('es-AR', { maximumFractionDigits: 1 })} %`;

  const format = { number, money, compactNumber, compactMoney, percent };

  /* ── Etiquetas de datos (plugin) ─────────────────────────────────
     Resuelve colisiones, recorta texto y evita solapamiento. */
  function dataLabelRect(ctx, value, centerX, centerY, area, clamp = true) {
    const maxWidth = Math.max(0, area.right - area.left - 4);
    let label = String(value ?? '');
    while (label.length > 1 && ctx.measureText(label).width > maxWidth - 8) label = label.slice(0, -1);
    if (!label || ctx.measureText(label).width > maxWidth - 8) return null;
    const width = ctx.measureText(label).width + 8, height = 16;
    let left = centerX - width / 2, top = centerY - height / 2;
    if (clamp) {
      left = Math.max(area.left + 1, Math.min(left, area.right - width - 1));
      top = Math.max(area.top + 1, Math.min(top, area.bottom - height - 1));
    }
    const rect = { left, top, right: left + width, bottom: top + height, width, height, label };
    return left >= area.left && top >= area.top && rect.right <= area.right && rect.bottom <= area.bottom ? rect : null;
  }

  function dataLabelOverlaps(rect, placed) {
    return placed.some(other => rect.left < other.right + 2 && rect.right + 2 > other.left && rect.top < other.bottom + 2 && rect.bottom + 2 > other.top);
  }

  function drawDataLabel(ctx, rect, color = tokens.ink, inside = false) {
    if (!rect) return;
    ctx.save();
    ctx.font = `600 ${tokens.labelSize}px ${tokens.fontFamily}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    if (inside) {
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = 'rgba(25, 38, 52, .72)';
      ctx.strokeText(rect.label, (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2, rect.width - 6);
      ctx.fillStyle = '#fff';
      ctx.fillText(rect.label, (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2, rect.width - 6);
    } else {
      ctx.fillStyle = 'rgba(255,255,255,.94)';
      ctx.fillRect(rect.left, rect.top, rect.width, rect.height);
      ctx.strokeStyle = tokens.border;
      ctx.lineWidth = .75;
      ctx.strokeRect(rect.left + .375, rect.top + .375, rect.width - .75, rect.height - .75);
      ctx.fillStyle = color || tokens.ink;
      ctx.fillText(rect.label, (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2, rect.width - 6);
    }
    ctx.restore();
  }

  const rectHeight = () => 16;

  const dataLabels = {
    id: 'app360DataLabels',
    afterDatasetsDraw(chart) {
      const area = chart.chartArea;
      if (!area || area.right - area.left < 24 || area.bottom - area.top < 18) return;
      const ctx = chart.ctx, placed = [], lineCandidates = [];
      const pluginOptions = chart.options.plugins?.app360DataLabels || chart.options.plugins?.commercialDataLabels || {};
      const fmt = (value, index, dataset, datasetIndex) => pluginOptions.formatter
        ? pluginOptions.formatter(value, index, dataset, chart, datasetIndex)
        : compactNumber(value);
      ctx.save();
      ctx.beginPath();
      ctx.rect(area.left, area.top, area.right - area.left, area.bottom - area.top);
      ctx.clip();
      ctx.font = `600 ${tokens.labelSize}px ${tokens.fontFamily}`;
      chart.data.datasets.forEach((dataset, datasetIndex) => {
        if (!chart.isDatasetVisible(datasetIndex)) return;
        const meta = chart.getDatasetMeta(datasetIndex);
        if (meta.hidden) return;
        const type = dataset.type || chart.config.type;
        if (type === 'line') {
          meta.data.forEach((point, index) => {
            const value = Number(dataset.data[index]);
            if (!Number.isFinite(value) || value === 0 || !point) return;
            const pos = point.getProps(['x', 'y'], true);
            const label = fmt(value, index, dataset, datasetIndex);
            if (label == null || label === '') return;
            const isTerminal = index === dataset.data.length - 1;
            lineCandidates.push({
              x: pos.x, y: pos.y, index, datasetIndex, isTerminal, label,
              color: Array.isArray(dataset.borderColor) ? dataset.borderColor[index] : dataset.borderColor,
              priority: (isTerminal ? 1e12 : 0) + Math.abs(value)
            });
          });
          return;
        }
        if (type === 'doughnut') {
          const values = dataset.data.map(value => Number(value) || 0);
          const total = values.reduce((sum, value, index) => sum + (chart.getDataVisibility(index) ? value : 0), 0);
          meta.data.forEach((arc, index) => {
            const value = values[index];
            if (!value || !chart.getDataVisibility(index) || total <= 0) return;
            const props = arc.getProps(['x', 'y', 'startAngle', 'endAngle', 'innerRadius', 'outerRadius'], true);
            const angle = (props.startAngle + props.endAngle) / 2;
            const midRadius = (props.innerRadius + props.outerRadius) / 2;
            const label = fmt(value, index, dataset, datasetIndex);
            if (label == null || label === '') return;
            const width = ctx.measureText(String(label)).width + 8;
            if (props.outerRadius - props.innerRadius < 17 || midRadius * Math.abs(props.endAngle - props.startAngle) < width + 8) return;
            const rect = dataLabelRect(ctx, label, props.x + Math.cos(angle) * midRadius, props.y + Math.sin(angle) * midRadius, area, false);
            if (!rect || dataLabelOverlaps(rect, placed)) return;
            placed.push(rect);
            drawDataLabel(ctx, rect, dataset.backgroundColor?.[index] || semantic.neutral, true);
          });
          return;
        }
        if (type !== 'bar') return;
        const horizontal = meta.iScale?.axis === 'y';
        const stacked = Boolean(chart.options.scales?.x?.stacked || chart.options.scales?.y?.stacked);
        meta.data.forEach((bar, index) => {
          const value = Number(dataset.data[index]);
          if (!Number.isFinite(value) || value === 0 || !bar) return;
          const props = bar.getProps(['x', 'y', 'base', 'width', 'height'], true);
          const label = fmt(value, index, dataset, datasetIndex);
          if (label == null || label === '') return;
          const textWidth = ctx.measureText(String(label)).width + 8;
          let rect, inside = false;
          if (horizontal) {
            const left = Math.min(props.base, props.x), right = Math.max(props.base, props.x);
            if (stacked) {
              if (right - left < textWidth + 4 || props.height < 14) return;
              rect = dataLabelRect(ctx, label, (left + right) / 2, props.y, area, false);
              if (!rect || rect.left < left + 2 || rect.right > right - 2) return;
              inside = true;
            } else {
              const centerX = value > 0 ? right + textWidth / 2 + 3 : left - textWidth / 2 - 3;
              rect = dataLabelRect(ctx, label, centerX, props.y, area, false);
              if (!rect && right - left >= textWidth + 4) {
                rect = dataLabelRect(ctx, label, (left + right) / 2, props.y, area, false);
                inside = Boolean(rect);
              }
            }
          } else {
            const top = Math.min(props.base, props.y), bottom = Math.max(props.base, props.y);
            if (stacked) {
              if (bottom - top < 19) return;
              rect = dataLabelRect(ctx, label, props.x, (top + bottom) / 2, area, false);
              if (!rect || rect.top < top + 2 || rect.bottom > bottom - 2) return;
              inside = true;
            } else {
              const centerY = value > 0 ? top - rectHeight() / 2 - 3 : bottom + rectHeight() / 2 + 3;
              rect = dataLabelRect(ctx, label, props.x, centerY, area, false);
              if (!rect && bottom - top >= rectHeight() + 4) {
                rect = dataLabelRect(ctx, label, props.x, (top + bottom) / 2, area, false);
                inside = Boolean(rect);
              }
            }
          }
          if (!rect || dataLabelOverlaps(rect, placed)) return;
          placed.push(rect);
          const barColor = Array.isArray(dataset.borderColor)
            ? dataset.borderColor[index]
            : dataset.borderColor;
          drawDataLabel(ctx, rect, barColor || tokens.ink, inside);
        });
      });
      lineCandidates.sort((a, b) => b.priority - a.priority);
      const maxLineLabels = Math.max(4, Math.min(12, Math.floor((area.right - area.left) / 65)));
      const minLineGap = Math.max(45, (area.right - area.left) / maxLineLabels);
      const selectedLineCandidates = [];
      lineCandidates.forEach(candidate => {
        if (selectedLineCandidates.length >= maxLineLabels) return;
        const terminalPair = candidate.isTerminal && selectedLineCandidates.some(other => other.isTerminal && other.index === candidate.index && other.datasetIndex !== candidate.datasetIndex);
        const sameTerminalLimit = candidate.isTerminal && selectedLineCandidates.filter(other => other.isTerminal && other.index === candidate.index).length >= 2;
        if (sameTerminalLimit || (!terminalPair && selectedLineCandidates.some(other => Math.abs(other.x - candidate.x) < minLineGap))) return;
        const offsets = [-22, 22, -39, 39, -56, 56, 0];
        for (const offset of offsets) {
          const rect = dataLabelRect(ctx, candidate.label, candidate.x, candidate.y + offset, area);
          if (!rect || dataLabelOverlaps(rect, placed)) continue;
          placed.push(rect);
          drawDataLabel(ctx, rect, candidate.color);
          selectedLineCandidates.push(candidate);
          break;
        }
      });
      ctx.restore();
    }
  };

  /* ── Opciones base ─────────────────────────────────────────────── */
  function baseOptions({ horizontal = false, stacked = false, percent: isPercent = false, legend = 'bottom' } = {}) {
    const valueAxis = {
      beginAtZero: true,
      stacked,
      grid: { color: tokens.grid, drawBorder: false },
      ticks: { color: tokens.muted, font: { size: tokens.tickSize } }
    };
    const categoryAxis = {
      stacked,
      grid: { display: false },
      ticks: { color: tokens.muted, font: { size: tokens.tickSize } }
    };
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 8, right: 8 } },
      plugins: {
        legend: legend === false
          ? { display: false }
          : {
              display: true,
              position: legend,
              labels: {
                color: tokens.muted,
                boxWidth: 12,
                usePointStyle: true,
                padding: 14,
                font: { size: tokens.tickSize }
              }
            },
        tooltip: {
          backgroundColor: 'rgba(37,54,74,.94)',
          padding: 10,
          cornerRadius: 6,
          titleFont: { size: tokens.tickSize, weight: '600' },
          bodyFont: { size: tokens.tickSize },
          displayColors: true,
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true
        }
      },
      scales: horizontal
        ? { x: { ...valueAxis, ticks: { ...valueAxis.ticks, callback: v => isPercent ? `${v}%` : compactNumber(v) } }, y: categoryAxis }
        : { x: categoryAxis, y: { ...valueAxis, ticks: { ...valueAxis.ticks, callback: v => isPercent ? `${v}%` : compactNumber(v) } } }
    };
  }

  /* ── Merge profundo ────────────────────────────────────────────────
     Necesario para que un override parcial (p.ej. solo `tooltip.callbacks`)
     no borre el resto de la configuración base. */
  function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function deepMerge(base, override) {
    if (!isPlainObject(base) || !isPlainObject(override)) {
      return override === undefined ? base : override;
    }
    const result = { ...base };
    for (const key of Object.keys(override)) {
      const value = override[key];
      if (value === undefined) continue;
      result[key] = isPlainObject(value) && isPlainObject(base[key])
        ? deepMerge(base[key], value)
        : value;
    }
    return result;
  }

  /* ── Regla de leyenda ──────────────────────────────────────────────
     Una sola regla para todo el sitio:
     - Dona/torta: siempre visible (los colores necesitan nombre).
     - Barra/línea con un solo dataset: oculta (el título ya lo dice).
     - Barra/línea con 2+ datasets: visible abajo.
     Un `display` explícito en el template siempre gana. */
  function resolveLegend(config) {
    const explicit = config.options?.plugins?.legend?.display;
    if (explicit !== undefined) return explicit;
    const type = config.type;
    if (type === 'doughnut' || type === 'pie' || type === 'polarArea') return true;
    const datasets = config.data?.datasets || [];
    return datasets.length > 1;
  }

  /* ── Creación ──────────────────────────────────────────────────────
     Punto único de creación de gráficos. Ningún template debería llamar
     a `new Chart()` directamente. */
  const instances = new WeakMap();

  function create(canvas, config) {
    if (typeof global.Chart === 'undefined' || !canvas) return null;

    const previous = instances.get(canvas);
    if (previous) previous.destroy();

    const horizontal = config.options?.indexAxis === 'y';
    const stacked = Boolean(config.options?.scales?.x?.stacked || config.options?.scales?.y?.stacked);
    const percent = Boolean(config.percent);
    const showLegend = resolveLegend(config);

    const defaults = baseOptions({ horizontal, stacked, percent, legend: showLegend ? 'bottom' : false });

    // El template puede pedir explícitamente no mostrar etiquetas de datos.
    const plugins = config.dataLabels === false
      ? [...(config.plugins || [])]
      : [dataLabels, ...(config.plugins || [])];

    const merged = {
      ...config,
      type: config.type,
      plugins,
      options: deepMerge(
        { ...defaults, indexAxis: config.options?.indexAxis },
        config.options || {}
      )
    };

    // La animación no es configurable por template: siempre apagada.
    merged.options.animation = false;
    merged.options.animations = false;
    merged.options.responsive = true;
    merged.options.maintainAspectRatio = false;

    const chart = new global.Chart(canvas, merged);
    instances.set(canvas, chart);
    return chart;
  }

  function destroy(canvas) {
    const previous = instances.get(canvas);
    if (previous) {
      previous.destroy();
      instances.delete(canvas);
    }
  }

  /* ── Defaults globales ─────────────────────────────────────────────
     Se aplican a TODOS los gráficos, incluso los creados con `new Chart()`
     directo. Esto es lo que garantiza apariencia idéntica entre paneles:
     leyenda, tooltip, animación, ejes y tipografía.

     Chart.js 4 no garantiza que los subobjetos existan, así que se crean
     con `ensure()` antes de escribir. */
  function ensure(parent, key) {
    if (!parent[key] || typeof parent[key] !== 'object') parent[key] = {};
    return parent[key];
  }

  if (global.Chart) {
    const D = global.Chart.defaults;

    ensure(D, 'font').family = tokens.fontFamily;
    D.font.size = tokens.tickSize;
    D.color = tokens.muted;
    D.borderColor = tokens.grid;

    // Sin animación: los paneles se recargan por filtros y el movimiento distrae.
    D.animation = false;
    D.animations = false;

    // Interacción homogénea: tooltip por índice, sin exigir hover exacto.
    D.interaction = { mode: 'index', intersect: false };

    // Leyenda: siempre abajo, con punto, mismo tamaño y color.
    const legend = ensure(ensure(D, 'plugins'), 'legend');
    legend.position = 'bottom';
    legend.align = 'center';
    const legendLabels = ensure(legend, 'labels');
    legendLabels.color = tokens.muted;
    legendLabels.usePointStyle = true;
    legendLabels.boxWidth = 12;
    legendLabels.boxHeight = 12;
    legendLabels.padding = 14;
    legendLabels.font = { size: tokens.tickSize };

    // Tooltip: fondo oscuro del sistema, esquinas y tipografía consistentes.
    const tooltip = ensure(ensure(D, 'plugins'), 'tooltip');
    tooltip.backgroundColor = 'rgba(37,54,74,.94)';
    tooltip.padding = 10;
    tooltip.cornerRadius = 6;
    tooltip.titleFont = { size: tokens.tickSize, weight: '600' };
    tooltip.bodyFont = { size: tokens.tickSize };
    tooltip.displayColors = true;
    tooltip.boxWidth = 10;
    tooltip.boxHeight = 10;
    tooltip.usePointStyle = true;

    // Ejes: grilla suave, ticks muted, sin borde de eje.
    const scales = ensure(D, 'scales');
    for (const scaleId of ['linear', 'logarithmic']) {
      const scale = ensure(scales, scaleId);
      const grid = ensure(scale, 'grid');
      grid.color = tokens.grid;
      grid.drawBorder = false;
      const ticks = ensure(scale, 'ticks');
      ticks.color = tokens.muted;
      ticks.font = { size: tokens.tickSize };
    }
    const category = ensure(scales, 'category');
    ensure(category, 'grid').display = false;
    const categoryTicks = ensure(category, 'ticks');
    categoryTicks.color = tokens.muted;
    categoryTicks.font = { size: tokens.tickSize };
  }

  global.App360Charts = {
    palette,
    semantic,
    tokens,
    format,
    baseOptions,
    dataLabels,
    create,
    mount: create,
    destroy,
    colorAt: index => palette[index % palette.length]
  };
})(window);
