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
  const state = {vendedores: [], requestId: 0, cargas: 0};

  function number(value) {
    return Number(value || 0).toLocaleString('es-AR', {maximumFractionDigits: 2});
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

  // Indicador «Cargando…» del período: visible mientras haya una operación pendiente.
  function marcarCarga(delta) {
    state.cargas = Math.max(0, state.cargas + delta);
    $('objetivosCarga').hidden = state.cargas === 0;
  }

  function tomSelect(select, options = {}) {
    if (!window.TomSelect) return null;
    return new TomSelect(select, options);
  }

  async function cargarDatos() {
    const mes = $('periodoObjetivos').value;
    if (!mes) return;
    const requestId = ++state.requestId;
    marcarCarga(1);
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
      marcarCarga(-1);
    }
  }

  function resumenMedidas(vendedor) {
    const metas = vendedor.metas || {};
    const realizados = vendedor.realizados || {};
    return Object.keys(MEDIDAS).map(measure => {
      const meta = metas[measure];
      const avance = meta == null ? 'Sin meta' : `${number(realizados[measure] / meta * 100)}%`;
      const target = meta == null ? 'Sin meta' : MEDIDAS[measure].format(meta);
      return `<div class="oc-summary-measure"><strong>${escapeHtml(MEDIDAS[measure].label)} · ${escapeHtml(avance)}</strong><span>Meta: ${escapeHtml(target)}</span><span>Realizado de líneas: ${escapeHtml(MEDIDAS[measure].format(realizados[measure]))}</span></div>`;
    }).join('');
  }

  function crearTarjeta(nombre, ref, draft = false) {
    const card = document.createElement('article');
    card.className = `oc-seller-card${draft ? ' oc-seller-draft' : ''}`;
    if (ref) card.dataset.vendedorRef = ref;
    const title = draft
      ? '<label class="oc-seller-select">Vendedor comercial<select data-vendedor><option value="">Buscar o agregar vendedor…</option></select></label>'
      : `<div><h2>${escapeHtml(nombre)}</h2><p>Objetivos y avance calculados para ${escapeHtml($('periodoObjetivos').value)}.</p></div>`;
    card.innerHTML = `<div class="oc-seller-head"><div class="oc-seller-title">${title}</div><div class="oc-seller-actions"></div></div><div class="oc-seller-summary" data-summary></div><div class="oc-lines" data-lines></div><p class="oc-line-error" data-card-error hidden></p>`;
    card.querySelector('.oc-seller-actions').append(...botonesEncabezado(draft));
    if (draft) {
      configurarSelectorVendedor(card.querySelector('[data-vendedor]'), card);
      card.querySelector('[data-cancel-draft]').addEventListener('click', () => quitarTarjeta(card));
    }
    $('listaVendedores').append(card);
    $('objetivosVacio').hidden = true;
    return card;
  }

  // Botones del encabezado: «Cancelar» solo en el borrador; «Agregar objetivo» en todas las tarjetas.
  function botonesEncabezado(draft) {
    const botones = [];
    if (draft) {
      const cancelar = document.createElement('button');
      cancelar.type = 'button';
      cancelar.dataset.cancelDraft = '';
      cancelar.textContent = 'Cancelar';
      botones.push(cancelar);
    }
    const agregar = document.createElement('button');
    agregar.type = 'button';
    agregar.className = 'oc-add-line';
    agregar.dataset.addLine = '';
    agregar.textContent = '＋ Agregar objetivo';
    botones.push(agregar);
    return botones;
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
    card._vendedorSelect = instance;
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

  // Importe: formato de dinero de App360UI («$ 1.234,56»). Cajas y kilos: número es-AR sin «$».
  function activarCampoMeta(input, measure, valor) {
    const tieneValor = valor !== undefined && valor !== null && Number(valor) !== 0;
    if (measure === 'importe') {
      const money = window.App360UI?.money;
      if (!input || !money) return;
      money.bindInput(input);
      if (tieneValor) money.setValue(input, valor);
      return;
    }
    input.addEventListener('blur', () => {
      const numero = leerMeta(input);
      if (Number.isFinite(numero) && input.value.trim()) input.value = number(numero);
    });
    if (tieneValor) input.value = number(valor);
  }
  // Devuelve el importe de la meta, 0 si está vacía o NaN si el texto no es un número.
  function leerMeta(input) {
    if (!String(input?.value ?? '').trim()) return 0;
    const valor = window.App360UI?.money?.getValue(input);
    return Number.isFinite(valor) ? valor : NaN;
  }
  // Campo de meta con su unidad dentro del campo (ARS, cajas, kg) y la etiqueta en la misma grilla.
  function crearInputMeta(measure, value = 0) {
    const label = document.createElement('label');
    label.className = 'oc-line-target';
    label.innerHTML = `<span>${escapeHtml(MEDIDAS[measure].label)}</span><span class="oc-unit-field"><input type="text" inputmode="decimal" autocomplete="off" placeholder="0" data-meta="${escapeHtml(measure)}" aria-label="Meta de ${escapeHtml(MEDIDAS[measure].label)}"><small>${escapeHtml(MEDIDAS[measure].unidad)}</small></span>`;
    activarCampoMeta(label.querySelector('[data-meta]'), measure, value);
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
        if (!supported) input.value = '';
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
      form.innerHTML = `<div class="oc-line-head"><h3>Nueva línea de objetivo</h3><button type="button" data-cancel-line>Quitar línea</button></div><p class="com-note oc-product-hint" data-product-hint hidden></p><div class="oc-line-meta"><label>Nivel del objetivo<select data-dimension-tipo required></select></label><label>Valor del catálogo<select data-dimension-valor required></select></label></div><div class="oc-line-footer"><span class="oc-line-realizado">El realizado se calculará desde PRE al guardar.</span><div class="oc-line-actions"><button type="submit" class="com-primary">Guardar línea</button></div></div><p class="oc-line-error" data-line-error hidden></p>`;
      const typeSelect = form.querySelector('[data-dimension-tipo]');
      typeSelect.replaceWith(crearSelectDimension());
      form.querySelector('.oc-line-meta').append(...Object.keys(MEDIDAS).map(measure => crearInputMeta(measure, '')));
      const lineHeader = form.querySelector('.oc-line-head');
      lineHeader.querySelector('[data-cancel-line]').addEventListener('click', () => {
        form.remove();
        if (!card.querySelector('.oc-line')) quitarTarjeta(card);
      });
      form._dimensionControls = configurarCatalogoDimension(form);
    } else {
      form.classList.add('oc-line-guardada');
      form.innerHTML = `<div class="oc-line-head"><h3>${escapeHtml(DIMENSIONES[linea.dimension_tipo] || linea.dimension_tipo)} · ${escapeHtml(linea.dimension_valor)}</h3><button type="button" class="com-goal-delete" data-delete-line>Eliminar línea</button></div><div class="oc-line-meta"></div><div class="oc-line-footer"><span class="oc-line-realizado">Realizado leído desde PRE: ${escapeHtml(MEDIDAS.importe.format(linea.realizado_importe))} · ${escapeHtml(MEDIDAS.cajas.format(linea.realizado_cajas))} · ${escapeHtml(MEDIDAS.kilos.format(linea.realizado_kilos))}</span><div class="oc-line-actions"><button type="submit" class="com-primary">Guardar cambios</button></div></div><p class="oc-line-error" data-line-error hidden></p>`;
      form.querySelector('.oc-line-meta').append(...Object.keys(MEDIDAS).map(measure => crearInputMeta(measure, linea[`meta_${measure}`])));
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
      // Lo guardado sirve de referencia para habilitar «Guardar cambios» solo con cambios reales.
      form._metasGuardadas = metasDelFormulario(form);
      form.addEventListener('input', () => sincronizarGuardar(form));
      sincronizarGuardar(form);
    }
    form.addEventListener('submit', event => guardarLinea(event, form, linea));
    card.querySelector('[data-lines]').append(form);
    return form;
  }

  function addVendorCard() {
    const card = crearTarjeta('', '', true);
    card.scrollIntoView({block: 'start'});
    return card;
  }

  function metasDelFormulario(form) {
    const metas = {importe: leerMeta(form.querySelector('[data-meta="importe"]'))};
    for (const measure of ['cajas', 'kilos']) {
      const input = form.querySelector(`[data-meta="${measure}"]`);
      if (!input.disabled) metas[measure] = leerMeta(input);
    }
    return metas;
  }

  async function guardarLinea(event, form, linea) {
    event.preventDefault();
    const card = form.closest('.oc-seller-card');
    const error = form.querySelector('[data-line-error]');
    error.hidden = true;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    form.classList.add('oc-line-saving');
    marcarCarga(1);
    try {
      const metas = metasDelFormulario(form);
      if (Object.values(metas).some(valor => Number.isNaN(valor))) {
        throw new Error('Ingresá un valor numérico válido, por ejemplo 1.234,56.');
      }
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
        form._metasGuardadas = metas;
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
        const {objetivo} = await requestJson('/api/objetivos-comerciales', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
          body: JSON.stringify(payload),
        });
        convertirBorrador(card, objetivo);
        form.replaceWith(agregarFormularioLinea(card, objetivo));
      }
      await actualizarResumen(card);
    } catch (errorValue) {
      error.textContent = errorValue.message || 'No se pudo guardar la línea.';
      error.hidden = false;
    } finally {
      button.disabled = false;
      form.classList.remove('oc-line-saving');
      sincronizarGuardar(form);
      marcarCarga(-1);
    }
  }

  async function eliminarLinea(id, form) {
    const confirmed = window.App360UI?.confirm
      ? await window.App360UI.confirm({title: 'Eliminar línea', message: 'Se eliminará esta línea del período.', confirmText: 'Eliminar', variant: 'danger'})
      : window.confirm('¿Eliminar esta línea del período?');
    if (!confirmed) return;
    const card = form.closest('.oc-seller-card');
    marcarCarga(1);
    try {
      await requestJson(`/api/objetivos-comerciales/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: {'X-CSRFToken': csrfToken},
      });
      form.remove();
      if (card.querySelector('.oc-line')) await actualizarResumen(card);
      else quitarTarjeta(card);
    } catch (error) {
      const message = form.querySelector('[data-line-error]');
      message.textContent = error.message || 'No se pudo eliminar la línea.';
      message.hidden = false;
    } finally {
      marcarCarga(-1);
    }
  }

  // Vuelve a leer el resumen de una sola tarjeta; las demás tarjetas y los borradores no cambian.
  async function actualizarResumen(card) {
    const requestId = state.requestId;
    try {
      const params = new URLSearchParams({mes: $('periodoObjetivos').value, medida: 'importe'});
      const data = await requestJson(`/api/objetivos-comerciales?${params}`);
      if (requestId !== state.requestId || !card.isConnected) return;
      const vendedor = (data.objetivos || []).find(item => String(item.vendedor_id) === card.dataset.vendedorId);
      card.querySelector('[data-summary]').innerHTML = vendedor ? resumenMedidas(vendedor) : '';
    } catch (error) {
      if (requestId === state.requestId) setError('objetivosError', error.message || 'No se pudo actualizar el resumen del vendedor.');
    }
  }

  // Un borrador pasa a tarjeta guardada al guardar su primera línea: cambia el título y se quita «Cancelar».
  function convertirBorrador(card, objetivo) {
    if (!card.classList.contains('oc-seller-draft')) return;
    card._vendedorSelect?.destroy();
    card.classList.remove('oc-seller-draft');
    card.dataset.vendedorId = String(objetivo.vendedor_id);
    card.dataset.vendedorRef = `id:${objetivo.vendedor_id}`;
    card.querySelector('.oc-seller-title').innerHTML = `<div><h2>${escapeHtml(objetivo.nombre_visible)}</h2><p>Objetivos y avance calculados para ${escapeHtml($('periodoObjetivos').value)}.</p></div>`;
    card.querySelector('[data-cancel-draft]')?.remove();
  }

  // Quita una tarjeta (borrador descartado o vendedor sin líneas) y muestra el aviso si la lista queda vacía.
  function quitarTarjeta(card) {
    card._vendedorSelect?.destroy();
    card.remove();
    $('objetivosVacio').hidden = $('listaVendedores').children.length > 0;
  }

  // «Guardar cambios» solo se habilita cuando alguna meta de la línea cambió respecto de lo guardado.
  function sincronizarGuardar(form) {
    const boton = form.querySelector('button[type="submit"]');
    const guardadas = form._metasGuardadas;
    if (!boton || !guardadas || form.classList.contains('oc-line-saving')) return;
    const actuales = metasDelFormulario(form);
    boton.disabled = Object.keys(actuales).every(measure => actuales[measure] === guardadas[measure]);
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
        const anioOrigen = (String(goal.periodo || '').match(/\b(?:19|20)\d{2}\b/) || [])[0] || '';
        const monthField = goal.mes_sugerido
          ? `<span>${escapeHtml(goal.mes_sugerido)}</span>`
          : `<span class="oc-periodo-pareja"><select data-month-mes required aria-label="Mes"></select><select data-month-anio required aria-label="Año"></select></span>`;
        const sellerOptions = state.vendedores.map(v => `<option value="${escapeHtml(v.id)}">${escapeHtml(v.nombre_visible)}</option>`).join('');
        return `<tr data-goal-id="${escapeHtml(goal.goal_id)}" data-month-suggested="${escapeHtml(goal.mes_sugerido || '')}" data-anio-origen="${escapeHtml(anioOrigen)}"><td data-label="Empleado">${escapeHtml(goal.empleado || 'Sin empleado')}</td><td data-label="Período original">${escapeHtml(goal.periodo || 'Sin período')}</td><td data-label="Descripción">${escapeHtml(goal.descripcion || '')}</td><td data-label="Meta" class="num">${escapeHtml(number(goal.meta))}</td><td data-label="Conversión"><form class="oc-legacy-form" data-convert-form novalidate><label>Vendedor comercial<select data-seller required><option value="">Buscar vendedor…</option>${sellerOptions}</select></label><label>Empresa<select data-company required><option value="">Elegir…</option><option value="CARNES">Carnes</option><option value="LACTEOS">Lácteos</option></select></label><label>Medida<select data-measure required><option value="">Elegir…</option><option value="importe">Importe</option><option value="cajas">Cajas</option><option value="kilos">Kilos</option></select></label><label>Mes ${monthField}</label><button class="com-primary" type="submit">Convertir a línea</button></form></td></tr>`;
      }).join('');
      $('legacyGoals').innerHTML = `<table><thead><tr><th>Empleado</th><th>Período original</th><th>Descripción</th><th>Meta</th><th>Vinculación comercial</th></tr></thead><tbody>${rows}</tbody></table>`;
      $('legacyGoals').querySelectorAll('tr[data-goal-id]').forEach(row => {
        const mesSelect = row.querySelector('[data-month-mes]');
        if (!mesSelect) return;
        llenarSelectoresPeriodo(mesSelect, row.querySelector('[data-month-anio]'), {
          anioOrigen: Number(row.dataset.anioOrigen) || null,
          vacio: true,
        });
      });
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
    const mesSelect = row.querySelector('[data-month-mes]');
    const anioSelect = row.querySelector('[data-month-anio]');
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
    else if (mesSelect?.value && anioSelect?.value) payload.mes = `${anioSelect.value}-${mesSelect.value}`;
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
  // Mes y año en español, con valor YYYY-MM. La barra de período y la conversión de
  // objetivos históricos usan este mismo helper. Sin valor, deja «Mes…» y «Año…» vacíos.
  function llenarSelectoresPeriodo(selectMes, selectAnio, {valor = '', anioOrigen = null, vacio = false} = {}) {
    const [anio = '', mes = ''] = valor ? valor.split('-') : [];
    const actual = new Date().getFullYear();
    const referencia = Number(anio) || actual;
    const desde = Math.min(referencia, anioOrigen || referencia, actual - 2);
    const hasta = Math.max(referencia, actual + 1);
    const anios = [];
    for (let y = desde; y <= hasta; y++) anios.push(new Option(String(y), String(y)));
    const meses = MESES_PERIODO.map((nombre, i) => new Option(nombre, String(i + 1).padStart(2, '0')));
    if (vacio) {
      anios.unshift(new Option('Año…', ''));
      meses.unshift(new Option('Mes…', ''));
    }
    selectAnio.replaceChildren(...anios);
    selectMes.replaceChildren(...meses);
    selectAnio.value = anio;
    selectMes.value = mes;
  }
  function fijarPeriodo(valor) {
    llenarSelectoresPeriodo($('periodoMes'), $('periodoAnio'), {valor});
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
