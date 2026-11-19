/* Estados comunes de App360: tono explícito y texto insertado solo como texto. */
(function (root) {
  'use strict';

  const VARIANTE_POR_ESTADO = Object.freeze({
    'Cumplido': 'ok',
    'En ritmo': 'ok',
    'Por debajo del ritmo esperado': 'warn',
    'No cumplido': 'warn',
    'No iniciado': 'neutral',
    'Sin meta': 'neutral',
    'Activo': 'ok',
    'Activo a 30 días': 'ok',
    'Inactivo': 'neutral',
    'Pendiente': 'warn',
    'Pendiente aprobación': 'warn',
    'Pend. anulación': 'warn',
    'Pendiente de anulación': 'warn',
    'Anulado': 'neutral',
    'Aprobado': 'ok',
    'Pagado': 'ok',
    'Liquidado': 'neutral',
    'Período ya liquidado': 'neutral',
    'Falta': 'error',
    'Tarde': 'warn',
    'Fichada falt.': 'warn',
    'Fichada faltante': 'warn',
    'Justificado': 'neutral',
    'OK': 'ok',
    'Ingreso': 'ok',
    'Egreso': 'neutral',
    'No participa': 'neutral',
    'Rechazado': 'error',
    'Rechazada': 'error',
  });

  function statusDot(estado, opciones = {}) {
    const clave = estado === null || estado === undefined ? '' : String(estado);
    const variante = Object.prototype.hasOwnProperty.call(VARIANTE_POR_ESTADO, clave)
      ? VARIANTE_POR_ESTADO[clave]
      : 'neutral';
    const etiqueta = opciones?.texto === undefined || opciones.texto === null
      ? (clave || '—')
      : String(opciones.texto);

    const contenedor = document.createElement('span');
    contenedor.className = `app-status app-status--${variante}`;

    const punto = document.createElement('span');
    punto.className = 'app-status__dot';
    punto.setAttribute('aria-hidden', 'true');

    const texto = document.createElement('span');
    texto.className = 'app-status__text';
    texto.textContent = etiqueta;

    contenedor.append(punto, texto);
    return contenedor;
  }

  root.App360Status = Object.freeze({statusDot});
})(window);
