(() => {
  'use strict';
  const root = document.querySelector('.com-panel');
  if (!root) return;
  const clientes = root.dataset.mode === 'clientes';
  const $ = id => document.getElementById(id);
  const form = $('com-filtros');
  const number = value => value == null ? '—' : Number(value).toLocaleString('es-AR', {maximumFractionDigits: 1});
  const money = value => value == null ? '—' : Number(value).toLocaleString('es-AR', {style: 'currency', currency: 'ARS', maximumFractionDigits: 0});
  const compactPart = value => Number(value).toLocaleString('es-AR', {maximumFractionDigits: 1});
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
  const chartFormat = (value, measure) => measure === 'importe' ? compactMoney(value) : compactNumber(value);
  const fecha = value => value ? value.slice(0, 10).split('-').reverse().join('/') : '—';
  const elem = (tag, text, cls) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node; };
  const badge = (text, cls = '') => elem('span', text, `com-badge ${cls}`);
  // Etiqueta de origen del comprobante: PRE, FAC o NC (nota de crédito, se lista pero no suma).
  const ORIGENES = {PRE: 'Presupuesto', FAC: 'Factura', NC: 'Nota de crédito: se muestra, no suma en los totales', OTRO: 'Comprobante sin código'};
  const origen = tipo => { const b = badge(tipo, 'com-origen' + (tipo === 'NC' ? ' com-origen-nc' : '')); b.title = ORIGENES[tipo] || tipo; return b; };
  const conOrigen = (texto, tipos) => { const box = elem('span'); (tipos || []).forEach(t => box.append(origen(t))); box.append(document.createTextNode(texto)); return box; };
  const porTipo = c => { const box = elem('div'); ['PRE', 'FAC'].forEach(t => { const v = c.por_tipo[t]; const line = elem('span', null, 'com-por-tipo'); line.append(origen(t), document.createTextNode(`${number(v.n)} op. · ${money(v.importe)}`)); box.append(line); }); return box; };
  let state = new URLSearchParams(location.search), data, chart, requestId = 0, detailId = 0, detailTrigger;
  const extraCharts = new Map(); let quantityRequestId = 0, mixRequestId = 0, analysisDimension = 'producto';
  const filterInstances = new Map();
  const filterLabels = {
    cliente: {all: 'Todos los clientes', search: 'Buscar cliente…'},
    producto: {all: 'Todos los productos', search: 'Buscar producto…'}
  };
  const sectionFilters = {
    analisis: {cliente: state.get('analisis_cliente') || '', producto: state.get('analisis_producto') || ''},
    mix: {cliente: state.get('mix_cliente') || '', producto: state.get('mix_producto') || ''}
  };
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone: 'America/Argentina/Tucuman'}).format(new Date());
  function defaults() {
    const end = today();
    form.elements.fecha_desde.value = end.slice(0, 8) + '01';
    form.elements.fecha_hasta.value = end;
  }
  function setPreset(preset) {
    const end = new Date(`${today()}T00:00:00Z`);
    const iso = date => date.toISOString().slice(0, 10);
    if (preset === '7d' || preset === '30d') {
      const start = new Date(end);
      start.setUTCDate(start.getUTCDate() - (preset === '7d' ? 6 : 29));
      form.elements.fecha_desde.value = iso(start);
      form.elements.fecha_hasta.value = iso(end);
    } else if (preset === 'last-month') {
      form.elements.fecha_desde.value = iso(new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 1, 1)));
      form.elements.fecha_hasta.value = iso(new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 0)));
    } else if (preset === 'year') {
      form.elements.fecha_desde.value = `${end.getUTCFullYear()}-01-01`;
      form.elements.fecha_hasta.value = iso(end);
    } else defaults();
  }
  defaults();
  for (const name of ['empresa', 'fecha_desde', 'fecha_hasta', 'q']) {
    if (form.elements[name] && state.has(name)) form.elements[name].value = state.get(name);
  }
  for (const dimension of ['cliente', 'producto']) {
    if (state.get(dimension)) form.elements[dimension].add(new Option(state.get(dimension), state.get(dimension), true, true));
  }
  if (!form.elements.empresa.value) form.elements.empresa.value = 'TODAS';
  if (state.get('vendedor')) form.elements.vendedor.add(new Option(state.get('vendedor'), state.get('vendedor'), true, true));
  if (clientes) {
    if (!['atencion', 'activos', 'sin_compra', 'todos'].includes(state.get('vista'))) state.set('vista', 'atencion');
    $('com-orden').value = ['prioridad', 'cliente', 'dias', 'importe'].includes(state.get('orden')) ? state.get('orden') : 'prioridad';
    $('com-size').value = state.get('por_pagina') === '50' ? '50' : '25';
  } else {
    $('com-meta-medida').value = ['importe', 'cajas', 'kilos'].includes(state.get('medida')) ? state.get('medida') : 'importe';
  }
  function params() {
    const p = new URLSearchParams(new FormData(form));
    if (clientes) {
      p.set('vista', state.get('vista') || 'atencion'); p.set('pagina', state.get('pagina') || '1');
      p.set('orden', $('com-orden').value); p.set('por_pagina', $('com-size').value);
    } else {
      p.set('medida', $('com-meta-medida').value);
      if (root.dataset.mode === 'ventas') {
        for (const [scope, values] of Object.entries(sectionFilters)) for (const dimension of ['cliente', 'producto']) {
          const key = `${scope}_${dimension}`;
          if (values[dimension]) p.set(key, values[dimension]); else p.delete(key);
        }
      }
    }
    return p;
  }
  async function get(url, p) {
    const response = await fetch(url + '?' + p, {headers: {'Accept': 'application/json'}});
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Tu sesión o permiso no permite cargar estos datos. Volvé a iniciar sesión.');
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'No se pudieron cargar los datos.');
    return result;
  }
  function table(headers, rows, cls = '') {
    const t = elem('table', null, cls), head = elem('thead'), hr = elem('tr');
    headers.forEach(([text, numeric]) => {const h = elem('th', text, numeric ? 'num' : ''); h.scope = 'col'; hr.append(h);});
    head.append(hr); t.append(head); const body = elem('tbody');
    for (const row of rows) {
      const tr = elem('tr'); row.forEach((value, i) => {
        const td = elem('td', null, headers[i][1] ? 'num' : ''); td.dataset.label = headers[i][0];
        if (value instanceof Node) td.append(value); else td.textContent = value ?? '—'; tr.append(td);
      }); body.append(tr);
    }
    t.append(body); return t;
  }
  // Etiquetas de datos y paleta: fuente única en static/js/app_charts.js
  const charts = window.App360Charts;
  const commercialDataLabels = charts ? charts.dataLabels : {id: 'app360DataLabels', afterDatasetsDraw() {}};
  function metric(label, value, note) {
    const box = elem('div', null, 'com-metric'); box.append(elem('span', label), elem('strong', value));
    if (note) box.append(elem('small', note)); return box;
  }
  function comparativeText(c, format = money) {
    return `Anterior: ${format(c.anterior)} · Diferencia: ${format(c.diferencia)} · ${c.variacion_pct == null ? 'Sin base comparable' : number(c.variacion_pct) + '%'}`;
  }
  function transferLink(p) {
    const link = $(clientes ? 'com-ventas' : 'com-seguimiento');
    const query = new URLSearchParams();
    for (const key of ['empresa', 'vendedor', 'cliente', 'producto', 'fecha_desde', 'fecha_hasta']) if (p.get(key)) query.set(key, p.get(key));
    link.href = (clientes ? '/dashboard-comercial' : '/comercial/seguimiento-clientes') + '?' + query;
  }
  function readFilterValue(select) {
    return filterInstances.get(select)?.getValue() ?? select.value;
  }
  // Lo que muestra el control (incluido «Todos los …») lleva su nombre completo en title:
  // si el texto se corta con puntos suspensivos, el nombre completo sigue disponible.
  function titularItems(instance) {
    instance.control.querySelectorAll('.item').forEach(item => { item.title = item.textContent.trim(); });
  }
  function setFilterValue(select, value) {
    const instance = filterInstances.get(select);
    if (instance) {
      instance.setValue(value || '', true);
      titularItems(instance);
    }
    else select.value = value || '';
    select.title = select.options[select.selectedIndex]?.text || '';
  }
  function filterSelects(scope, dimension) {
    return document.querySelectorAll(`[data-com-filter-scope="${scope}"][data-com-filter-dimension="${dimension}"]`);
  }
  function populateFilter(scope, dimension, items, selected) {
    const {all: allLabel, search: searchLabel} = filterLabels[dimension];
    const values = [...new Set((items || []).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
    const selectedValue = selected || '';
    if (selectedValue && !values.includes(selectedValue)) values.push(selectedValue);
    const signature = values.join('\u0000');
    filterSelects(scope, dimension).forEach(select => {
      if (select.dataset.optionsKey !== signature) {
        filterInstances.get(select)?.destroy();
        filterInstances.delete(select);
        select.replaceChildren(new Option(allLabel, ''), ...values.map(value => new Option(value, value)));
        select.dataset.optionsKey = signature;
        if (window.TomSelect) {
          const instance = new TomSelect(select, {
            create: false,
            allowEmptyOption: true,
            maxOptions: 500,
            placeholder: searchLabel,
            plugins: ['dropdown_input']
          });
          instance.on('dropdown_open', () => {
            instance.dropdown.querySelectorAll('.option').forEach(option => {
              option.title = option.textContent.trim();
            });
          });
          filterInstances.set(select, instance);
        }
      }
      setFilterValue(select, selectedValue);
    });
  }
  function syncFilterScope(scope) {
    for (const dimension of ['cliente', 'producto']) {
      const selected = scope === 'principal' ? form.elements[dimension].value || '' : sectionFilters[scope][dimension];
      filterSelects(scope, dimension).forEach(select => setFilterValue(select, selected));
    }
  }
  async function options(p, id) {
    const opts = await get('/api/comercial/paneles/opciones', p);
    if (id !== requestId) return;
    const selected = p.get('vendedor') || '';
    form.elements.vendedor.replaceChildren(new Option('Todos los vendedores', ''));
    const values = new Set(opts.vendedores); if (selected) values.add(selected);
    [...values].sort((a,b) => a.localeCompare(b, 'es')).forEach(v => form.elements.vendedor.add(new Option(v, v)));
    form.elements.vendedor.value = selected;
    populateFilter('principal', 'cliente', opts.clientes, p.get('cliente'));
    populateFilter('principal', 'producto', opts.productos, p.get('producto'));
    for (const scope of ['analisis', 'mix']) {
      populateFilter(scope, 'cliente', opts.clientes, sectionFilters[scope].cliente);
      populateFilter(scope, 'producto', opts.productos, sectionFilters[scope].producto);
    }
  }
  async function load() {
    if (!form.reportValidity()) return;
    closeDetail(false);
    // Invalidate pending analytics when the shared filters change.
    ++quantityRequestId; ++mixRequestId;
    const id = ++requestId, p = params(); state = p;
    history.replaceState(null, '', location.pathname + '?' + p); transferLink(p);
    $('com-error').hidden = true; $('com-content').hidden = true; root.setAttribute('aria-busy', 'true');
    $('com-status').textContent = 'Cargando datos…';
    if (!clientes && root.dataset.mode === 'ventas') {
      if (!$('cantidades-body').hidden) void loadQuantities();
      if (!$('mix-body').hidden) void loadMix();
    }
    try {
      // Filters and data load together; a failure is explicit, never a fabricated zero.
      const [result] = await Promise.all([get(clientes ? '/api/comercial/seguimiento-clientes' : '/api/dashboard-comercial/resumen-estrategico', p), options(p, id)]);
      if (id !== requestId) return;
      data = result;
      $('com-content').hidden = false;
      if (clientes) renderClientes(); else renderVentas();
      $('com-status').textContent = `Última importación: ${data.ultima_importacion ? fecha(data.ultima_importacion) + ' ' + data.ultima_importacion.slice(11, 16) : 'Sin registro'} · Última operación disponible en el alcance: ${fecha(data.fecha_maxima)} · Corte: ${fecha(data.hasta)}`;
    } catch (error) {
      if (id !== requestId) return;
      $('com-content').hidden = true; $('com-error').hidden = false;
      $('com-error').querySelector('span').textContent = error.message;
      $('com-status').textContent = 'Datos no disponibles.';
    } finally { if (id === requestId) root.removeAttribute('aria-busy'); }
  }
  function renderClientes() {
    const r = data.resumen;
    $('com-periodo').textContent = `Actividad: ${fecha(data.desde_30d)} → ${fecha(data.hasta)} · Corte: ${fecha(data.hasta)}`;
    $('com-kpis').replaceChildren(metric('Cartera histórica', number(r.total)), metric('Activos a 30 días', number(r.activos)), metric('Sin compra en 30 días', number(r.sin_compra)), metric('Tasa de actividad', r.tasa_actividad == null ? '—' : number(r.tasa_actividad) + '%'), metric('Nuevos a 30 días', number(r.nuevos)));
    $('com-comparacion').textContent = `${fecha(data.desde)} → ${fecha(data.hasta)} frente a ${fecha(data.desde_anterior)} → ${fecha(data.hasta_anterior)} · Misma cantidad de días.`;
    $('com-senales').replaceChildren(...[['Clientes únicos con atención', r.atencion], ['Sin recompra', r.sin_recompra], ['Compra en baja', r.baja], ['Menor variedad', r.variedad]].map(([label, value]) => {const box = elem('div', null, 'com-signal'); box.append(elem('strong', number(value)), elem('span', label)); return box;}));
    const counts = {atencion:r.atencion, activos:r.activos, sin_compra:r.sin_compra, todos:r.total};
    document.querySelectorAll('[data-vista]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.vista === state.get('vista')));
      if (!button.dataset.label) button.dataset.label = button.textContent;
      button.textContent = `${button.dataset.label} (${number(counts[button.dataset.vista])})`;
    });
    const rows = data.clientes.map(c => {
      const name = elem('button', c.cliente, 'com-name'); name.type = 'button'; name.onclick = () => openDetail(c.cliente, name);
      const vendors = elem('span', c.vendedores.length > 1 ? `${c.vendedores[0]} +${c.vendedores.length - 1}` : c.vendedores[0]); vendors.title = c.vendedores.join(', ');
      const signals = elem('div'); if (!c.senales.length) signals.append(elem('span', 'Sin señales')); else c.senales.forEach(s => signals.append(badge(s, 'attention')));
      return [name, vendors, badge(c.activo ? 'Activo' : 'Sin compra en 30 días', c.activo ? 'active' : ''), c.mostrar_origen ? conOrigen(fecha(c.ultima_compra), c.ultima_compra_tipos) : fecha(c.ultima_compra), number(c.dias), c.mostrar_origen ? porTipo(c) : money(c.importe), signals];
    });
    $('com-clientes').replaceChildren(rows.length ? table([['Cliente'], ['Vendedores'], ['Actividad a 30 días'], ['Última compra'], ['Días', true], ['Importe del período', true], ['Señales']], rows, 'com-client-table') : elem('p', 'No hay clientes en esta vista con los filtros elegidos. Probá otra vista o limpiá los filtros.', 'com-empty'));
    state.set('pagina', data.pagina); history.replaceState(null, '', location.pathname + '?' + state);
    $('com-list-count').textContent = `${number(data.total)} clientes en esta vista · Una fila por cliente; las señales pueden coincidir.`;
    $('com-page').textContent = `Página ${data.pagina} de ${data.paginas}`;
    $('com-prev').disabled = data.pagina <= 1; $('com-next').disabled = data.pagina >= data.paginas;
  }
  function renderVentas() {
    $('com-periodo').textContent = `${fecha(data.desde)} → ${fecha(data.hasta)} · Comparación: ${fecha(data.desde_anterior)} → ${fecha(data.hasta_anterior)} · Misma cantidad de días.${data.estado_datos === 'sin_operaciones' ? ' Sin operaciones en este período.' : ''}`;
    $('com-kpis').replaceChildren(...[['importe', 'Importe de ventas'], ['cajas', 'Cajas'], ['kilos', 'Kilos'], ['clientes', 'Clientes compradores']].map(([key, label]) => {
      const format = key === 'importe' ? money : number, k = data.kpis[key]; return metric(label, format(k.actual), comparativeText(k, format));
    }));
    drawEvolution();
    const measure = $('com-meta-medida').value, format = measure === 'importe' ? money : number;
    $('com-objetivos-nota').textContent = `Mes ${data.mes_objetivos} · Realizado desde el día 1 hasta ${fecha(data.hasta)}. Cumplimiento por suma de líneas del vendedor, sin prorrateo. Los filtros de cliente y producto ajustan el diagnóstico y mantienen el alcance de la meta.`;
    $('com-objetivos').replaceChildren(data.objetivos.length ? table([['Vendedor'], ['Realizado', true], ['Meta', true], ['Cumplimiento', true], ['Desvío', true], ['Estado']], data.objetivos.map(o => [o.nombre_visible, format(o.realizado), format(o.meta), o.cumplimiento == null ? '—' : number(o.cumplimiento * 100) + '%', format(o.diferencia_meta), o.estado + (o.cobertura === 'parcial' ? ' · cobertura parcial' : '')]), 'com-objective-table') : elem('p', 'No hay vendedores en este alcance.', 'com-empty'));
    $('com-rankings').replaceChildren(...[['vendedor', 'Participación por vendedor'], ['producto', 'Principales productos'], ['cliente', 'Concentración por cliente']].map(([key, title]) => {
      const section = elem('section'); section.append(elem('h3', title));
      const rows = data.composicion[key];
      if (!rows.length) section.append(elem('p', 'Sin operaciones en este período.', 'com-note'));
      rows.forEach(r => {
        const row = elem('div', null, 'com-rank-row'), label = elem('div', null, 'com-rank-label');
        label.append(elem('span', r.nombre), elem('strong', number(r.pct) + '%'));
        const track = elem('div', null, 'com-rank-track'), bar = elem('div', null, 'com-rank-bar'); bar.style.width = Math.min(100, Math.max(0, r.pct)) + '%'; track.append(bar);
        row.append(label, track, elem('small', money(r.plata))); section.append(row);
      });
      if (rows.length) {
        const details = elem('details'); details.append(elem('summary', 'Ver importes y cantidades'));
        const wrap = elem('div');
        renderCompositionTable(wrap, data.composicion_detalle?.[key] || rows);
        details.append(wrap); section.append(details);
      }
      return section;
    }));
  }
  const COMPOSITION_ROW_LIMITS = [10, 20, 50, 100];
  function renderCompositionTable(host, rows) {
    const controls = elem('div', null, 'com-rank-table-controls');
    const label = elem('label'); label.append(elem('span', 'Filas visibles'));
    const select = elem('select');
    COMPOSITION_ROW_LIMITS.forEach(limit => {
      select.add(new Option(String(limit), String(limit)));
    });
    select.value = String(COMPOSITION_ROW_LIMITS[0]);
    label.append(select); controls.append(label);
    const tableHost = elem('div', null, 'com-table-wrap');
    const renderRows = () => tableHost.replaceChildren(table(
      [['Nombre'], ['Importe', true], ['Cajas', true], ['Kilos', true]],
      rows.slice(0, Number(select.value)).map(row => [row.nombre, money(row.plata), number(row.cajas), number(row.kilos)])
    ));
    select.addEventListener('change', renderRows);
    renderRows(); host.append(controls, tableHost);
  }
  function drawEvolution() {
    if (chart) {chart.destroy(); chart = null;}
    const measure = $('com-evolucion-medida').value, key = measure === 'importe' ? 'monto' : measure;
    const actual = new Map(data.serie.map(r => [r.fecha, r[key]])), anterior = new Map(data.serie_anterior.map(r => [r.fecha, r[key]]));
    const start = new Date(data.desde + 'T00:00:00Z'), previous = new Date(data.desde_anterior + 'T00:00:00Z'), end = new Date(data.hasta + 'T00:00:00Z');
    const labels = [], values = [], prevValues = [], rows = [], format = measure === 'importe' ? money : number;
    for (let time = start.getTime(), oldTime = previous.getTime(); time <= end.getTime(); time += 86400000, oldTime += 86400000) {
      const d = new Date(time).toISOString().slice(0,10), p = new Date(oldTime).toISOString().slice(0,10);
      labels.push(fecha(d)); values.push(actual.get(d) || 0); prevValues.push(anterior.get(p) || 0);
      rows.push([fecha(d), format(actual.get(d) || 0), fecha(p), format(anterior.get(p) || 0)]);
    }
    $('com-serie-tabla').replaceChildren(table([['Fecha actual'], ['Actual', true], ['Fecha anterior'], ['Anterior', true]], rows));
    const canvas = $('com-evolucion');
    canvas.parentElement.hidden = typeof Chart === 'undefined';
    if (typeof Chart === 'undefined') { $('com-serie-tabla').parentElement.open = true; return; }
    const colors = charts ? charts.semantic : {neutral:'#234e70', previous:'#8496a8'};
    chart = charts.create(canvas, {type:'line', data:{labels, datasets:[{label:'Período actual', data:values, borderColor:colors.neutral, backgroundColor:colors.neutral, pointRadius:0, borderWidth:2}, {label:'Período anterior', data:prevValues, borderColor:colors.previous, backgroundColor:colors.previous, pointRadius:0, borderWidth:2, borderDash:[5,4]}]}, options:{scales:{x:{ticks:{maxTicksLimit:8}}, y:{ticks:{callback:value => number(value)}}}, plugins:{app360DataLabels:{formatter:value=>chartFormat(value,measure)},tooltip:{callbacks:{label:ctx => `${ctx.dataset.label}: ${format(ctx.parsed.y)}`}}}}});
  }
  function drawExtraChart(id, config) {
    if (extraCharts.has(id)) {extraCharts.get(id).destroy(); extraCharts.delete(id);}
    if (typeof Chart === 'undefined') return false;
    const canvas = $(id);
    if (!canvas) return false;
    extraCharts.set(id, charts.create(canvas, config));
    return true;
  }
  // Clic en una barra: fija el filtro de la dimensión y recarga la sección; otro clic
  // sobre la misma barra lo limpia. Usa el mismo camino que el filtro manual (change).
  // `nombres` es el valor de cada barra en el mismo orden que los datos.
  function barraConAccion(config, scope, dimension, nombres) {
    const cursorPuntero = (event, elementos) => {
      const nombre = elementos.length ? nombres[elementos[0].index] : '';
      event.native.target.style.cursor = nombre ? 'pointer' : 'default';
      event.native.target.title = !nombre ? '' : sectionFilters[scope][dimension] === nombre
        ? 'Clic para quitar el filtro'
        : `Clic para filtrar por ${nombre}`;
    };
    return {
      ...config,
      options: {
        ...config.options,
        onHover: cursorPuntero,
        onClick: (event, elementos) => {
          if (!elementos.length) return;
          const nombre = nombres[elementos[0].index];
          if (!nombre) return;
          const actual = sectionFilters[scope][dimension] || '';
          fijarFiltroDeSeccion(scope, dimension, actual === nombre ? '' : nombre);
        },
      },
    };
  }
  function fijarFiltroDeSeccion(scope, dimension, value) {
    sectionFilters[scope][dimension] = value;
    syncFilterScope(scope);
    const key = `${scope}_${dimension}`;
    if (value) state.set(key, value); else state.delete(key);
    const p = params(); state = p;
    history.replaceState(null, '', location.pathname + '?' + p); transferLink(p);
    refreshSectionFilters(scope);
  }
  const chartColors = charts ? charts.palette : ['#234e70','#4f8095','#769b82','#a97c3f','#9b7180','#667b91','#7a8a4f','#bf8065','#7d8fa3','#7f7c55'];
  function analyticsParams(scope) {
    const p = params();
    p.delete('q'); p.delete('vista'); p.delete('orden'); p.delete('pagina'); p.delete('por_pagina');
    if (scope && sectionFilters[scope]) {
      for (const dimension of ['cliente', 'producto']) {
        if (sectionFilters[scope][dimension]) p.set(dimension, sectionFilters[scope][dimension]);
        else p.delete(dimension);
      }
    }
    return p;
  }
  function showAnalyticsError(prefix, error, retry) {
    const host = $(`${prefix}-error`); host.hidden = false;
    host.querySelector('span').textContent = error.message || 'No se pudieron cargar los análisis.';
    host.querySelector('button').onclick = retry;
  }
  const monthLabel = value => {
    if (!value) return '—'; const [year, month] = value.split('-');
    return new Date(Number(year), Number(month)-1, 1).toLocaleDateString('es-AR',{month:'short',year:'2-digit'});
  };
  function accessibleTable(id, headers, rows) { $(id).replaceChildren(table(headers, rows)); }
  // Tabla de datos con control de teclado: cada nombre es un botón que aplica el mismo filtro
  // que el clic en la barra (Enter o Espacio sobre el botón).
  function tablaConFiltro(id, headers, rows, scope, dimension) {
    const nodo = table(headers, rows);
    if (!scope) return $(id).replaceChildren(nodo);
    nodo.querySelectorAll('tbody tr').forEach((tr, i) => {
      const nombre = rows[i]?.[0];
      const celda = tr.querySelector('td, th');
      if (!nombre || !celda) return;
      const boton = elem('button', nombre, 'com-name');
      boton.type = 'button';
      boton.title = sectionFilters[scope][dimension] === nombre
        ? 'Quitar el filtro' : `Filtrar por ${nombre}`;
      boton.setAttribute('aria-pressed', String(sectionFilters[scope][dimension] === nombre));
      boton.onclick = () => {
        const actual = sectionFilters[scope][dimension] || '';
        fijarFiltroDeSeccion(scope, dimension, actual === nombre ? '' : nombre);
      };
      celda.replaceChildren(boton);
    });
    $(id).replaceChildren(nodo);
  }
  async function loadQuantities() {
    const id = ++quantityRequestId, p = analyticsParams('analisis'); p.set('tipo', analysisDimension);
    p.set('medida', $('cantidad-medida').value);
    $('cantidad-error').hidden = true;
    $('cantidad-loading').hidden = false;
    try {
      const result = await get('/api/dashboard-comercial/analisis', p);
      if (id !== quantityRequestId) return;
      $('cantidad-loading').hidden = true;
      const top = result.top15 || [], measure = $('cantidad-medida').value;
      const value = row => measure === 'cajas' ? row.cajas : measure === 'kilos' ? (row.kilos ?? 0) : row.monto;
      const format = measure === 'importe' ? money : number;
      const titles = {producto:'Productos',cliente:'Clientes',vendedor:'Vendedores'};
      const labels = {cajas:'cajas',kilos:'kilos',importe:'importe'};
      $('cantidad-ranking-titulo').textContent = `15 principales ${titles[analysisDimension].toLowerCase()} por ${labels[measure]}`;
      const dimensionFiltro = analysisDimension === 'vendedor' ? null : analysisDimension;
      tablaConFiltro('cantidad-ranking-table', [[titles[analysisDimension]], [labels[measure], true]], top.map(row => [row.nombre, format(value(row))]), dimensionFiltro ? 'analisis' : null, dimensionFiltro);
      const hasTop = top.length > 0;
      $('cantidad-ranking').hidden = !hasTop; $('cantidad-ranking-empty').hidden = hasTop;
      if (hasTop) drawExtraChart('cantidad-ranking', barraConAccion({type:'bar', data:{labels:top.map(r=>r.nombre), datasets:[{label:labels[measure], data:top.map(value), backgroundColor:top.map((_,i)=>chartColors[i%chartColors.length]), borderRadius:3}]}, options:{indexAxis:'y', plugins:{app360DataLabels:{formatter:value=>chartFormat(value,measure)},legend:{display:false}, tooltip:{callbacks:{label:c=>format(c.parsed.x)}}}, scales:{x:{ticks:{callback:v=>format(v)}}}}}, 'analisis', analysisDimension, analysisDimension === 'vendedor' ? top.map(() => '') : top.map(r => r.nombre)));
      const series = result.evo_6m || [];
      const hasEvo = series.length > 0;
      $('cantidad-evolucion').hidden = !hasEvo; $('cantidad-evolucion-empty').hidden = hasEvo;
      accessibleTable('cantidad-evolucion-table', [['Mes'], [labels[measure], true]], series.map(row=>[monthLabel(row.periodo), format(value(row))]));
      if (hasEvo) drawExtraChart('cantidad-evolucion', {type:'line', data:{labels:series.map(r=>monthLabel(r.periodo)), datasets:[{label:labels[measure], data:series.map(value), borderColor:chartColors[0], backgroundColor:chartColors[0]+'30', fill:true, tension:.22, pointRadius:3}]}, options:{plugins:{app360DataLabels:{formatter:value=>chartFormat(value,measure)},legend:{display:false},tooltip:{callbacks:{label:c=>format(c.parsed.y)}}}, scales:{y:{ticks:{callback:v=>format(v)}}}}});
    } catch (error) { if (id === quantityRequestId) { $('cantidad-loading').hidden = true; showAnalyticsError('cantidad',error,loadQuantities); } }
  }
  async function loadMix() {
    const id = ++mixRequestId, p = analyticsParams('mix'); $('mix-error').hidden = true;
    $('mix-loading').hidden = false;
    try {
      const result = await get('/api/dashboard-comercial/mix', p);
      if (id !== mixRequestId) return;
      $('mix-loading').hidden = true;
      const palette = chartColors;
      const products = result.mix_global || [], diversity = result.diversidad_clientes || [];
      const clients = result.mix_por_cliente || [], topProducts = result.top_productos_stacked || [];
      const evolution = result.evo_mix || [], evoProducts = result.top_productos_evo || [];
      const hasProducts=products.length>0, hasDiversity=diversity.length>0, hasClients=clients.length>0&&topProducts.length>0, hasEvolution=evolution.length>0&&evoProducts.length>0;
      for (const [name, available] of [['mix-productos',hasProducts],['mix-variedad',hasDiversity],['mix-clientes',hasClients],['mix-evolucion',hasEvolution]]) {$(name).hidden=!available;$(`${name}-empty`).hidden=available;}
      tablaConFiltro('mix-productos-table', [['Producto'],['Cajas',true],['Participación',true]], products.map(r=>[r.producto,number(r.cajas),number(r.pct)+'%']), 'mix', 'producto');
      accessibleTable('mix-variedad-table', [['Cliente'],['Productos distintos',true],['Cajas',true]], diversity.map(r=>[r.cliente,number(r.n_productos),number(r.cajas)]));
      accessibleTable('mix-clientes-table', [['Cliente'],...topProducts.map(p=>[p,true])], clients.map(c=>[c.cliente,...topProducts.map(p=>number(c.productos?.[p]||0))]));
      accessibleTable('mix-evolucion-table', [['Mes'],...evoProducts.map(p=>[p,true])], evolution.map(r=>[monthLabel(r.periodo),...evoProducts.map(prod=>number(r.productos?.[prod]||0))]));
      if(hasProducts) drawExtraChart('mix-productos',barraConAccion({type:'doughnut',data:{labels:products.map(r=>r.producto),datasets:[{data:products.map(r=>r.cajas),backgroundColor:products.map((_,i)=>palette[i%palette.length]),borderColor:'#fff',borderWidth:2}]},options:{cutout:'55%',plugins:{app360DataLabels:{formatter:(value,index,dataset,chart)=>{const total=dataset.data.reduce((sum,item,i)=>sum+(chart.getDataVisibility(i)?Number(item)||0:0),0);return total?`${Math.round(Number(value)/total*100)}%`:'';}},tooltip:{callbacks:{label:c=>`${c.label}: ${number(c.parsed)} cajas`}}}}}, 'mix', 'producto', products.map(r=>r.producto)));
      if(hasDiversity) drawExtraChart('mix-variedad',{type:'bar',data:{labels:diversity.map(r=>r.cliente),datasets:[{label:'Productos distintos',data:diversity.map(r=>r.n_productos),backgroundColor:diversity.map((_,i)=>palette[i%palette.length]),borderRadius:3}]},options:{indexAxis:'y',plugins:{app360DataLabels:{formatter:value=>compactNumber(value)},legend:{display:false}}}});
      if(hasClients) drawExtraChart('mix-clientes',{type:'bar',data:{labels:clients.map(r=>r.cliente),datasets:topProducts.map((product,i)=>({label:product,data:clients.map(c=>c.productos?.[product]||0),backgroundColor:palette[i%palette.length],borderWidth:1}))},options:{indexAxis:'y',scales:{x:{stacked:true,ticks:{callback:v=>number(v)}},y:{stacked:true}},plugins:{app360DataLabels:{formatter:value=>compactNumber(value)},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${number(c.parsed.x)} cajas`}}}}});
      if(hasEvolution) drawExtraChart('mix-evolucion',{type:'line',data:{labels:evolution.map(r=>monthLabel(r.periodo)),datasets:evoProducts.map((product,i)=>({label:product,data:evolution.map(r=>r.productos?.[product]||0),borderColor:palette[i],backgroundColor:palette[i],borderWidth:2,tension:.22,pointRadius:3}))},options:{plugins:{app360DataLabels:{formatter:value=>compactNumber(value)},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${number(c.parsed.y)} cajas`}}},scales:{y:{ticks:{callback:v=>number(v)}}}}});
    } catch(error) { if(id===mixRequestId) { $('mix-loading').hidden = true; showAnalyticsError('mix',error,loadMix); } }
  }
  function toggleAnalysis(buttonId, bodyId, loadFn) {
    const button=$(buttonId), body=$(bodyId); button.addEventListener('click',()=>{
      const open=button.getAttribute('aria-expanded')!=='true'; button.setAttribute('aria-expanded',String(open)); button.querySelector(':scope > span:last-child').textContent=open?'−':'＋'; body.hidden=!open; if(open) loadFn();
    });
  }
  // Últimas operaciones del cliente: se piden al abrir su desplegable (20 por vez) y se guardan mientras la página está abierta.
  const opsCache = new Map();
  let opsVerTodos = false;
  function opsParams(name, modo, desplazamiento) {
    const p = new URLSearchParams();
    for (const key of ['fecha_desde', 'fecha_hasta', 'empresa', 'vendedor']) if (state.get(key)) p.set(key, state.get(key));
    p.set('cliente', name); p.set('modo', modo); p.set('desplazamiento', String(desplazamiento));
    return p;
  }
  function renderOperaciones(host, name, detailToken) {
    const section = elem('section'); section.setAttribute('aria-labelledby', 'com-ops-title');
    const title = elem('h3', 'Últimas operaciones'); title.id = 'com-ops-title';
    const switchLabel = elem('label', null, 'com-ops-toggle'), toggle = elem('input'); toggle.type = 'checkbox'; toggle.id = 'com-ops-todos';
    toggle.setAttribute('role', 'switch'); toggle.setAttribute('aria-describedby', 'com-ops-ayuda'); toggle.checked = opsVerTodos;
    switchLabel.append(toggle, elem('span', 'Ver todos los comprobantes'));
    const help = elem('p', 'Muestra ventas, presupuestos, facturas y notas de crédito tal como están en SabioGo.', 'com-note'); help.id = 'com-ops-ayuda';
    const list = elem('div', null, 'com-table-wrap'); list.setAttribute('aria-live', 'polite'); list.setAttribute('aria-busy', 'false');
    const status = elem('p', null, 'com-note'), more = elem('button', 'Ver más'); more.type = 'button'; more.hidden = true;
    const note = elem('p', 'Los totales del panel cuentan según el criterio del cliente. Esta lista muestra los comprobantes tal como están en SabioGo.', 'com-note');
    section.append(title, switchLabel, help, list, status, more, note); host.append(section);
    let token = 0;
    const modo = () => (toggle.checked ? 'todos' : 'criterio');
    const keyOf = () => `${name}\u0000${modo()}\u0000${opsParams(name, modo(), 0)}`;
    function paint(entry) {
      status.replaceChildren(); more.hidden = !entry.siguiente;
      if (!entry.items.length) { list.replaceChildren(elem('p', 'Este cliente no tiene operaciones en el período.', 'com-empty')); return; }
      list.replaceChildren(table([['Fecha'], ['Tipo'], ['Comprobante'], ['Importe', true], ['En los totales']],
        entry.items.map(o => [fecha(o.fecha), origen(o.tipo), [o.comprobante, o.nro].filter(Boolean).join(' · ') || '—', money(o.importe), o.cuenta_en_totales ? 'Sí' : 'No suma'])));
    }
    async function cargar(masPaginas) {
      const key = keyOf(), mine = ++token;
      let entry = opsCache.get(key);
      if (!entry) { entry = {items: [], siguiente: 0, cargado: false}; opsCache.set(key, entry); }
      if (entry.cargado && !masPaginas) { paint(entry); return; }
      list.setAttribute('aria-busy', 'true'); more.hidden = true; status.replaceChildren(elem('span', 'Cargando operaciones…'));
      try {
        const result = await get('/api/comercial/seguimiento-clientes/operaciones', opsParams(name, modo(), entry.siguiente || 0));
        if (mine !== token || detailToken !== detailId) return;
        entry.items = entry.items.concat(result.operaciones); entry.siguiente = result.siguiente; entry.cargado = true;
        paint(entry);
      } catch (error) {
        if (mine !== token || detailToken !== detailId) return;
        const retry = elem('button', 'Reintentar'); retry.type = 'button'; retry.onclick = () => cargar(masPaginas);
        const motivo = error instanceof TypeError || !error.message ? 'Revisá tu conexión e intentá de nuevo.' : error.message;
        status.replaceChildren(elem('span', `No se pudieron cargar las operaciones. ${motivo} `, 'com-error'), retry);
      } finally { list.setAttribute('aria-busy', 'false'); }
    }
    toggle.onchange = () => { opsVerTodos = toggle.checked; cargar(false); };
    more.onclick = () => cargar(true);
    cargar(false);
  }
  function closeDetail(restore = true) {
    if (!$('com-detalle')) return;
    ++detailId; $('com-detalle').hidden = true;
    if (restore && detailTrigger?.isConnected) detailTrigger.focus();
  }
  async function openDetail(name, trigger) {
    detailTrigger = trigger; const id = ++detailId;
    $('com-detalle').hidden = false; $('com-detalle-title').textContent = name;
    $('com-detalle-content').replaceChildren(elem('p', 'Cargando detalle…', 'com-note'));
    $('com-close').focus();
    const p = new URLSearchParams(state); p.set('cliente', name);
    try {
      const result = await get('/api/comercial/seguimiento-clientes/detalle', p);
      if (id !== detailId) return;
      const c = result.cliente, host = $('com-detalle-content'); host.replaceChildren();
      if (!c) {host.append(elem('p', 'No hay operaciones para este cliente en el alcance seleccionado.')); return;}
      host.append(elem('p', `Período: ${fecha(result.desde)} → ${fecha(result.hasta)} · Corte: ${fecha(result.hasta)}`, 'com-note'));
      host.append(elem('p', 'Vendedores del historial seleccionado: ' + c.vendedores.join(', ')));
      host.append(badge(c.activo ? 'Activo a 30 días' : 'Sin compra en 30 días', c.activo ? 'active' : ''));
      c.senales.forEach(s => host.append(badge(s, 'attention')));
      if (c.nuevo) host.append(badge('Nuevo a 30 días'));
      const ultima = elem('p'); ultima.append(document.createTextNode('Última compra: '));
      if (c.mostrar_origen) c.ultima_compra_tipos.forEach(t => ultima.append(origen(t)));
      ultima.append(document.createTextNode(`${fecha(c.ultima_compra)} · ${c.dias} días sin comprar.`)); host.append(ultima);
      host.append(metric('Importe del período', money(c.importe), comparativeText(c.comparacion)));
      if (c.mostrar_origen) {
        host.append(elem('h3', 'Importe del período por tipo de comprobante'));
        const tipos = elem('div', null, 'com-table-wrap');
        tipos.append(table([['Origen'], ['Operaciones', true], ['Importe', true]], ['PRE', 'FAC'].map(t => [origen(t), number(c.por_tipo[t].n), money(c.por_tipo[t].importe)])));
        host.append(tipos, elem('p', 'Cliente con criterio «Ambos»: presupuestos y facturas se suman por separado. Las notas de crédito (NC) se listan abajo y no suman. Un presupuesto que luego se factura podría figurar en los dos tipos.', 'com-note'));
      }
      host.append(elem('p', `Comparación: ${fecha(result.desde_anterior)} → ${fecha(result.hasta_anterior)}. Productos distintos: ${c.variedad.actual} ahora / ${c.variedad.anterior} antes.`, 'com-note'));
      host.append(elem('h3', 'Evolución de compras del período'));
      const evolution = elem('div', null, 'com-table-wrap'); evolution.append(c.serie.length ? table([['Fecha'], ['Importe', true]], c.serie.map(r => [fecha(r.fecha), money(r.importe)])) : elem('p', 'Sin compras en este período.', 'com-empty')); host.append(evolution);
      const products = elem('details'); products.append(elem('summary', `Productos comprados (${c.productos.length})`)); const wrap = elem('div', null, 'com-table-wrap'); wrap.append(c.productos.length ? table([['Producto'], ['Importe', true]], c.productos.map(r => [r.nombre, money(r.importe)])) : elem('p', 'Sin productos en este período.', 'com-note')); products.append(wrap); host.append(products);
      renderOperaciones(host, name, id);
    } catch (error) {
      if (id !== detailId) return;
      const retry = elem('button', 'Reintentar'); retry.onclick = () => openDetail(name, trigger);
      $('com-detalle-content').replaceChildren(elem('p', error.message, 'com-error'), retry);
    }
  }
  async function refreshWithoutJump(refresh) {
    const scrollX = window.scrollX, scrollY = window.scrollY;
    await refresh();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    window.scrollTo({left: scrollX, top: scrollY, behavior: 'instant'});
  }
  function refreshSectionFilters(scope) {
    if (scope === 'analisis') {
      if (!$('cantidades-body').hidden) return refreshWithoutJump(loadQuantities);
      return;
    }
    if (scope === 'mix') {
      if (!$('mix-body').hidden) return refreshWithoutJump(loadMix);
    }
  }
  // Buscador «Nombre del cliente»: filtra al escribir (300 ms) y también con Enter.
  let busquedaTimer = 0;
  form.elements.q?.addEventListener('input', () => {
    clearTimeout(busquedaTimer);
    busquedaTimer = setTimeout(() => { state.set('pagina', '1'); load(); }, 300);
  });
  form.addEventListener('submit', event => {event.preventDefault(); clearTimeout(busquedaTimer); state.set('pagina', '1'); load();});
  document.querySelectorAll('[data-com-filter-scope][data-com-filter-dimension]').forEach(select => select.addEventListener('change', () => {
    const scope = select.dataset.comFilterScope;
    const dimension = select.dataset.comFilterDimension;
    const value = readFilterValue(select);
    if (scope === 'principal') {
      setFilterValue(form.elements[dimension], value);
      syncFilterScope('principal');
      if (clientes) state.set('pagina', '1');
      refreshWithoutJump(load);
      return;
    }
    if (!sectionFilters[scope]) return;
    sectionFilters[scope][dimension] = value || '';
    syncFilterScope(scope);
    const key = `${scope}_${dimension}`;
    if (value) state.set(key, value); else state.delete(key);
    const p = params(); state = p;
    history.replaceState(null, '', location.pathname + '?' + p); transferLink(p);
    refreshSectionFilters(scope);
  }));
  $('com-retry').onclick = load;
  document.querySelectorAll('[data-period-preset]').forEach(button => button.addEventListener('click', () => {
    setPreset(button.dataset.periodPreset);
    if (clientes) state.set('pagina', '1');
    load();
  }));
  $('com-limpiar').onclick = () => {
    form.reset();
    for (const dimension of ['cliente', 'producto']) setFilterValue(form.elements[dimension], '');
    syncFilterScope('principal');
    for (const scope of Object.keys(sectionFilters)) {
      for (const dimension of ['cliente', 'producto']) sectionFilters[scope][dimension] = '';
      syncFilterScope(scope);
    }
    defaults();
    const preserved = new URLSearchParams();
    if (clientes) {
      for (const key of ['vista', 'orden', 'por_pagina']) {
        const value = state.get(key);
        if (value) preserved.set(key, value);
      }
      preserved.set('pagina', '1');
    }
    state = preserved;
    load();
  };
  if (clientes) {
    document.querySelectorAll('[data-vista]').forEach(b => b.onclick = () => {state.set('vista', b.dataset.vista); state.set('pagina', '1'); load();});
    for (const id of ['com-orden', 'com-size']) $(id).onchange = () => {state.set('pagina', '1'); load();};
    $('com-prev').onclick = () => {state.set('pagina', String(data.pagina - 1)); load();};
    $('com-next').onclick = () => {state.set('pagina', String(data.pagina + 1)); load();};
    $('com-close').onclick = () => closeDetail();
    document.addEventListener('keydown', event => {if (event.key === 'Escape' && !$('com-detalle').hidden) closeDetail();});
  } else if (root.dataset.mode === 'ventas') {
    $('com-evolucion-medida').onchange = () => {if (data) drawEvolution();};
    $('com-meta-medida').onchange = load;
    toggleAnalysis('cantidades-toggle','cantidades-body',loadQuantities);
    toggleAnalysis('mix-toggle','mix-body',loadMix);
    document.querySelectorAll('[data-analysis-dimension]').forEach(button=>button.addEventListener('click',()=>{
      analysisDimension=button.dataset.analysisDimension;
      document.querySelectorAll('[data-analysis-dimension]').forEach(item=>{const active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-pressed',String(active));});
      if(!$('cantidades-body').hidden) loadQuantities();
    }));
    $('cantidad-medida').onchange=()=>{if(!$('cantidades-body').hidden)loadQuantities();};
  } else {
    $('com-evolucion-medida').onchange = () => {if (data) drawEvolution();};
    $('com-meta-medida').onchange = load;
  }
  load();
})();
