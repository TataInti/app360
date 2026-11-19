(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const DIMENSIONES = {
    empresa: 'Empresa',
    rubro: 'Rubro',
    subrubro: 'Subrubro',
    marca: 'Marca',
    producto: 'Producto',
  };
  const MEDIDAS = {
    importe: { label: 'Importe', unidad: 'ARS', format: value => Number(value || 0).toLocaleString('es-AR', {style: 'currency', currency: 'ARS', maximumFractionDigits: 2}) },
    cajas: { label: 'Cajas', unidad: 'cajas', format: value => `${number(value)} cajas` },
    kilos: { label: 'Kilos', unidad: 'kg', format: value => `${number(value)} kg` },
  };
  const state = {vendedores: [], requestId: 0};

  function number(value) {
    return Number(value || 0).toLocaleString('es-AR', {maximumFractionDigits: 2});
  }

  function esc(value) {
    const entities = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
    return String(value ?? '').replace(/[&<>"']/g, character => entities[character]);
  }

  function currentMonth() {
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'No se pudo completar la operación.');
    return data;
  }

  function setError(id, message = '') {
    const element = $(id);
    element.textContent = message;
    element.hidden = !message;
  }

  function tomSelect(select, options = {}) {
    if (!window.TomSelect) return null;
    return new TomSelect(select, options);
  }

  async function cargarDatos() {
    const mes = $('periodoObjetivos').value;
    if (!mes) return;
    const requestId = ++state.requestId;
    $('objetivosCarga').hidden = false;
    $('listaVendedores').replaceChildren();
    setError('objetivosError');
    try {
      const [data, opciones] = await Promise.all([
        requestJson(`/api/objetivos-comerciales?${new URLSearchParams({mes, medida: 'importe'})}`),
        requestJson('/api/objetivos-comerciales/opciones'),
      ]);
      if (requestId !== state.requestId) return;
      state.vendedores = opciones.vendedores || [];
      const filas = (data.objetivos || []).filter(vendedor => (vendedor.lineas || []).length);
      $('objetivosVacio').hidden = filas.length > 0;
      filas.forEach(renderVendedorGuardado);
    } catch (error) {
      if (requestId !== state.requestId) return;
      setError('objetivosError', error.message || 'No se pudieron cargar los objetivos del período.');
      $('objetivosVacio').hidden = true;
    } finally {
      if (requestId === state.requestId) $('objetivosCarga').hidden = true;
    }
  }

  function resumenMedidas(vendedor) {
    const metas = vendedor.metas || {};
    const realizados = vendedor.realizados || {};
    return Object.keys(MEDIDAS).map(measure => {
      const meta = metas[measure];
      const avance = meta == null ? 'Sin meta' : `${number(realizados[measure] / meta * 100)}%`;
      const target = meta == null ? 'Sin meta' : MEDIDAS[measure].format(meta);
      return `<div class="oc-summary-measure"><strong>${MEDIDAS[measure].label} · ${esc(avance)}</strong><span>Meta: ${esc(target)}</span><span>Realizado de líneas: ${esc(MEDIDAS[measure].format(realizados[measure]))}</span></div>`;
    }).join('');
  }

  function crearTarjeta(nombre, ref, draft = false) {
    const card = document.createElement('article');
    card.className = `oc-seller-card${draft ? ' oc-seller-draft' : ''}`;
    if (ref) card.dataset.vendedorRef = ref;
    const title = draft
      ? '<label class="oc-seller-select">Vendedor comercial<select data-vendedor><option value="">Buscar o agregar vendedor…</option></select></label>'
      : `<div><h2>${esc(nombre)}</h2><p>Objetivos y avance calculados para ${esc($('periodoObjetivos').value)}.</p></div>`;
    card.innerHTML = `<div class="oc-seller-head"><div class="oc-seller-title">${title}</div><button type="button" class="oc-add-line" data-add-line>＋ Agregar objetivo</button></div><div class="oc-seller-summary" data-summary></div><div class="oc-lines" data-lines></div><p class="oc-line-error" data-card-error hidden></p>`;
    if (draft) configurarSelectorVendedor(card.querySelector('[data-vendedor]'), card);
    $('listaVendedores').append(card);
    $('objetivosVacio').hidden = true;
    return card;
  }

  function configurarSelectorVendedor(select, card) {
    const opts = state.vendedores.map(v => ({value: v.referencia, text: v.nombre_visible}));
    const instance = tomSelect(select, {
      valueField: 'value',
      labelField: 'text',
      searchField: ['text'],
      options: opts,
      create(input) {
        const nombre = input.trim().replace(/\s+/g, ' ');
        return nombre ? {value: `nombre:${nombre}`, text: nombre} : false;
      },
      createFilter: input => input.trim().length > 1,
      maxOptions: 100,
      placeholder: 'Buscar vendedor…',
      plugins: ['dropdown_input'],
      onChange(value) {
        card.dataset.vendedorRef = value || '';
        card.querySelector('[data-add-line]').disabled = !value;
      },
    });
    if (!instance) {
      select.replaceChildren(new Option('Seleccionar vendedor…', ''));
      opts.forEach(item => select.add(new Option(item.text, item.value)));
      select.addEventListener('change', () => {
        card.dataset.vendedorRef = select.value;
        card.querySelector('[data-add-line]').disabled = !select.value;
      });
    }
    card.querySelector('[data-add-line]').disabled = true;
  }

  function renderVendedorGuardado(vendedor) {
    const card = crearTarjeta(vendedor.nombre_visible || vendedor.vendedor, `id:${vendedor.vendedor_id}`);
    card.dataset.vendedorId = String(vendedor.vendedor_id);
    card.querySelector('[data-summary]').innerHTML = resumenMedidas(vendedor);
    (vendedor.lineas || []).forEach(linea => agregarFormularioLinea(card, linea));
  }

  function obtenerRefVendedor(card) {
    return card.dataset.vendedorRef || '';
  }

  function crearSelectDimension(value = '') {
    const select = document.createElement('select');
    select.dataset.dimensionTipo = '';
    select.setAttribute('aria-label', 'Nivel del objetivo');
    select.add(new Option('Elegir nivel…', ''));
    Object.entries(DIMENSIONES).forEach(([key, label]) => select.add(new Option(label, key)));
    select.value = value;
    return select;
  }

  function crearInputMeta(measure, value = 0) {
    const label = document.createElement('label');
    label.className = 'oc-line-target';
    label.innerHTML = `<span>${MEDIDAS[measure].label}</span><input type="number" min="0" step="0.01" value="${esc(value)}" placeholder="0" data-meta="${measure}" aria-label="Meta de ${MEDIDAS[measure].label}"><small>${MEDIDAS[measure].unidad}</small>`;
    return label;
  }

  function configurarCatalogoDimension(form) {
    const typeSelect = form.querySelector('[data-dimension-tipo]');
    const valueSelect = form.querySelector('[data-dimension-valor]');
    let valueInstance = null;

    function applyCapabilities(option) {
      const product = typeSelect.value === 'producto';
      for (const measure of ['cajas', 'kilos']) {
        const input = form.querySelector(`[data-meta="${measure}"]`);
        const supported = !product || Boolean(option?.[`supports_${measure}`]);
        input.disabled = !supported;
        input.title = supported ? '' : `${MEDIDAS[measure].label} se habilita cuando hay cantidades del producto en staging.`;
        if (!supported) input.value = '0';
      }
      const hint = form.querySelector('[data-product-hint]');
      hint.hidden = !product;
      hint.textContent = product
        ? 'El importe está disponible para todos los productos. Cajas y kilos se habilitan según las cantidades registradas en staging.'
        : '';
    }

    function setupValues(selected = '') {
      valueInstance?.destroy();
      valueSelect.replaceChildren(new Option('Buscar valor…', ''));
      const selectedType = typeSelect.value;
      applyCapabilities(null);
      if (!selectedType) return;
      const opts = selected ? [{value: selected, supports_cajas: true, supports_kilos: true}] : [];
      valueInstance = tomSelect(valueSelect, {
        valueField: 'value',
        labelField: 'value',
        searchField: ['value'],
        options: opts,
        items: selected ? [selected] : [],
        create: false,
        maxOptions: 100,
        loadThrottle: 250,
        shouldLoad: () => true,
        // Con 'focus', TomSelect consulta las opciones al abrir el desplegable sin escribir.
        preload: 'focus',
        placeholder: `Buscar ${DIMENSIONES[selectedType].toLowerCase()}…`,
        plugins: ['dropdown_input'],
        load(query, callback) {
          const params = new URLSearchParams({dimension: selectedType, q: query || ''});
          fetch(`/api/objetivos-comerciales/opciones?${params}`)
            .then(response => response.json())
            .then(data => callback(data.opciones || []))
            .catch(() => callback([]));
        },
        onChange(value) {
          applyCapabilities(value ? this.options[value] : null);
        },
      });
      if (!valueInstance) {
        valueSelect.addEventListener('focus', async () => {
          if (valueSelect.options.length > 1) return;
          const params = new URLSearchParams({dimension: selectedType});
          const data = await requestJson(`/api/objetivos-comerciales/opciones?${params}`);
          (data.opciones || []).forEach(option => valueSelect.add(new Option(option.value, option.value)));
        }, {once: true});
      }
      applyCapabilities(opts[0]);
    }

    typeSelect.addEventListener('change', () => setupValues());
    setupValues(valueSelect.dataset.selected || '');
    return {getValue: () => valueInstance?.getValue() || valueSelect.value, setType: value => {
      typeSelect.value = value || '';
      setupValues();
    }};
  }

  function agregarFormularioLinea(card, linea = null) {
    const form = document.createElement('form');
    form.className = 'oc-line';
    form.dataset.lineId = linea?.id ? String(linea.id) : '';
    const isNew = !linea;
    if (isNew) {
      form.innerHTML = `<div class="oc-line-head"><h3>Nueva línea de objetivo</h3><button type="button" data-cancel-line>Quitar línea</button></div><div class="oc-line-meta"><label>Nivel del objetivo<select data-dimension-tipo required></select></label><label>Valor del catálogo<select data-dimension-valor required></select></label><div data-targets></div></div><p class="com-note" data-product-hint hidden></p><div class="oc-line-footer"><span class="oc-line-realizado">El realizado se calculará desde PRE al guardar.</span><div class="oc-line-actions"><button type="submit" class="com-primary">Guardar línea</button></div></div><p class="oc-line-error" data-line-error hidden></p>`;
      const typeSelect = form.querySelector('[data-dimension-tipo]');
      typeSelect.replaceWith(crearSelectDimension());
      const targets = form.querySelector('[data-targets]');
      targets.replaceWith(...Object.keys(MEDIDAS).map(measure => crearInputMeta(measure, '')));
      const lineHeader = form.querySelector('.oc-line-head');
      lineHeader.querySelector('[data-cancel-line]').addEventListener('click', () => {
        form.remove();
        if (!card.querySelector('.oc-line')) card.remove();
      });
      form._dimensionControls = configurarCatalogoDimension(form);
    } else {
      form.innerHTML = `<div class="oc-line-head"><h3>${esc(DIMENSIONES[linea.dimension_tipo] || linea.dimension_tipo)} · ${esc(linea.dimension_valor)}</h3><button type="button" class="com-goal-delete" data-delete-line>Eliminar línea</button></div><div class="oc-line-meta" data-targets></div><div class="oc-line-footer"><span class="oc-line-realizado">Realizado leído desde PRE: ${esc(MEDIDAS.importe.format(linea.realizado_importe))} · ${esc(MEDIDAS.cajas.format(linea.realizado_cajas))} · ${esc(MEDIDAS.kilos.format(linea.realizado_kilos))}</span><div class="oc-line-actions"><button type="submit" class="com-primary">Guardar cambios</button></div></div><p class="oc-line-error" data-line-error hidden></p>`;
      const targets = form.querySelector('[data-targets]');
      targets.replaceWith(...Object.keys(MEDIDAS).map(measure => crearInputMeta(measure, linea[`meta_${measure}`])));
      if (linea.dimension_tipo === 'producto') {
        const caps = linea.capacidades || {};
        for (const measure of ['cajas', 'kilos']) {
          const input = form.querySelector(`[data-meta="${measure}"]`);
          const supported = Boolean(caps[`supports_${measure}`]) || Number(linea[`meta_${measure}`]) > 0;
          input.disabled = !supported;
          input.title = supported ? '' : `${MEDIDAS[measure].label} se habilita cuando hay cantidades del producto en staging.`;
        }
      }
      form.querySelector('[data-delete-line]').addEventListener('click', () => eliminarLinea(linea.id, form));
    }
    form.addEventListener('submit', event => guardarLinea(event, card, form, linea));
    card.querySelector('[data-lines]').append(form);
    return form;
  }

  function addVendorCard() {
    return crearTarjeta('', '', true);
  }

  function metasDelFormulario(form) {
    const metas = {importe: Number(form.querySelector('[data-meta="importe"]').value || 0)};
    for (const measure of ['cajas', 'kilos']) {
      const input = form.querySelector(`[data-meta="${measure}"]`);
      if (!input.disabled) metas[measure] = Number(input.value || 0);
    }
    return metas;
  }

  async function guardarLinea(event, card, form, linea) {
    event.preventDefault();
    const error = form.querySelector('[data-line-error]');
    error.hidden = true;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    form.classList.add('oc-line-saving');
    try {
      const metas = metasDelFormulario(form);
      if (!Object.values(metas).some(valor => valor > 0)) {
        throw new Error('Cargá una meta mayor que cero en importe, cajas o kilos para guardar la línea.');
      }
      const payload = Object.fromEntries(
        Object.entries(metas).map(([measure, valor]) => [`meta_${measure}`, valor]),
      );
      if (linea) {
        await requestJson(`/api/objetivos-comerciales/${encodeURIComponent(linea.id)}`, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
          body: JSON.stringify(payload),
        });
      } else {
        const dimensionType = form.querySelector('[data-dimension-tipo]').value;
        const dimensionValue = form._dimensionControls?.getValue() || form.querySelector('[data-dimension-valor]').value;
        if (!dimensionType || !dimensionValue) throw new Error('Elegí el nivel y el valor del catálogo para esta línea.');
        const ref = obtenerRefVendedor(card);
        if (!ref) throw new Error('Elegí un vendedor antes de guardar la línea.');
        payload.mes = $('periodoObjetivos').value;
        payload.dimension_tipo = dimensionType;
        payload.dimension_valor = dimensionValue;
        if (ref.startsWith('id:')) payload.vendedor_id = Number(ref.slice(3));
        else payload.vendedor_nombre = ref.slice(7);
        await requestJson('/api/objetivos-comerciales', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
          body: JSON.stringify(payload),
        });
      }
      await cargarDatos();
    } catch (errorValue) {
      error.textContent = errorValue.message || 'No se pudo guardar la línea.';
      error.hidden = false;
    } finally {
      button.disabled = false;
      form.classList.remove('oc-line-saving');
    }
  }

  async function eliminarLinea(id, form) {
    const confirmed = window.App360UI?.confirm
      ? await window.App360UI.confirm({title: 'Eliminar línea', message: 'Se eliminará esta línea del período.', confirmText: 'Eliminar', variant: 'danger'})
      : window.confirm('¿Eliminar esta línea del período?');
    if (!confirmed) return;
    try {
      await requestJson(`/api/objetivos-comerciales/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: {'X-CSRFToken': csrfToken},
      });
      await cargarDatos();
    } catch (error) {
      const message = form.querySelector('[data-line-error]');
      message.textContent = error.message || 'No se pudo eliminar la línea.';
      message.hidden = false;
    }
  }

  async function cargarLegacy() {
    $('legacyLoading').hidden = false;
    setError('legacyError');
    try {
      const data = await requestJson('/api/objetivos-comerciales/pendientes');
      state.vendedores = data.vendedores_comerciales?.map(v => ({
        id: v.id,
        nombre_visible: v.nombre_visible,
        referencia: `id:${v.id}`,
      })) || state.vendedores;
      const pending = data.pendientes || [];
      if (!pending.length) {
        $('legacyGoals').innerHTML = '<p class="com-empty">Los objetivos históricos están listos para convertir cuando los selecciones.</p>';
        return;
      }
      const rows = pending.map(goal => {
        const monthField = goal.mes_sugerido
          ? `<span>${esc(goal.mes_sugerido)}</span>`
          : `<input type="month" data-month required aria-label="Período mensual">`;
        const sellerOptions = state.vendedores.map(v => `<option value="${esc(v.id)}">${esc(v.nombre_visible)}</option>`).join('');
        return `<tr data-goal-id="${esc(goal.goal_id)}" data-month-suggested="${esc(goal.mes_sugerido || '')}"><td data-label="Empleado">${esc(goal.empleado || 'Sin empleado')}</td><td data-label="Período original">${esc(goal.periodo || 'Sin período')}</td><td data-label="Descripción">${esc(goal.descripcion || '')}</td><td data-label="Meta" class="num">${number(goal.meta)}</td><td data-label="Conversión"><form class="oc-legacy-form" data-convert-form novalidate><label>Vendedor comercial<select data-seller required><option value="">Buscar vendedor…</option>${sellerOptions}</select></label><label>Empresa<select data-company required><option value="">Elegir…</option><option value="CARNES">Carnes</option><option value="LACTEOS">Lácteos</option></select></label><label>Medida<select data-measure required><option value="">Elegir…</option><option value="importe">Importe</option><option value="cajas">Cajas</option><option value="kilos">Kilos</option></select></label><label>Mes ${monthField}</label><button class="com-primary" type="submit">Convertir a línea</button></form></td></tr>`;
      }).join('');
      $('legacyGoals').innerHTML = `<table><thead><tr><th>Empleado</th><th>Período original</th><th>Descripción</th><th>Meta</th><th>Vinculación comercial</th></tr></thead><tbody>${rows}</tbody></table>`;
      $('legacyGoals').querySelectorAll('[data-seller]').forEach(select => tomSelect(select, {
        allowEmptyOption: true,
        maxOptions: 100,
        placeholder: 'Buscar vendedor…',
        plugins: ['dropdown_input'],
      }));
    } catch (error) {
      setError('legacyError', error.message || 'No se pudieron cargar los objetivos históricos.');
    } finally {
      $('legacyLoading').hidden = true;
    }
  }

  async function convertirLegacy(event) {
    const form = event.target.closest('[data-convert-form]');
    if (!form) return;
    event.preventDefault();
    const row = form.closest('tr');
    const monthInput = row.querySelector('[data-month]');
    const payload = {
      goal_id: Number(row.dataset.goalId),
      vendedor_id: Number(form.querySelector('[data-seller]').value),
      empresa: form.querySelector('[data-company]').value,
      medida: form.querySelector('[data-measure]').value,
    };
    const faltantes = [];
    if (!payload.vendedor_id) faltantes.push('vendedor comercial');
    if (!payload.empresa) faltantes.push('empresa');
    if (!payload.medida) faltantes.push('medida');
    if (row.dataset.monthSuggested) payload.mes = row.dataset.monthSuggested;
    else if (monthInput?.value) payload.mes = monthInput.value;
    else faltantes.push('mes');
    if (faltantes.length) {
      setError('legacyError', `Para convertir este objetivo falta: ${faltantes.join(', ')}.`);
      return;
    }
    setError('legacyError');
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await requestJson('/api/objetivos-comerciales/convertir', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify(payload),
      });
      await Promise.all([cargarDatos(), cargarLegacy()]);
    } catch (error) {
      setError('legacyError', error.message || 'No se pudo convertir el objetivo histórico.');
    } finally {
      button.disabled = false;
    }
  }

  $('listaVendedores').addEventListener('click', event => {
    const button = event.target.closest('[data-add-line]');
    if (!button) return;
    const card = button.closest('.oc-seller-card');
    if (card.dataset.vendedorRef) agregarFormularioLinea(card);
  });
  $('legacyGoals').addEventListener('submit', convertirLegacy);
  $('agregarVendedor').addEventListener('click', addVendorCard);
  // Período en español: selectores de mes y año que mantienen el valor YYYY-MM en
  // #periodoObjetivos y en ?mes=, así un enlace reproduce el mismo período.
  const MESES_PERIODO = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  function periodoDesdeUrl() {
    const mes = new URLSearchParams(location.search).get('mes');
    return /^\d{4}-(0[1-9]|1[0-2])$/.test(mes || '') ? mes : null;
  }
  function fijarPeriodo(valor) {
    const [anio, mes] = valor.split('-');
    const actual = new Date().getFullYear();
    const anios = [];
    for (let y = Math.min(Number(anio), actual - 2); y <= Math.max(Number(anio), actual + 1); y++) anios.push(y);
    $('periodoAnio').replaceChildren(...anios.map(y => new Option(String(y), String(y))));
    $('periodoMes').replaceChildren(...MESES_PERIODO.map((nombre, i) => new Option(nombre, String(i + 1).padStart(2, '0'))));
    $('periodoAnio').value = anio;
    $('periodoMes').value = mes;
    $('periodoObjetivos').value = valor;
  }
  function cambiarPeriodoDesdeSelectores() {
    const valor = `${$('periodoAnio').value}-${$('periodoMes').value}`;
    $('periodoObjetivos').value = valor;
    const url = new URL(location.href);
    url.searchParams.set('mes', valor);
    history.replaceState(null, '', url);
    $('periodoObjetivos').dispatchEvent(new Event('change'));
  }
  $('periodoMes').addEventListener('change', cambiarPeriodoDesdeSelectores);
  $('periodoAnio').addEventListener('change', cambiarPeriodoDesdeSelectores);
  $('periodoObjetivos').addEventListener('change', cargarDatos);
  document.addEventListener('DOMContentLoaded', () => {
    fijarPeriodo(periodoDesdeUrl() || currentMonth());
    void cargarDatos();
    void cargarLegacy();
  });
})();
