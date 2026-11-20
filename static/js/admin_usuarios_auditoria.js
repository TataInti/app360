/* Administración > Usuarios > Auditoría completa (C4): filtros por usuario, acción y fechas, página de 50
   del servidor y textos legibles. Todo dato que viene de la API se escribe con textContent: nada de la
   auditoría se interpreta como HTML. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const ESPERA_BUSQUEDA_MS = 300;
  let pagina = 1;
  let paginas = 1;
  let temporizador = null;
  let solicitud = 0;

  function mostrarAviso(texto) {
    const aviso = $("avisoAuditoria");
    aviso.textContent = texto;
    aviso.classList.toggle("d-none", !texto);
  }

  function hayFiltros() {
    return (
      $("filtroUsuarioAuditoria").value.trim() !== "" ||
      $("filtroAccionAuditoria").value !== "todas" ||
      $("filtroDesdeAuditoria").value !== "" ||
      $("filtroHastaAuditoria").value !== ""
    );
  }

  function parametros() {
    const params = new URLSearchParams();
    const usuario = $("filtroUsuarioAuditoria").value.trim();
    if (usuario) {
      params.set("q", usuario);
    }
    params.set("accion", $("filtroAccionAuditoria").value || "todas");
    const desde = $("filtroDesdeAuditoria").value;
    const hasta = $("filtroHastaAuditoria").value;
    if (desde) {
      params.set("desde", desde);
    }
    if (hasta) {
      params.set("hasta", hasta);
    }
    params.set("pagina", String(pagina));
    return params;
  }

  function celda(texto, clase) {
    const td = document.createElement("td");
    if (clase) {
      td.className = clase;
    }
    td.textContent = texto;
    return td;
  }

  function filaEvento(evento) {
    const tr = document.createElement("tr");
    tr.appendChild(celda(evento.fecha || "—", "text-nowrap"));
    tr.appendChild(celda(evento.quien || "—"));
    tr.appendChild(celda(evento.accion || "—"));
    tr.appendChild(celda(evento.a_quien || "—"));
    tr.appendChild(celda(evento.detalle || "—"));
    tr.appendChild(celda(evento.ip || "—", "text-nowrap"));
    return tr;
  }

  function pintarPaginacion(datos) {
    paginas = datos.paginas || 1;
    pagina = datos.pagina || 1;
    const total = datos.total || 0;
    const acciones = total === 1 ? "acción" : "acciones";
    $("textoPaginaAuditoria").textContent = "Página " + pagina + " de " + paginas + " · " + total + " " + acciones;
    $("btnPaginaAnterior").disabled = pagina <= 1;
    $("btnPaginaSiguiente").disabled = pagina >= paginas;
  }

  async function cargar() {
    const numero = ++solicitud;
    $("cargandoAuditoria").classList.remove("d-none");
    let respuesta;
    try {
      respuesta = await fetch("/api/admin/usuarios/auditoria?" + parametros().toString(), {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
    } catch (_) {
      if (numero === solicitud) {
        $("cargandoAuditoria").classList.add("d-none");
        mostrarAviso("No pudimos cargar la auditoría. Revisá la conexión y volvé a intentar.");
      }
      return;
    }
    if (respuesta.redirected) {
      // La sesión venció: el servidor manda al login.
      window.location.assign(respuesta.url);
      return;
    }
    let datos = {};
    try {
      datos = await respuesta.json();
    } catch (_) {
      datos = {};
    }
    if (numero !== solicitud) {
      // Respuesta vieja: ya hay una búsqueda más nueva en curso.
      return;
    }
    $("cargandoAuditoria").classList.add("d-none");
    if (!respuesta.ok) {
      const campos = datos.campos ? Object.values(datos.campos).join(" ") : "";
      mostrarAviso(campos || datos.error || "No se pudo cargar la auditoría.");
      return;
    }
    mostrarAviso("");
    const eventos = datos.eventos || [];
    $("cuerpoAuditoriaCompleta").replaceChildren(...eventos.map(filaEvento));
    $("tituloVacioAuditoria").textContent = hayFiltros()
      ? "Ninguna acción coincide con estos filtros"
      : "Todavía no hay acciones registradas";
    $("estadoVacioAuditoria").classList.toggle("d-none", eventos.length > 0);
    pintarPaginacion(datos);
  }

  function buscarDesdePrimeraPagina() {
    pagina = 1;
    cargar();
  }

  function iniciar() {
    $("filtroUsuarioAuditoria").addEventListener("input", () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(buscarDesdePrimeraPagina, ESPERA_BUSQUEDA_MS);
    });
    for (const id of ["filtroAccionAuditoria", "filtroDesdeAuditoria", "filtroHastaAuditoria"]) {
      $(id).addEventListener("change", buscarDesdePrimeraPagina);
    }
    $("formFiltrosAuditoria").addEventListener("submit", (evento) => {
      evento.preventDefault();
      clearTimeout(temporizador);
      buscarDesdePrimeraPagina();
    });
    $("btnLimpiarAuditoria").addEventListener("click", () => {
      clearTimeout(temporizador);
      $("filtroUsuarioAuditoria").value = "";
      $("filtroAccionAuditoria").value = "todas";
      $("filtroDesdeAuditoria").value = "";
      $("filtroHastaAuditoria").value = "";
      buscarDesdePrimeraPagina();
    });
    $("btnPaginaAnterior").addEventListener("click", () => {
      if (pagina > 1) {
        pagina -= 1;
        cargar();
      }
    });
    $("btnPaginaSiguiente").addEventListener("click", () => {
      if (pagina < paginas) {
        pagina += 1;
        cargar();
      }
    });
    cargar();
  }

  iniciar();
})();
