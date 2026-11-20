/* Formularios de Tesorería (SIS-1C): «Registrar nuevo movimiento» y «Nuevo arqueo de caja».
 *
 * Compartido por Tesorería (panel), Movimientos y Arqueos. Los dos modales salen de un único parcial
 * cada uno (templates/tesoreria/_modal_movimiento.html y _modal_arqueo.html). Este módulo solo expone
 * la lógica común; cada página la monta con sus propios ids:
 *   - Movimiento: POST /api/tesoreria/movimientos con {tipo, monto, instrumento_id, categoria_gasto_id, descripcion}.
 *   - Arqueo: POST /api/tesoreria/arqueos con {fecha, turno, saldo_inicial, saldo_final, observaciones, detalles}.
 *     El servidor toma ingresos y egresos de los movimientos del turno, recalcula la diferencia y usa detalles.
 *
 * Importes: App360Format (es-AR, «$ 1.500»). Estado: punto + texto (App360 §3.15).
 */
(function (root) {
  'use strict';

  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content;

  function mostrarErrorFormulario(form, mensaje) {
    const aviso = form?.querySelector('[data-form-error]');
    if (!aviso) { root.alert(mensaje); return; }
    aviso.textContent = mensaje;
    aviso.classList.remove('d-none');
  }

  function ocultarErrorFormulario(form) {
    form?.querySelector('[data-form-error]')?.classList.add('d-none');
  }

  // Importes con un único formateador. Decimales solo cuando el valor los tiene.
  function importe(valor, decimales) {
    if (root.App360Format) return root.App360Format.formatARS(valor, {decimales: decimales ?? 0});
    const n = Number(valor);
    if (!Number.isFinite(n)) return '—';
    const d = decimales ?? 0;
    return '$ ' + n.toLocaleString('es-AR', {minimumFractionDigits: d, maximumFractionDigits: d});
  }

  function tieneCentavos(valor) {
    const n = Number(valor);
    return Number.isFinite(n) && Math.abs(n - Math.round(n)) > 0.004;
  }

  function decimalesPara(valores) {
    return valores.some((v) => tieneCentavos(v)) ? 2 : 0;
  }

  // Estado como punto + texto (App360 §3.15): mismo marcado que app-status del sistema.
  function punto(variante, texto) {
    return `<span class="app-status app-status--${variante}"><span class="app-status__dot" aria-hidden="true"></span>`
      + `${escapeHtml(texto)}</span>`;
  }

  // Tipo de movimiento: chip propio (app-tipo), no un estado. El texto se escapa; las clases salen de un enum fijo.
  function tipoHtml(tipo) {
    if (tipo === 'ingreso') return '<span class="app-tipo app-tipo--ingreso">Ingreso</span>';
    if (tipo === 'egreso') return '<span class="app-tipo app-tipo--egreso">Egreso</span>';
    return `<span class="app-tipo">${escapeHtml(String(tipo ?? '—'))}</span>`;
  }

  // Monto con el signo del tipo: «+ $ 1.500,00» (ingreso) y «− $ 120,00» (egreso). El signo solo presenta el tipo;
  // el valor y el formato son los de importe(). Sin ingreso ni egreso no lleva signo ni color.
  function montoHtml(tipo, monto, decimales) {
    const signo = tipo === 'ingreso' ? '+ ' : tipo === 'egreso' ? '\u2212 ' : '';
    const modificador = tipo === 'ingreso' || tipo === 'egreso' ? ` app-tipo__monto--${tipo}` : '';
    return `<span class="app-tipo__monto${modificador}">${escapeHtml(signo + importe(monto, decimales))}</span>`;
  }

  // Clase de fila activa: borde izquierdo del color del tipo. Las filas anuladas las arma cada pantalla.
  function claseFila(tipo) {
    return tipo === 'ingreso' || tipo === 'egreso' ? `app-tipo-fila app-tipo-fila--${tipo}` : '';
  }

  function diferenciaHtml(diferencia) {
    const n = Number(diferencia);
    if (!Number.isFinite(n) || Math.abs(n) < 0.005) return punto('ok', 'Sin diferencia');
    return n < 0 ? punto('error', 'Faltante') : punto('warn', 'Sobrante');
  }

  // Estado de movimiento como punto + texto: Activo, Anulado o Pend. anulación.
  function estadoHtml(estado) {
    if (estado === 'anulado') return punto('neutral', 'Anulado');
    if (estado === 'pendiente_anulacion') return punto('warn', 'Pend. anulación');
    return punto('ok', 'Activo');
  }

  // Importe alineado a la derecha (cifras tabulares) y, al lado, el estado de la diferencia.
  // Un valor vacío cuenta como 0, igual que en la pantalla original.
  function celdaDiferenciaHtml(diferencia, decimales) {
    const valor = diferencia === null || diferencia === undefined || diferencia === '' ? 0 : diferencia;
    return '<span class="d-inline-flex align-items-center justify-content-end gap-2">'
      + `<span class="app-table__numeric">${escapeHtml(importe(valor, decimales))}</span>`
      + `${diferenciaHtml(valor)}</span>`;
  }

  function etiquetaEfecto(efecto) {
    if (efecto === 'suma') return 'Suma';
    if (efecto === 'resta') return 'Resta';
    if (efecto === 'segun_movimiento') return 'Según movimiento';
    return 'No participa';
  }

  function etiquetaNaturaleza(naturaleza) {
    return naturaleza === 'ambos' ? 'Ambos' : naturaleza.charAt(0).toUpperCase() + naturaleza.slice(1);
  }

  // ------------------------------------------------------------ Movimiento

  let conceptosRapidos = [];

  // Ids del modal de movimiento: Movimientos usa los del parcial; el panel pasa los suyos.
  const IDS_MOVIMIENTO = {concepto: 'selectCategoriaGasto', tipo: 'selectTipoMovimiento', hint: 'tipoMovimientoHint', instrumento: 'selectInstrumento'};
  const idsMovimiento = (ids) => Object.assign({}, IDS_MOVIMIENTO, ids || {});

  function cargarConceptos(conceptos, ids) {
    conceptosRapidos = conceptos.filter((c) => c.naturaleza);
    const select = document.getElementById(idsMovimiento(ids).concepto);
    if (!select) return;
    select.innerHTML = '<option value="">Seleccionar…</option>' + conceptosRapidos.map((c) =>
      `<option value="${escapeHtml(c.id)}">${escapeHtml(c.nombre)} · `
      + `${escapeHtml(etiquetaNaturaleza(c.naturaleza))} · ${escapeHtml(etiquetaEfecto(c.efecto))}</option>`).join('');
  }

  function sincronizarTipoRapido(ids) {
    const campos = idsMovimiento(ids);
    const conceptoId = Number(document.getElementById(campos.concepto).value || 0);
    const concepto = conceptosRapidos.find((c) => Number(c.id) === conceptoId);
    const tipo = document.getElementById(campos.tipo);
    const hint = document.getElementById(campos.hint);
    if (!concepto) {
      tipo.disabled = true;
      hint.textContent = 'Seleccioná primero un concepto.';
    } else if (concepto.naturaleza === 'ambos') {
      tipo.disabled = false;
      tipo.value = 'ingreso';
      hint.textContent = 'Este concepto admite ambos tipos.';
    } else {
      tipo.value = concepto.naturaleza;
      tipo.disabled = true;
      hint.textContent = `Tipo fijado por el concepto: ${concepto.naturaleza}.`;
    }
  }

  function cargarInstrumentos(instrumentos, ids) {
    const select = document.getElementById(idsMovimiento(ids).instrumento);
    if (!select) return;
    select.innerHTML = instrumentos.length
      ? instrumentos.map((i) => `<option value="${escapeHtml(i.id)}">${escapeHtml(i.nombre)}</option>`).join('')
      : '<option value="">Sin instrumentos</option>';
  }

  function enviarMovimiento(formulario, alGuardar) {
    ocultarErrorFormulario(formulario);
    const formData = new FormData(formulario);
    const data = {
      tipo: formData.get('tipo'),
      monto: parseFloat(formData.get('monto')),
      instrumento_id: parseInt(formData.get('instrumento_id')),
      categoria_gasto_id: parseInt(formData.get('categoria_gasto_id')),
      descripcion: formData.get('descripcion'),
    };
    fetch('/api/tesoreria/movimientos', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
      body: JSON.stringify(data),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.message) {
          alGuardar?.();
        } else {
          mostrarErrorFormulario(formulario, d.error || 'No se pudo guardar el movimiento. Revisá los datos e intentá de nuevo.');
        }
      })
      .catch((e) => {
        console.error('Error:', e);
        mostrarErrorFormulario(formulario, 'No hay conexión con el servidor. Revisá la conexión e intentá de nuevo.');
      });
  }

  // ---------------------------------------------------------------- Arqueo

  // Envía el arqueo con el conteo por instrumento (detalles). El servidor toma ingresos y egresos del turno.
  function enviarArqueo(formulario, detalles, alGuardar) {
    ocultarErrorFormulario(formulario);
    const formData = new FormData(formulario);
    const data = {
      fecha: formData.get('fecha'),
      turno: formData.get('turno'),
      saldo_inicial: parseFloat(formData.get('saldo_inicial')) || 0,
      saldo_final: parseFloat(formData.get('saldo_real')) || 0,
      observaciones: formData.get('observaciones'),
      detalles: detalles,
    };
    fetch('/api/tesoreria/arqueos', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
      body: JSON.stringify(data),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.message) {
          alGuardar?.();
        } else {
          mostrarErrorFormulario(formulario, d.error || 'No se pudo guardar el arqueo. Revisá los datos e intentá de nuevo.');
        }
      })
      .catch((e) => {
        console.error('Error:', e);
        mostrarErrorFormulario(formulario, 'No hay conexión con el servidor. Revisá la conexión e intentá de nuevo.');
      });
  }

  // ---- Totales del turno y diferencia (misma lógica que Arqueos): diferencia = real − (inicial + ingresos − egresos).
  let totalesTurno = null;

  function valorDinero(ref) {
    const campo = typeof ref === 'string' ? document.getElementById(ref) : ref;
    const money = root.App360UI?.money;
    const monto = money?.getValue(campo);
    if (Number.isFinite(monto)) return monto;
    return Number.parseFloat(campo?.value || '') || 0;
  }

  function calcularDiferencia(formulario) {
    const inicial = valorDinero(formulario.querySelector('[data-money-calc="saldo_inicial"]'));
    const real = valorDinero(formulario.querySelector('[data-money-calc="saldo_real"]'));
    const campoDif = document.getElementById('diferenciaCalc');
    const estado = document.getElementById('diferenciaEstado');
    if (!totalesTurno) {
      if (campoDif) campoDif.value = '';
      if (estado) estado.innerHTML = '';
      return;
    }
    const diferencia = real - (inicial + totalesTurno.ingresos - totalesTurno.egresos);
    if (campoDif) campoDif.value = importe(diferencia, 2);
    if (estado) estado.innerHTML = diferenciaHtml(diferencia);
  }

  async function cargarTotalesTurno(formulario) {
    const fecha = formulario.querySelector('input[name="fecha"]').value;
    const turno = formulario.querySelector('select[name="turno"]').value;
    const aviso = document.getElementById('avisoTotalesTurno');
    totalesTurno = null;
    document.getElementById('ingresosTurnoSistema').value = '';
    document.getElementById('egresosTurnoSistema').value = '';
    if (aviso) aviso.hidden = true;
    if (!fecha || !turno) { calcularDiferencia(formulario); return; }
    try {
      const params = new URLSearchParams({fecha, turno});
      const resp = await fetch(`/api/tesoreria/arqueos/totales?${params}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'No se pudieron cargar los movimientos del turno.');
      // Si cambió fecha o turno mientras llegaba la respuesta, se descarta.
      if (formulario.querySelector('input[name="fecha"]').value !== fecha
          || formulario.querySelector('select[name="turno"]').value !== turno) return;
      totalesTurno = {ingresos: Number(data.ingresos_total) || 0, egresos: Number(data.egresos_total) || 0};
      const decimales = decimalesPara([totalesTurno.ingresos, totalesTurno.egresos]);
      document.getElementById('ingresosTurnoSistema').value = importe(totalesTurno.ingresos, decimales);
      document.getElementById('egresosTurnoSistema').value = importe(totalesTurno.egresos, decimales);
    } catch (e) {
      if (aviso) { aviso.textContent = e.message || 'No se pudieron cargar los movimientos del turno.'; aviso.hidden = false; }
    }
    calcularDiferencia(formulario);
  }

  // Conteo por instrumento: una fila por instrumento con su campo de conteo real.
  function renderInstrumentosArqueo(instrumentos) {
    const cuerpo = document.getElementById('detalleInstrumentos');
    if (!cuerpo) return;
    if (!instrumentos.length) {
      cuerpo.innerHTML = '<tr><td class="app-table__cell" colspan="2">No hay instrumentos configurados</td></tr>';
      return;
    }
    cuerpo.innerHTML = instrumentos.map((inst) => `
      <tr>
        <th class="app-table__cell" scope="row">${escapeHtml(inst.nombre)}</th>
        <td class="app-table__cell app-table__numeric">
          <input class="app-field__control tes-numero" type="number" step="0.01" data-money-input
                 data-inst-id="${escapeHtml(inst.id)}" placeholder="Conteo real"
                 aria-label="Conteo real de ${escapeHtml(inst.nombre)}">
        </td>
      </tr>`).join('');
    root.App360UI?.money?.initInputs(cuerpo);
  }

  function detallesArqueo() {
    const detalles = [];
    document.querySelectorAll('#detalleInstrumentos input[data-inst-id]').forEach((entrada) => {
      detalles.push({instrumento_id: parseInt(entrada.dataset.instId, 10), conteo_real: valorDinero(entrada)});
    });
    return detalles;
  }

  // Monta el arqueo completo sobre el formulario de la página (mismos ids que el parcial).
  function montarArqueo(formulario, alGuardar) {
    const hoy = new Date().toISOString().split('T')[0];
    const fecha = formulario.querySelector('input[name="fecha"]');
    if (fecha) fecha.value = hoy;
    formulario.querySelectorAll('[data-money-calc]').forEach((entrada) => {
      entrada.addEventListener('input', () => calcularDiferencia(formulario));
    });
    fecha?.addEventListener('change', () => cargarTotalesTurno(formulario));
    formulario.querySelector('select[name="turno"]')?.addEventListener('change', () => cargarTotalesTurno(formulario));
    document.getElementById('modalNuevoArqueo')?.addEventListener('show.bs.modal', () => cargarTotalesTurno(formulario));
    formulario.addEventListener('submit', (evento) => {
      evento.preventDefault();
      if (!totalesTurno) {
        root.alert('No se pudieron cargar los movimientos del turno. Revisá fecha y turno antes de guardar.');
        return;
      }
      enviarArqueo(formulario, detallesArqueo(), () => alGuardar(formulario));
    });
  }

  // Arqueo del panel (Tesorería): mismos campos y payload que el formulario original del panel, sin conteo por
  // instrumento ni totales del turno. Ingresos y egresos son editables, como en el panel original.
  function montarArqueoPanel(formulario, alGuardar) {
    formulario.addEventListener('submit', (evento) => {
      evento.preventDefault();
      ocultarErrorFormulario(formulario);
      const formData = new FormData(formulario);
      const inicial = parseFloat(formData.get('saldo_inicial')) || 0;
      const ingresos = parseFloat(formData.get('ingresos')) || 0;
      const egresos = parseFloat(formData.get('egresos')) || 0;
      const real = parseFloat(formData.get('saldo_real')) || 0;
      const data = {
        fecha: formData.get('fecha'),
        turno: formData.get('turno'),
        saldo_inicial: inicial,
        ingresos: ingresos,
        egresos: egresos,
        saldo_final: real,
        diferencia: real - (inicial + ingresos - egresos),
        observaciones: formData.get('observaciones'),
      };
      fetch('/api/tesoreria/arqueos', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
        body: JSON.stringify(data),
      })
        .then((r) => r.json())
        .then((d) => {
          if (d.message) {
            alGuardar?.(formulario);
          } else {
            mostrarErrorFormulario(formulario, d.error || 'No se pudo guardar el arqueo. Revisá los datos e intentá de nuevo.');
          }
        })
        .catch((e) => {
          console.error('Error:', e);
          mostrarErrorFormulario(formulario, 'No hay conexión con el servidor. Revisá la conexión e intentá de nuevo.');
        });
    });
  }

  root.TesoreriaForms = Object.freeze({
    importe,
    decimalesPara,
    tipoHtml,
    montoHtml,
    claseFila,
    diferenciaHtml,
    estadoHtml,
    celdaDiferenciaHtml,
    cargarConceptos,
    sincronizarTipoRapido,
    cargarInstrumentos,
    enviarMovimiento,
    montarArqueo,
    montarArqueoPanel,
    renderInstrumentosArqueo,
  });
})(window);
