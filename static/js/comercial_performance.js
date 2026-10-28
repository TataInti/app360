(() => {
  'use strict';
  const root = document.querySelector('.com-panel[data-mode="performance"]');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const number = value => value == null ? '—' : Number(value).toLocaleString('es-AR', {maximumFractionDigits: 1});
  const money = value => value == null ? '—' : Number(value).toLocaleString('es-AR', {style: 'currency', currency: 'ARS', maximumFractionDigits: 0});
  const fecha = value => value ? value.slice(0, 10).split('-').reverse().join('/') : '—';
  const elem = (tag, text, cls) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node; };
  const colors = window.App360Charts ? window.App360Charts.semantic : {neutral:'#234e70', neutralSoft:'rgba(35,78,112,.55)', previous:'#8496a8', previousSoft:'rgba(132,150,168,.4)'};
  let state = new URLSearchParams(location.search), data, chart, requestId = 0;
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
  const form = $('com-filtros');
  defaults();
  for (const name of ['empresa', 'vendedor', 'fecha_desde', 'fecha_hasta', 'cliente', 'producto']) {
    if (form.elements[name] && state.has(name)) form.elements[name].value = state.get(name);
  }
  if (!form.elements.empresa.value) form.elements.empresa.value = 'TODAS';
  if (state.get('vendedor')) form.elements.vendedor.add(new Option(state.get('vendedor'), state.get('vendedor'), true, true));
  if (state.get('cliente') || state.get('producto')) document.querySelector('.com-advanced').open = true;
  $('com-evolucion-medida').value = ['importe', 'cajas', 'kilos'].includes(state.get('medida')) ? state.get('medida') : 'importe';
  $('com-granularidad').value = ['dia', 'semana', 'mes'].includes(state.get('granularidad')) ? state.get('granularidad') : 'dia';
  function params() {
    const p = new URLSearchParams(new FormData(form));
    p.set('medida', $('com-evolucion-medida').value);
    p.set('granularidad', $('com-granularidad').value);
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
  function metric(label, value, note, variant) {
    const box = elem('div', null, `com-metric${variant ? ` ${variant}` : ''}`); box.append(elem('span', label), elem('strong', value));
    if (note) box.append(elem('small', note)); return box;
  }
  function comparativeText(c, format = money) {
    return `Anterior: ${format(c.anterior)} · Diferencia: ${format(c.diferencia)} · ${c.variacion_pct == null ? 'Sin base comparable' : number(c.variacion_pct) + '%'}`;
  }
  function transferLink(p) {
    const link = $('com-seguimiento');
    const query = new URLSearchParams();
    for (const key of ['empresa', 'vendedor', 'fecha_desde', 'fecha_hasta']) if (p.get(key)) query.set(key, p.get(key));
    link.href = '/comercial/seguimiento-clientes' + '?' + query;
  }
  async function options(p, id) {
    const opts = await get('/api/comercial/paneles/opciones', p);
    if (id !== requestId) return;
    const selected = p.get('vendedor') || '';
    form.elements.vendedor.replaceChildren(new Option('Todos los vendedores', ''));
    const values = new Set(opts.vendedores); if (selected) values.add(selected);
    [...values].sort((a,b) => a.localeCompare(b, 'es')).forEach(v => form.elements.vendedor.add(new Option(v, v)));
    form.elements.vendedor.value = selected;
  }
  function rankList(title, rows, moneyFormat = true) {
    const section = elem('section'); section.append(elem('h3', title));
    if (!rows.length) section.append(elem('p', 'Sin operaciones en este período.', 'com-note'));
    rows.forEach(r => {
      const row = elem('div', null, 'com-rank-row'), label = elem('div', null, 'com-rank-label');
      label.append(elem('span', r.nombre), elem('strong', number(r.pct) + '%'));
      const track = elem('div', null, 'com-rank-track'), bar = elem('div', null, 'com-rank-bar'); bar.style.width = Math.min(100, Math.max(0, r.pct)) + '%'; track.append(bar);
      const value = moneyFormat ? money(r.importe ?? r.plata) : `${number(r.importe)}`;
      row.append(label, track, elem('small', value)); section.append(row);
    });
    if (rows.length) {const details = elem('details'); details.append(elem('summary', 'Ver importes y cantidades')); const wrap = elem('div', null, 'com-table-wrap'); wrap.append(table([['Nombre'], ['Importe', true], ['Cajas', true], ['Kilos', true]], rows.map(r => [r.nombre, money(r.importe ?? r.plata), number(r.cajas), number(r.kilos)]))); details.append(wrap); section.append(details);}
    return section;
  }
  async function load() {
    if (!form.reportValidity()) return;
    const id = ++requestId, p = params(); state = p;
    history.replaceState(null, '', location.pathname + '?' + p); transferLink(p);
    $('com-error').hidden = true; $('com-content').hidden = true; root.setAttribute('aria-busy', 'true');
    $('com-status').textContent = 'Cargando datos…';
    try {
      const [result] = await Promise.all([get('/api/comercial/performance', p), options(p, id)]);
      if (id !== requestId) return;
      data = result;
      $('com-content').hidden = false;
      render();
      $('com-status').textContent = `Última importación: ${data.ultima_importacion ? fecha(data.ultima_importacion) + ' ' + data.ultima_importacion.slice(11, 16) : 'Sin registro'} · Última operación disponible en el alcance: ${fecha(data.fecha_maxima)} · Corte: ${fecha(data.hasta)}`;
    } catch (error) {
      if (id !== requestId) return;
      $('com-content').hidden = true; $('com-error').hidden = false;
      $('com-error').querySelector('span').textContent = error.message;
      $('com-status').textContent = 'Datos no disponibles.';
    } finally { if (id === requestId) root.removeAttribute('aria-busy'); }
  }
  function render() {
    const m = $('com-evolucion-medida').value, format = m === 'importe' ? money : number;
    $('com-periodo').textContent = `${fecha(data.desde)} → ${fecha(data.hasta)} · Comparación: ${fecha(data.desde_anterior)} → ${fecha(data.hasta_anterior)} · Misma cantidad de días.${data.estado_datos === 'sin_operaciones' ? ' Sin operaciones en este período.' : ''}`;
    $('com-kpis').replaceChildren(
      metric('Importe de ventas', money(data.kpis.importe.actual), comparativeText(data.kpis.importe), 'com-metric--sales'),
      metric('Cajas', number(data.kpis.cajas.actual), comparativeText(data.kpis.cajas, number)),
      metric('Kilos', number(data.kpis.kilos.actual), comparativeText(data.kpis.kilos, number)),
      metric('Ticket promedio', data.ticket_promedio_equipo == null ? '—' : money(data.ticket_promedio_equipo)),
      metric('Clientes compradores', number(data.kpis.clientes.actual), null, 'com-metric--buyers')
    );
    drawEvolution();
    const medida_column = m === 'importe' ? money : number;
    $('com-vendedores-nota').textContent = `Participación sobre el importe filtrado. Clientes: compradores en el período. Nuevos: primeros 30 días hasta el corte.`;
    const unattended = data.por_vendedor.length ? null : elem('p', data.estado_datos === 'sin_operaciones' ? 'No hay operaciones en este período.' : 'No hay vendedores en este alcance.', 'com-empty');
    $('com-vendedores').replaceChildren(unattended || table([['Vendedor'], ['Importe', true], ['Cajas', true], ['Kilos', true], ['Pedidos', true], ['Ticket promedio', true], ['Participación'], ['Clientes', true], ['Nuevos 30 días', true]], data.por_vendedor.map(v => [v.vendedor, money(v.importe), number(v.cajas), number(v.kilos), number(v.pedidos), v.ticket_promedio == null ? '—' : money(v.ticket_promedio), number(v.participacion) + '%', number(v.clientes_compradores), number(v.clientes_nuevos_30d)]), 'com-performance-table'));

    // Objetivos: se muestran solo si en el mes de corte hay metas cargadas.
    const objectivesSection = $('com-objetivos-section');
    if (data.tienen_meta) {
      objectivesSection.hidden = false;
      $('com-objetivos-nota').textContent = `Mes ${data.mes_objetivos} · Realizado desde el día 1 hasta ${fecha(data.hasta)}. Meta mensual completa, sin prorrateo. Desvío = realizado − meta.`;
      $('com-objetivos').replaceChildren(data.objetivos.length ? table([['Vendedor'], ['Empresa'], ['Realizado', true], ['Meta', true], ['Cumplimiento', true], ['Desvío', true], ['Estado']], data.objetivos.map(o => [o.nombre_visible, o.empresa, format(o.realizado), o.meta == null ? '—' : format(o.meta), o.cumplimiento == null ? '—' : number(o.cumplimiento * 100) + '%', o.desvio == null ? '—' : money(o.desvio), o.estado])) : elem('p', 'No hay vendedores con objetivo en este mes.', 'com-empty'));
    } else {
      objectivesSection.hidden = true;
      $('com-objetivos').replaceChildren();
    }

    $('com-composition').replaceChildren(
      rankList('Mix por empresa', data.mix_empresa),
      ...[['producto', 'Principales productos'], ['cliente', 'Concentración por cliente']].map(([key, title]) => rankList(title, data.composicion[key]))
    );
  }
  function drawEvolution() {
    if (chart) {chart.destroy(); chart = null;}
    const measure = $('com-evolucion-medida').value, key = measure;
    const series = data.evolucion.actual, seriesPrev = data.evolucion.anterior;
    const labels = [], values = [], prevValues = [], rows = [], format = measure === 'importe' ? money : number;
    const n = Math.max(series.length, seriesPrev.length);
    for (let i = 0; i < n; i++) {
      const a = series[i], b = seriesPrev[i];
      labels.push(a ? (a.etiqueta || a.fecha) : (b.etiqueta || b.fecha));
      values.push(a ? a[key] || 0 : 0); prevValues.push(b ? b[key] || 0 : 0);
      rows.push([a ? (a.etiqueta || a.fecha) : '—', format(a ? a[key] || 0 : 0), b ? (b.etiqueta || b.fecha || (b.fecha.slice(0,10))) : '—', format(b ? b[key] || 0 : 0)]);
    }
    $('com-serie-tabla').replaceChildren(table([['Período actual'], ['Actual', true], ['Período anterior'], ['Anterior', true]], rows));
    const canvas = $('com-evolucion');
    canvas.parentElement.hidden = typeof Chart === 'undefined';
    if (typeof Chart === 'undefined') { $('com-serie-tabla').parentElement.open = true; return; }
    chart = window.App360Charts.create(canvas, {type: measure === 'importe' ? 'line' : 'bar', data:{labels, datasets:[{label:'Período actual', data:values, borderColor:colors.neutral, backgroundColor: measure === 'importe' ? colors.neutral : colors.neutralSoft, pointRadius:0, borderWidth:2, borderRadius:3}, {label:'Período anterior', data:prevValues, borderColor:colors.previous, backgroundColor:colors.previousSoft, pointRadius:0, borderWidth:2, borderDash:[5,4]}]}, options:{scales:{x:{ticks:{maxTicksLimit:10, autoSkip:true}}, y:{ticks:{callback:value => number(value)}}}, plugins:{tooltip:{callbacks:{label:ctx => `${ctx.dataset.label}: ${format(ctx.parsed.y)}`}}}}});
  }
  form.addEventListener('submit', event => {event.preventDefault(); load();});
  $('com-retry').onclick = load;
  document.querySelectorAll('[data-period-preset]').forEach(button => button.addEventListener('click', () => {
    setPreset(button.dataset.periodPreset);
    load();
  }));
  $('com-limpiar').onclick = () => {form.reset(); defaults(); state = new URLSearchParams(); $('com-evolucion-medida').value = 'importe'; $('com-granularidad').value = 'dia'; load();};
  for (const id of ['com-evolucion-medida', 'com-granularidad']) $(id).onchange = load;
  load();
})();