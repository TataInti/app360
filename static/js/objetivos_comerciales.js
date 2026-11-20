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
    importe: { label: 'Importe', unidad: 'ARS', format: value => pesos(value) },
    cajas: { label: 'Cajas', unidad: 'cajas', format: value => `${number(value)} cajas` },
    kilos: { label: 'Kilos', unidad: 'kg', format: value => `${number(value)} kg` },
  };
  const MEDIDAS_EQUIPO = ['importe', 'cajas', 'kilos'];
  // Tono del punto de estado según el texto que devuelve la API. El texto se muestra tal cual.
  const TONO_ESTADO = {
    'Cumplido': 'ok',
    'En ritmo': 'ok',
    'Por debajo del ritmo esperado': 'warn',
    'No cumplido': 'warn',
    'No iniciado': 'none',
    'Sin meta': 'none',
  };
  const state = {vendedores: [], resumen: null, requestId: 0, cargas: 0, secuencia: 0};

  function number(value) {
    return Number(value || 0).toLocaleString('es-AR', {maximumFractionDigits: 2});
  }

  // Importes sin centavos (hallazgo 9): «$ 1.234.567».
  function pesos(value) {
    return Number(value || 0).toLocaleString('es-AR', {style: 'currency', currency: 'ARS', maximumFractionDigits: 0});
  }

  // Porcentaje entero: «268 %».
  function porcentaje(value) {
    return `${Math.round(Number(value) * 100).toLocaleString('es-AR')}\u00a0%`;
  }

  // Cajas y kilos se leen «realizado / meta»; sin meta, «—».
  function realMeta(real, meta) {
    return `${number(real)} / ${meta === null || meta === undefined ? '—' : number(meta)}`;
  }

  function currentMonth() {
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
  }

  // Crea un nodo sin HTML de cadena: los textos y atributos entran como datos, no como markup.
  function el(tag, attrs = {}, ...hijos) {
    const nodo = document.createElement(tag);
    for (const [clave, valor] of Object.entries(attrs)) {
      if (valor === null || valor === undefined || valor === false) continue;
      if (clave === 'className') nodo.className = valor;
      else if (clave === 'text') nodo.textContent = valor;
      else if (clave === 'data') Object.entries(valor).forEach(([dato, dv]) => { nodo.dataset[dato] = String(dv); });
      else nodo.setAttribute(clave, valor === true ? '' : String(valor));
    }
    nodo.append(...hijos.filter(hijo => hijo !== null && hijo !== undefined));
    return nodo;
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

  // TomSelect devuelve el foco al campo al terminar de elegir y, con openOnFocus, reabre el desplegable
  // (taparía los controles de abajo, como «Agregar objetivo»). Tras elegir, cada selector desactiva esa
  // reapertura y la restaura con el siguiente clic en el control.
  function tomSelect(select, options = {}) {
    if (!window.TomSelect) return null;
    const instancia = new TomSelect(select, options);
    instancia.control.addEventListener('mousedown', () => { instancia.settings.openOnFocus = true; }, true);
    return instancia;
  }
  function cerrarTrasElegir(instancia) {
    instancia.settings.openOnFocus = false;
    instancia.close();
  }

  function urlObjetivos() {
    return `/api/objetivos-comerciales?${new URLSearchParams({mes: $('periodoObjetivos').value, medida: 'importe'})}`;
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
        requestJson(urlObjetivos()),
        requestJson('/api/objetivos-comerciales/opciones'),
      ]);
      if (requestId !== state.requestId) return;
      state.vendedores = opciones.vendedores || [];
      state.resumen = data;
      (data.objetivos || [])
        .filter(vendedor => (vendedor.lineas || []).length)
        .forEach(vendedor => montarGrupo(crearGrupoGuardado(vendedor)));
      actualizarPresentacion();
    } catch (error) {
      if (requestId !== state.requestId) return;
      setError('objetivosError', error.message || 'No se pudieron cargar los objetivos del período.');
      $('objetivosVacio').hidden = true;
      $('objetivosTablaWrap').hidden = true;
    } finally {
      marcarCarga(-1);
    }
  }

  // Un grupo es un vendedor: fila de resumen, zona expandible con sus líneas y, si es borrador,
  // el selector de vendedor. Los datos de la fila se escriben con pintarResumen.
  function crearGrupo({ref = '', id = null, nombre = '', draft = false} = {}) {
    state.secuencia += 1;
    const detalleId = `oc-detalle-${state.secuencia}`;
    const grupo = el('tr', {className: draft ? 'oc-row oc-group-draft' : 'oc-row', data: {sellerGroup: '', sellerRow: '', summary: '', vendedorRef: ref}});
    if (draft) grupo.dataset.sellerDraft = '';
    if (id !== null) grupo.dataset.vendedorId = String(id);
    const nombreCelda = el('th', {scope: 'row', className: 'oc-name'});
    grupo.append(nombreCelda,
      el('td', {className: 'num'}), el('td', {className: 'num'}), el('td', {className: 'num'}), el('td'),
      el('td', {className: 'num'}), el('td', {className: 'num'}), el('td'));
    const [, lineas, meta, real, avance, cajas, kilos, estado] = grupo.children;
    const zonaLineas = el('div', {className: 'oc-lines', data: {lines: ''}});
    const agregar = el('button', {type: 'button', className: 'oc-text-action', data: {addLine: ''}, text: '＋ Agregar objetivo'});
    agregar.disabled = draft;
    const cancelar = draft
      ? el('button', {type: 'button', className: 'oc-text-action oc-mute', data: {cancelDraft: ''}, text: 'Cancelar'})
      : null;
    const detalle = el('tr', {className: 'oc-details', id: detalleId, hidden: !draft},
      el('td', {colspan: 8, 'aria-label': nombre ? `Líneas de ${nombre}` : 'Líneas del objetivo'},
        zonaLineas, el('div', {className: 'oc-group-actions'}, agregar, cancelar)));
    Object.assign(grupo, {
      _nombre: nombre,
      _boton: null,
      _detalle: detalle,
      _lineas: zonaLineas,
      _agregar: agregar,
      _cancelar: cancelar,
      _vendedorSelect: null,
      _celdas: {nombre: nombreCelda, lineas, meta, real, avance, cajas, kilos, estado},
    });
    return grupo;
  }

  // Fila de resumen del vendedor al que pertenece un elemento (de la fila o de su zona de líneas).
  function grupoDeElemento(node) {
    const detalle = node.closest('tr.oc-details');
    return detalle ? detalle.previousElementSibling : node.closest('tr[data-seller-group]');
  }

  // Inserta la fila de resumen y su fila de líneas en la tabla, antes de otro vendedor (o al final).
  function montarGrupo(grupo, antesDe = null) {
    const lista = $('listaVendedores');
    lista.insertBefore(grupo, antesDe);
    lista.insertBefore(grupo._detalle, antesDe);
  }

  function crearBotonExpandir(grupo, nombre) {
    const boton = el('button', {
      type: 'button',
      className: 'oc-toggle',
      'aria-expanded': 'false',
      'aria-controls': grupo._detalle.id,
      title: nombre,
    }, el('span', {className: 'oc-chev', 'aria-hidden': 'true', text: '▶'}), el('span', {text: nombre}));
    boton.addEventListener('click', () => expandir(grupo, boton.getAttribute('aria-expanded') !== 'true'));
    grupo._boton = boton;
    return boton;
  }

  // Los borradores no tienen botón de expandir: su zona de líneas siempre está visible.
  function expandir(grupo, abrir) {
    if (!grupo._boton) return;
    grupo._boton.setAttribute('aria-expanded', String(abrir));
    grupo._detalle.hidden = !abrir;
  }

  function nombrarDetalle(grupo, nombre) {
    grupo._nombre = nombre;
    grupo._detalle.firstElementChild.setAttribute('aria-label', nombre ? `Líneas de ${nombre}` : 'Líneas del objetivo');
  }

  function crearGrupoGuardado(vendedor) {
    const nombre = vendedor.nombre_visible || vendedor.vendedor || '';
    const grupo = crearGrupo({ref: `id:${vendedor.vendedor_id}`, id: vendedor.vendedor_id, nombre});
    grupo._celdas.nombre.append(crearBotonExpandir(grupo, nombre));
    pintarResumen(grupo, vendedor);
    (vendedor.lineas || []).forEach(linea => agregarFormularioLinea(grupo, linea));
    return grupo;
  }

  // Escribe la fila de resumen. vendedor: dato de la API, o null si el vendedor ya está elegido
  // pero todavía no tiene líneas ni datos (Sin meta, realizado sin leer).
  function pintarResumen(grupo, vendedor) {
    const c = grupo._celdas;
    const metas = vendedor?.metas || {};
    const realizados = vendedor?.realizados || {};
    c.lineas.textContent = String(vendedor?.cantidad_lineas ?? 0);
    c.meta.textContent = metas.importe === null || metas.importe === undefined ? '—' : pesos(metas.importe);
    c.real.textContent = vendedor ? pesos(realizados.importe) : '—';
    pintarAvance(c.avance, vendedor ? vendedor.cumplimiento : null);
    c.cajas.textContent = vendedor ? realMeta(realizados.cajas, metas.cajas) : '—';
    c.kilos.textContent = vendedor ? realMeta(realizados.kilos, metas.kilos) : '—';
    pintarEstado(c.estado, vendedor ? vendedor.estado : 'Sin meta');
  }

  function pintarBorradorVacio(grupo) {
    const c = grupo._celdas;
    c.lineas.textContent = '—';
    c.meta.textContent = '—';
    c.real.textContent = '—';
    pintarAvance(c.avance, null);
    c.cajas.textContent = '—';
    c.kilos.textContent = '—';
    pintarEstado(c.estado, null);
  }

  function pintarAvance(celda, cumplimiento) {
    celda.replaceChildren();
    if (cumplimiento === null || cumplimiento === undefined) {
      celda.textContent = '—';
      return;
    }
    const relleno = el('span');
    relleno.style.width = `${Math.min(Math.max(Number(cumplimiento), 0), 1) * 100}%`;
    celda.append(el('div', {className: 'oc-av'},
      el('div', {className: 'oc-track', 'aria-hidden': 'true'}, relleno),
      el('span', {className: 'num', text: porcentaje(cumplimiento)})));
  }

  function pintarEstado(celda, estado) {
    celda.replaceChildren();
    if (!estado) {
      celda.textContent = '—';
      return;
    }
    const tono = TONO_ESTADO[estado] || 'none';
    celda.append(el('span', {className: 'oc-estado'},
      el('i', {className: `oc-dot oc-dot-${tono}`, 'aria-hidden': 'true'}), estado));
  }

  function agregarBorrador() {
    const grupo = crearGrupo({draft: true});
    const select = el('select', {'aria-label': 'Vendedor comercial'}, new Option('Buscar o agregar vendedor…', ''));
    grupo._celdas.nombre.append(select);
    pintarBorradorVacio(grupo);
    montarGrupo(grupo, $('listaVendedores').firstElementChild);
    configurarSelectorVendedor(select, grupo);
    actualizarPresentacion();
    grupo.scrollIntoView({block: 'nearest'});
    return grupo;
  }

  function configurarSelectorVendedor(select, grupo) {
    const opciones = state.vendedores.map(v => ({value: v.referencia, text: v.nombre_visible}));
    const instancia = tomSelect(select, {
      valueField: 'value',
      labelField: 'text',
      searchField: ['text'],
      options: opciones,
      create(input) {
        const nombre = input.trim().replace(/\s+/g, ' ');
        return nombre ? {value: `nombre:${nombre}`, text: nombre} : false;
      },
      createFilter: input => input.trim().length > 1,
      maxOptions: 100,
      placeholder: 'Buscar vendedor…',
      plugins: ['dropdown_input'],
      onChange(value) {
        // Diferido: TomSelect termina su propia selección antes de quitarse.
        if (value) setTimeout(() => fijarVendedorBorrador(grupo, value), 0);
        seleccionarVendedor(grupo, value);
      },
    });
    grupo._vendedorSelect = instancia;
    if (!instancia) {
      select.replaceChildren(new Option('Seleccionar vendedor…', ''));
      opciones.forEach(item => select.add(new Option(item.text, item.value)));
      select.addEventListener('change', () => seleccionarVendedor(grupo, select.value));
    }
  }

  // Tras elegir, el selector se reemplaza por el nombre del vendedor. Así no queda un desplegable abierto
  // tapando la zona de líneas. Para cambiar de vendedor se cancela el borrador y se agrega otro.
  function fijarVendedorBorrador(grupo, ref) {
    grupo._vendedorSelect?.destroy();
    grupo._vendedorSelect = null;
    grupo._celdas.nombre.replaceChildren(el('span', {className: 'oc-draft-name', text: nombreDeRef(ref)}));
  }

  // Elegir un vendedor en el borrador: si ya tiene datos en el resumen, se muestran (realizado incluido).
  function seleccionarVendedor(grupo, ref) {
    grupo.dataset.vendedorRef = ref || '';
    grupo._agregar.disabled = !ref;
    if (!ref) {
      pintarBorradorVacio(grupo);
      nombrarDetalle(grupo, '');
      return;
    }
    const vendedor = vendedorDeRef(ref);
    pintarResumen(grupo, vendedor || null);
    nombrarDetalle(grupo, nombreDeRef(ref));
  }

  function vendedorDeRef(ref) {
    const lista = state.resumen?.objetivos || [];
    if (ref.startsWith('id:')) return lista.find(item => String(item.vendedor_id) === ref.slice(3)) || null;
    if (ref.startsWith('nombre:')) return lista.find(item => item.nombre_visible === ref.slice(7)) || null;
    return null;
  }

  function nombreDeRef(ref) {
    if (ref.startsWith('nombre:')) return ref.slice(7);
    return state.vendedores.find(item => item.referencia === ref)?.nombre_visible || '';
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
          cerrarTrasElegir(this);
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

  // Formulario de una línea dentro de la zona expandida del vendedor (nueva o guardada).
  function agregarFormularioLinea(grupo, linea = null) {
    const form = document.createElement('form');
    form.className = 'oc-line';
    form.dataset.lineId = linea?.id ? String(linea.id) : '';
    const isNew = !linea;
    if (isNew) {
      form.innerHTML = `<div class="oc-line-head"><h3>Nueva línea de objetivo</h3><button type="button" class="oc-text-action oc-mute" data-cancel-line>Quitar línea</button></div><p class="com-note oc-product-hint" data-product-hint hidden></p><div class="oc-line-meta"><label>Nivel del objetivo<select data-dimension-tipo required></select></label><label>Valor del catálogo<select data-dimension-valor required></select></label></div><div class="oc-line-footer"><span class="oc-line-realizado">El realizado se calculará desde PRE al guardar.</span><div class="oc-line-actions"><button type="submit" class="oc-save">Guardar línea</button></div></div><p class="oc-line-error" data-line-error hidden></p>`;
      const typeSelect = form.querySelector('[data-dimension-tipo]');
      typeSelect.replaceWith(crearSelectDimension());
      form.querySelector('.oc-line-meta').append(...Object.keys(MEDIDAS).map(measure => crearInputMeta(measure, '')));
      form.querySelector('[data-cancel-line]').addEventListener('click', () => {
        form.remove();
        if (!grupo._lineas.querySelector('form.oc-line')) quitarGrupo(grupo);
      });
      form._dimensionControls = configurarCatalogoDimension(form);
    } else {
      form.classList.add('oc-line-guardada');
      form.innerHTML = `<div class="oc-line-head"><h3>${escapeHtml(DIMENSIONES[linea.dimension_tipo] || linea.dimension_tipo)} · ${escapeHtml(linea.dimension_valor)}</h3><button type="button" class="oc-text-action oc-mute" data-delete-line>Eliminar línea</button></div><div class="oc-line-meta"></div><div class="oc-line-footer"><span class="oc-line-realizado">Realizado leído desde PRE: ${escapeHtml(MEDIDAS.importe.format(linea.realizado_importe))} · ${escapeHtml(MEDIDAS.cajas.format(linea.realizado_cajas))} · ${escapeHtml(MEDIDAS.kilos.format(linea.realizado_kilos))}</span><div class="oc-line-actions"><button type="submit" class="oc-save">Guardar cambios</button></div></div><p class="oc-line-error" data-line-error hidden></p>`;
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
    grupo._lineas.append(form);
    return form;
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
    const grupo = grupoDeElemento(form);
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
        const ref = grupo.dataset.vendedorRef || '';
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
        convertirBorrador(grupo, objetivo);
        form.replaceWith(agregarFormularioLinea(grupo, objetivo));
      }
      await refrescarResumen(grupo);
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
    const grupo = grupoDeElemento(form);
    marcarCarga(1);
    try {
      await requestJson(`/api/objetivos-comerciales/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: {'X-CSRFToken': csrfToken},
      });
      form.remove();
      if (grupo._lineas.querySelector('form.oc-line')) {
        await refrescarResumen(grupo);
      } else {
        quitarGrupo(grupo);
        await refrescarResumen(null);
      }
    } catch (error) {
      const message = form.querySelector('[data-line-error]');
      message.textContent = error.message || 'No se pudo eliminar la línea.';
      message.hidden = false;
    } finally {
      marcarCarga(-1);
    }
  }

  // Vuelve a leer el período y actualiza solo el vendedor afectado, la fila Equipo y el avance.
  // Los borradores abiertos de otros vendedores no se tocan.
  async function refrescarResumen(grupo = null, vendedorId = null) {
    const requestId = state.requestId;
    try {
      const data = await requestJson(urlObjetivos());
      if (requestId !== state.requestId) return;
      state.resumen = data;
      const id = vendedorId ?? grupo?.dataset.vendedorId;
      const vendedor = id === undefined || id === null
        ? null
        : (data.objetivos || []).find(item => String(item.vendedor_id) === String(id)) || null;
      const destino = grupo?.isConnected ? grupo : buscarGrupoGuardado(id);
      if (destino && vendedor) {
        pintarResumen(destino, vendedor);
      } else if (!destino && vendedor && (vendedor.lineas || []).length) {
        insertarGrupoOrdenado(crearGrupoGuardado(vendedor));
      }
      actualizarPresentacion();
    } catch (error) {
      if (requestId === state.requestId) setError('objetivosError', error.message || 'No se pudo actualizar el resumen del vendedor.');
    }
  }

  function buscarGrupoGuardado(id) {
    if (id === undefined || id === null) return null;
    return [...$('listaVendedores').children].find(item => item.dataset.vendedorId === String(id)) || null;
  }

  // Un vendedor nuevo en la tabla (por ejemplo, objetivo histórico convertido) entra por orden de nombre.
  function insertarGrupoOrdenado(grupo) {
    const siguiente = [...$('listaVendedores').querySelectorAll(':scope > tr[data-seller-group]')]
      .find(otro => !otro.hasAttribute('data-seller-draft') && otro._nombre.localeCompare(grupo._nombre, 'es') > 0);
    montarGrupo(grupo, siguiente || null);
  }

  // Un borrador pasa a vendedor guardado al guardar su primera línea: el selector se cambia por el nombre
  // y la zona de líneas queda expandida.
  function convertirBorrador(grupo, objetivo) {
    if (!grupo.hasAttribute('data-seller-draft')) return;
    grupo._vendedorSelect?.destroy();
    grupo.removeAttribute('data-seller-draft');
    grupo.classList.remove('oc-group-draft');
    grupo.dataset.vendedorId = String(objetivo.vendedor_id);
    grupo.dataset.vendedorRef = `id:${objetivo.vendedor_id}`;
    grupo._cancelar?.remove();
    grupo._celdas.nombre.replaceChildren(crearBotonExpandir(grupo, objetivo.nombre_visible));
    nombrarDetalle(grupo, objetivo.nombre_visible);
    expandir(grupo, true);
  }

  // Quita un vendedor de la tabla (borrador cancelado o sin líneas) y libera su selector.
  function quitarGrupo(grupo) {
    grupo._vendedorSelect?.destroy();
    grupo._detalle?.remove();
    grupo.remove();
    actualizarPresentacion();
  }

  // Estado de la vista: tabla o mensaje vacío, fila Equipo y avance esperado del período.
  function actualizarPresentacion() {
    const hayFilas = $('listaVendedores').querySelector(':scope > tr[data-seller-group]') !== null;
    $('objetivosTablaWrap').hidden = !hayFilas;
    $('objetivosVacio').hidden = hayFilas;
    actualizarEquipo();
    actualizarEsperado();
  }

  // Fila Equipo: cada medida suma solo a los vendedores con meta en esa medida, y el cumplimiento es
  // la suma de realizados sobre la suma de metas (nunca un promedio de porcentajes).
  function totalesEquipo(objetivos) {
    const total = {lineas: 0, conMeta: 0};
    for (const medida of MEDIDAS_EQUIPO) total[medida] = {meta: 0, real: 0, hay: false};
    for (const vendedor of objetivos) {
      const lineas = Number(vendedor.cantidad_lineas || 0);
      total.lineas += lineas;
      if (lineas > 0) total.conMeta += 1;
      for (const medida of MEDIDAS_EQUIPO) {
        const meta = vendedor.metas?.[medida];
        if (meta === null || meta === undefined) continue;
        total[medida].meta += Number(meta);
        total[medida].real += Number(vendedor.realizados?.[medida] || 0);
        total[medida].hay = true;
      }
    }
    return total;
  }

  function actualizarEquipo() {
    const total = totalesEquipo(state.resumen?.objetivos || []);
    const importe = total.importe;
    $('equipoEtiqueta').textContent = `Equipo · ${total.conMeta} con meta`;
    $('equipoLineas').textContent = String(total.lineas);
    $('equipoMeta').textContent = importe.hay ? pesos(importe.meta) : '—';
    $('equipoReal').textContent = importe.hay ? pesos(importe.real) : '—';
    pintarAvance($('equipoAvance'), importe.hay && importe.meta > 0 ? importe.real / importe.meta : null);
    $('equipoCajas').textContent = total.cajas.hay ? realMeta(total.cajas.real, total.cajas.meta) : '—';
    $('equipoKilos').textContent = total.kilos.hay ? realMeta(total.kilos.real, total.kilos.meta) : '—';
  }

  // Avance esperado del período: referencia lineal según la fecha de corte que informa la API.
  function actualizarEsperado() {
    const data = state.resumen;
    const referencia = (data?.objetivos || []).find(item => item.avance_esperado !== null && item.avance_esperado !== undefined);
    const bloque = $('objetivosEsperado');
    if (!data?.fecha_corte || !referencia) {
      bloque.hidden = true;
      return;
    }
    const [, mes, dia] = data.fecha_corte.split('-');
    $('objetivosEsperadoFecha').textContent = `${dia}/${mes}`;
    $('objetivosEsperadoPct').textContent = porcentaje(referencia.avance_esperado);
    bloque.hidden = false;
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
        onChange() { cerrarTrasElegir(this); },
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
      // Solo cambia el vendedor convertido: los borradores abiertos de la tabla se conservan.
      await Promise.all([refrescarResumen(null, payload.vendedor_id), cargarLegacy()]);
    } catch (error) {
      setError('legacyError', error.message || 'No se pudo convertir el objetivo histórico.');
    } finally {
      button.disabled = false;
    }
  }

  $('listaVendedores').addEventListener('click', event => {
    const grupo = grupoDeElemento(event.target);
    if (!grupo) return;
    if (event.target.closest('[data-add-line]')) {
      if (!grupo.dataset.vendedorRef) return;
      expandir(grupo, true);
      agregarFormularioLinea(grupo);
      return;
    }
    if (event.target.closest('[data-cancel-draft]')) quitarGrupo(grupo);
  });
  $('legacyGoals').addEventListener('submit', convertirLegacy);
  $('agregarVendedor').addEventListener('click', agregarBorrador);
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
