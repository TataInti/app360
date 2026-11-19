/* Formato numérico común de App360. No necesita dependencias del navegador. */
(function (root) {
  'use strict';

  const LOCALE = 'es-AR';
  const VACIO = '—';
  const ESPACIO_PORCENTAJE = '\u00a0%';

  function valorNumerico(valor) {
    if (valor === null || valor === undefined) return null;
    if (typeof valor === 'string' && valor.trim() === '') return null;
    if (typeof valor !== 'number' && typeof valor !== 'string') return null;
    const numero = Number(valor);
    return Number.isFinite(numero) ? numero : null;
  }

  function cantidadDecimales(opciones) {
    const valor = opciones?.decimales ?? 0;
    const numero = Number(valor);
    return Number.isInteger(numero) && numero >= 0 && numero <= 20 ? numero : 0;
  }

  function formatNumber(valor, opciones = {}) {
    const numero = valorNumerico(valor);
    if (numero === null) return VACIO;

    const decimales = cantidadDecimales(opciones);
    return new Intl.NumberFormat(LOCALE, {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
    }).format(numero);
  }

  function formatARS(valor, opciones = {}) {
    const numero = valorNumerico(valor);
    if (numero === null) return VACIO;

    const texto = formatNumber(numero, opciones);
    // Se conserva el signo negativo ASCII que genera Intl.NumberFormat para es-AR.
    return opciones?.signo === false ? texto : `$ ${texto}`;
  }

  function formatPercent(valor, opciones = {}) {
    const numero = valorNumerico(valor);
    if (numero === null) return VACIO;
    return `${formatNumber(numero * 100, opciones)}${ESPACIO_PORCENTAJE}`;
  }

  function parseNumberAR(texto) {
    if (texto === null || texto === undefined) return null;

    let fuente = String(texto).trim();
    if (!fuente) return null;
    fuente = fuente.replace(/^\$\s*/, '').replace(/[\s\u00a0\u202f]/g, '');

    let signo = '';
    if (/^[+\-\u2212]/.test(fuente)) {
      signo = fuente[0] === '+' ? '' : '-';
      fuente = fuente.slice(1);
    }
    if (!fuente || !/^\d[\d.,]*$/.test(fuente)) return null;

    let normalizado;
    if (fuente.includes(',')) {
      const partes = fuente.split(',');
      if (partes.length !== 2 || !/^\d+$/.test(partes[1])) return null;
      const entero = partes[0];
      const enteroValido = /^\d+$/.test(entero) || /^\d{1,3}(?:\.\d{3})+$/.test(entero);
      if (!enteroValido) return null;
      normalizado = `${entero.replace(/\./g, '')}.${partes[1]}`;
    } else if (fuente.includes('.')) {
      if (/^\d{1,3}(?:\.\d{3})+$/.test(fuente)) {
        normalizado = fuente.replace(/\./g, '');
      } else if (/^\d+\.\d+$/.test(fuente)) {
        normalizado = fuente;
      } else {
        return null;
      }
    } else {
      normalizado = fuente;
    }

    const numero = Number(`${signo}${normalizado}`);
    return Number.isFinite(numero) ? numero : null;
  }

  root.App360Format = Object.freeze({formatARS, formatNumber, formatPercent, parseNumberAR});
})(window);
