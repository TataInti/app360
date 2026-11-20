/*
 * App360DrawerForm: panel lateral de alta repetitiva (SIS-2B, decisión D3).
 *
 * Uso: App360DrawerForm.crear({ panel, primerCampo, textoGuardado, conservar, alGuardar, mensajeDescarte })
 *   panel: el <form> del panel (id único, con hidden, role="dialog", action = endpoint JSON).
 *   Marcado requerido dentro del panel: [data-drawer-status] (aviso aria-live), [data-drawer-cancel],
 *   botones de envío con data-accion="guardar" | "agregar", y un [data-error-campo="<campo>"] por campo con aviso.
 *   Los botones [data-drawer-open="<id del panel>"] abren el panel (delegación; sirven también si se crean luego).
 * El envío va por fetch con JSON, Accept: application/json y X-CSRFToken. Los textos se asignan con
 * textContent: no se interpola HTML de datos.
 * Contrato: skills/DESIGN_SYSTEM.md §3.13.1.
 */
(function (global) {
    'use strict';

    var SELECTOR_FOCO = 'input:not([type="hidden"]), select, textarea, button';

    function tokenCsrf() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function instantaneaDel(formulario) {
        var pares = [];
        Array.prototype.forEach.call(formulario.elements, function (el) {
            if (!el.name || el.name === 'csrf_token' || el.type === 'submit' || el.type === 'button') {
                return;
            }
            pares.push(encodeURIComponent(el.name) + '=' + encodeURIComponent(el.value));
        });
        return pares.join('&');
    }

    function esVisible(el) {
        return !el.disabled && el.getClientRects().length > 0;
    }

    function crear(config) {
        var panel = config.panel;
        var estado = panel.querySelector('[data-drawer-status]');
        var primerCampo = panel.querySelector(config.primerCampo || 'input, select, textarea');
        var conservar = config.conservar || [];
        var textoGuardado = config.textoGuardado || function () { return 'Registro guardado'; };
        var ultimoDisparador = null;
        var enviando = false;
        var instantanea = '';

        function sucio() {
            return instantaneaDel(panel) !== instantanea;
        }

        function marcarLimpio() {
            instantanea = instantaneaDel(panel);
        }

        function avisar(texto) {
            if (estado) {
                estado.textContent = texto || '';
            }
        }

        function limpiarErrores() {
            panel.querySelectorAll('[data-error-campo]').forEach(function (aviso) {
                aviso.textContent = '';
                aviso.hidden = true;
            });
            panel.querySelectorAll('[aria-invalid]').forEach(function (control) {
                control.removeAttribute('aria-invalid');
                control.removeAttribute('aria-describedby');
            });
        }

        function mostrarErrores(errores) {
            var primero = null;
            var sinCampo = [];
            limpiarErrores();
            Object.keys(errores).forEach(function (campo) {
                var control = panel.elements.namedItem(campo);
                var aviso = Array.prototype.find.call(panel.querySelectorAll('[data-error-campo]'), function (el) {
                    return el.dataset.errorCampo === campo;
                });
                if (aviso) {
                    aviso.textContent = errores[campo];
                    aviso.hidden = false;
                }
                if (control && control.setAttribute) {
                    control.setAttribute('aria-invalid', 'true');
                    if (aviso && aviso.id) {
                        control.setAttribute('aria-describedby', aviso.id);
                    }
                    if (!primero) {
                        primero = control;
                    }
                } else {
                    sinCampo.push(errores[campo]);
                }
            });
            avisar(sinCampo.length ? sinCampo.join(' ') : 'Revisá los campos marcados.');
            if (primero && primero.focus) {
                primero.focus();
            }
        }

        function confirmarDescarte() {
            var mensaje = config.mensajeDescarte || 'Hay datos sin guardar. Si cerrás el panel, se pierden.';
            if (global.App360UI && typeof global.App360UI.confirm === 'function') {
                return Promise.resolve(global.App360UI.confirm({
                    title: 'Descartar los datos cargados',
                    message: mensaje,
                    confirmText: 'Descartar',
                    cancelText: 'Seguir editando'
                }));
            }
            return Promise.resolve(global.confirm(mensaje));
        }

        function cerrarSinPreguntar() {
            panel.hidden = true;
            panel.reset();
            limpiarErrores();
            avisar('');
            if (ultimoDisparador && document.contains(ultimoDisparador)) {
                ultimoDisparador.focus();
            }
        }

        function abrir(disparador) {
            if (!panel.hidden) {
                return;
            }
            ultimoDisparador = disparador || null;
            panel.hidden = false;
            marcarLimpio();
            avisar('');
            if (primerCampo) {
                primerCampo.focus();
            }
        }

        function cerrar(opciones) {
            if (enviando) {
                return Promise.resolve(false);
            }
            if (!(opciones && opciones.forzar) && sucio()) {
                return confirmarDescarte().then(function (confirmado) {
                    if (confirmado) {
                        cerrarSinPreguntar();
                    }
                    return confirmado;
                });
            }
            cerrarSinPreguntar();
            return Promise.resolve(true);
        }

        function exito(cuerpo, accion) {
            var texto = textoGuardado(cuerpo);
            if (config.alGuardar) {
                config.alGuardar(cuerpo, accion);
            }
            if (accion === 'agregar') {
                var guardados = {};
                conservar.forEach(function (nombre) {
                    var control = panel.elements.namedItem(nombre);
                    if (control) {
                        guardados[nombre] = control.value;
                    }
                });
                panel.reset();
                conservar.forEach(function (nombre) {
                    var control = panel.elements.namedItem(nombre);
                    if (control) {
                        control.value = guardados[nombre];
                    }
                });
                limpiarErrores();
                marcarLimpio();
                avisar(texto);
                if (primerCampo) {
                    primerCampo.focus();
                }
                return;
            }
            cerrarSinPreguntar();
            if (global.App360UI && typeof global.App360UI.notify === 'function') {
                global.App360UI.notify(texto, 'success');
            }
        }

        function mensajeDeFallo(respuesta) {
            var sesionVencida = respuesta.redirected && /login/.test(respuesta.url);
            if (sesionVencida) {
                return 'Tu sesión venció. Volvé a iniciar sesión para guardar.';
            }
            return 'No tenés permiso para guardar o la pantalla cambió. Recargá la página e intentá de nuevo.';
        }

        function enviar(boton) {
            if (enviando) {
                return;
            }
            var accion = (boton && boton.dataset.accion) || 'guardar';
            var botones = Array.prototype.slice.call(panel.querySelectorAll('button'));
            var deshabilitadosAntes = botones.map(function (b) { return b.disabled; });
            var textoOriginal = boton ? boton.textContent : '';
            var datos = {};
            limpiarErrores();
            enviando = true;
            panel.setAttribute('aria-busy', 'true');
            botones.forEach(function (b) { b.disabled = true; });
            if (boton) {
                boton.textContent = 'Guardando…';
            }
            new FormData(panel).forEach(function (valor, clave) {
                if (clave !== 'csrf_token') {
                    datos[clave] = valor;
                }
            });

            fetch(panel.getAttribute('action'), {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': tokenCsrf()
                },
                body: JSON.stringify(datos)
            }).then(function (respuesta) {
                var esJson = (respuesta.headers.get('Content-Type') || '').indexOf('application/json') !== -1;
                if (!esJson) {
                    avisar(mensajeDeFallo(respuesta));
                    return null;
                }
                return respuesta.json().then(function (cuerpo) {
                    if (respuesta.status === 201 && cuerpo.ok) {
                        exito(cuerpo, accion);
                    } else if (respuesta.status === 422 && cuerpo.errors) {
                        mostrarErrores(cuerpo.errors);
                    } else {
                        avisar('No se pudo guardar. Intentá de nuevo.');
                    }
                    return null;
                });
            }).catch(function () {
                avisar('No se pudo conectar. Revisá la conexión y volvé a intentar.');
            }).then(function () {
                enviando = false;
                panel.removeAttribute('aria-busy');
                botones.forEach(function (b, i) { b.disabled = deshabilitadosAntes[i]; });
                if (boton && boton.isConnected) {
                    boton.textContent = textoOriginal;
                }
            });
        }

        panel.addEventListener('submit', function (evento) {
            evento.preventDefault();
            enviar(evento.submitter || panel.querySelector('[data-accion="guardar"]'));
        });

        panel.addEventListener('keydown', function (evento) {
            if (evento.key === 'Escape') {
                evento.preventDefault();
                cerrar();
                return;
            }
            if (evento.key !== 'Tab') {
                return;
            }
            var enfocables = Array.prototype.filter.call(panel.querySelectorAll(SELECTOR_FOCO), esVisible);
            if (!enfocables.length) {
                return;
            }
            var primero = enfocables[0];
            var ultimo = enfocables[enfocables.length - 1];
            if (evento.shiftKey && document.activeElement === primero) {
                evento.preventDefault();
                ultimo.focus();
            } else if (!evento.shiftKey && document.activeElement === ultimo) {
                evento.preventDefault();
                primero.focus();
            }
        });

        panel.querySelectorAll('[data-drawer-cancel]').forEach(function (boton) {
            boton.addEventListener('click', function () { cerrar(); });
        });

        document.addEventListener('click', function (evento) {
            var disparador = evento.target.closest && evento.target.closest('[data-drawer-open="' + panel.id + '"]');
            if (disparador) {
                evento.preventDefault();
                abrir(disparador);
            }
        });

        return {
            abrir: abrir,
            cerrar: cerrar,
            estaAbierto: function () { return !panel.hidden; }
        };
    }

    global.App360DrawerForm = { crear: crear };
})(window);
