(() => {
  const form = document.getElementById('salon-filtros');
  if (!form) return;

  const status = document.getElementById('salon-status');
  const error = document.getElementById('salon-error');
  const periodo = document.getElementById('salon-periodo');
  const metrics = document.getElementById('salon-kpis');
  const table = document.getElementById('salon-tabla');
  const ticketsTotal = document.getElementById('salon-tickets-total');
  const dateFormatter = new Intl.DateTimeFormat('es-AR', {
    day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC',
  });
  const numberFormatter = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 });
  const countFormatter = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 });
  let requestId = 0;

  function formatDate(value) {
    const [year, month, day] = value.split('-').map(Number);
    return dateFormatter.format(new Date(Date.UTC(year, month - 1, day)));
  }

  function formatNumber(value, count = false) {
    return (count ? countFormatter : numberFormatter).format(value || 0);
  }

  function appendCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.textContent = value;
    if (className) cell.className = className;
    row.append(cell);
  }

  function renderMetrics(kpis) {
    const definitions = [
      ['Tickets', 'tickets', true],
      ['Importe', 'importe', false],
      ['Cajas', 'cajas', false],
      ['Kilos', 'kilos', false],
    ];
    metrics.replaceChildren();
    definitions.forEach(([label, key, isCount]) => {
      const value = kpis[key];
      const card = document.createElement('article');
      card.className = 'com-metric';
      const title = document.createElement('span');
      title.textContent = label;
      const actual = document.createElement('strong');
      actual.textContent = formatNumber(value.actual, isCount);
      const comparison = document.createElement('small');
      comparison.textContent = `Anterior: ${formatNumber(value.anterior, isCount)} · ${value.variacion_texto}`;
      card.append(title, actual, comparison);
      metrics.append(card);
    });
  }

  function renderTickets(tickets) {
    table.replaceChildren();
    if (!tickets.length) {
      const empty = document.createElement('p');
      empty.className = 'com-empty salon-empty';
      empty.textContent = 'No hay tickets facturados de Salón para las fechas elegidas.';
      table.append(empty);
      return;
    }

    const ticketTable = document.createElement('table');
    ticketTable.className = 'salon-table';
    const headers = ['Fecha', 'Origen', 'Sucursal', 'Tipo', 'Número', 'Cliente', 'Vendedor', 'Importe', 'Cajas', 'Kilos'];
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headers.forEach((label) => {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = label;
      headerRow.append(th);
    });
    thead.append(headerRow);
    ticketTable.append(thead);

    const tbody = document.createElement('tbody');
    tickets.forEach((ticket) => {
      const row = document.createElement('tr');
      appendCell(row, formatDate(ticket.fecha));
      appendCell(row, ticket.origen);
      appendCell(row, ticket.sucursal);
      appendCell(row, ticket.tipo);
      appendCell(row, ticket.numero);
      appendCell(row, ticket.cliente, 'salon-client-cell');
      appendCell(row, ticket.vendedor);
      appendCell(row, formatNumber(ticket.importe), 'salon-number-cell');
      appendCell(row, formatNumber(ticket.cajas), 'salon-number-cell');
      appendCell(row, formatNumber(ticket.kilos), 'salon-number-cell');
      tbody.append(row);
    });
    ticketTable.append(tbody);
    table.append(ticketTable);
  }

  async function loadData() {
    const thisRequest = ++requestId;
    const values = new FormData(form);
    const query = new URLSearchParams(values);
    status.textContent = 'Cargando tickets facturados…';
    error.hidden = true;
    form.querySelector('button[type="submit"]').disabled = true;

    try {
      const response = await fetch(`/api/comercial/salon?${query.toString()}`, {
        headers: { Accept: 'application/json' },
      });
      const data = await response.json();
      if (thisRequest !== requestId) return;
      if (!response.ok) throw new Error(data.error || 'No se pudieron cargar los tickets.');

      periodo.textContent = `Actual: ${formatDate(data.desde)}–${formatDate(data.hasta)} · Anterior: ${formatDate(data.desde_anterior)}–${formatDate(data.hasta_anterior)}`;
      renderMetrics(data.kpis);
      renderTickets(data.tickets);
      ticketsTotal.textContent = `${formatNumber(data.tickets.length, true)} tickets · Vendedor: ${data.vendedor}`;
      status.textContent = 'Período actualizado.';
    } catch (err) {
      if (thisRequest !== requestId) return;
      error.textContent = err.message || 'No se pudieron cargar los tickets. Volvé a intentar.';
      error.hidden = false;
      status.textContent = '';
    } finally {
      if (thisRequest === requestId) form.querySelector('button[type="submit"]').disabled = false;
    }
  }

  // Las fechas aplicadas viajan en la URL (?desde=&hasta=) y se cargan al abrir la página.
  function leerFechasDeUrl() {
    const params = new URLSearchParams(location.search);
    if (params.get('desde')) form.elements.fecha_desde.value = params.get('desde');
    if (params.get('hasta')) form.elements.fecha_hasta.value = params.get('hasta');
  }
  function reflejarFechasEnUrl() {
    const desde = form.elements.fecha_desde.value, hasta = form.elements.fecha_hasta.value;
    if (!desde || !hasta) return;
    const url = new URL(location.href);
    url.searchParams.set('desde', desde);
    url.searchParams.set('hasta', hasta);
    history.replaceState(null, '', url);
  }
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (form.reportValidity()) {
      reflejarFechasEnUrl();
      loadData();
    }
  });
  leerFechasDeUrl();
  reflejarFechasEnUrl();
  loadData();
})();
