/* Administración > Usuarios (C2): lista con filtros, alta con clave temporal (se muestra una sola vez),
   desactivar y reactivar. Todo texto que viene de la API se escribe con textContent. La clave temporal
   vive solo en el panel de confirmación del DOM: no va a la URL, al almacenamiento local ni a la consola. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const CLASES_ESTADO = {
    activo: "bg-success",
    desactivado: "bg-secondary",
    cambiar_clave: "bg-warning text-dark",
  };
  let temporizadorBusqueda = null;

  function aviso(texto, tipo) {
    const el = $("avisoUsuarios");
    el.textContent = texto;
    el.className = "alert " + (tipo === "ok" ? "alert-success" : "alert-danger");
    el.setAttribute("role", tipo === "ok" ? "status" : "alert");
  }

  function sinAviso() {
    $("avisoUsuarios").textContent = "";
    $("avisoUsuarios").classList.add("d-none");
  }

  function mostrarAviso(texto, tipo) {
    aviso(texto, tipo);
    $("avisoUsuarios").classList.remove("d-none");
  }

  async function llamar(url, metodo = "GET", cuerpo) {
    const opciones = {
      method: metodo,
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    };
    if (cuerpo !== undefined) {
      opciones.headers["Content-Type"] = "application/json";
      opciones.body = JSON.stringify(cuerpo);
    }
    if (metodo !== "GET") {
      opciones.headers["X-CSRFToken"] = csrf;
    }
    const respuesta = await fetch(url, opciones);
    if (respuesta.redirected) {
      // La sesión venció: el servidor manda al login.
      window.location.assign(respuesta.url);
      return { ok: false, status: 401, datos: { error: "Tu sesión ya no es válida. Volvé a iniciar sesión." } };
    }
    let datos = {};
    try {
      datos = await respuesta.json();
    } catch (_) {
      datos = {};
    }
    return { ok: respuesta.ok, status: respuesta.status, datos: datos };
  }

  async function confirmar(opciones) {
    if (window.App360UI && typeof window.App360UI.confirm === "function") {
      return window.App360UI.confirm(opciones);
    }
    return window.confirm(opciones.message);
  }

  function celda(texto, clase) {
    const td = document.createElement("td");
    if (clase) {
      td.className = clase;
    }
    td.textContent = texto;
    return td;
  }

  function filaUsuario(usuario) {
    const tr = document.createElement("tr");
    tr.appendChild(celda(usuario.username, "fw-semibold"));
    tr.appendChild(celda(usuario.rol_nombre));

    const tdEstado = document.createElement("td");
    const etiqueta = document.createElement("span");
    etiqueta.className = "badge " + (CLASES_ESTADO[usuario.estado] || "bg-secondary");
    etiqueta.textContent = usuario.estado_nombre;
    tdEstado.appendChild(etiqueta);
    tr.appendChild(tdEstado);

    tr.appendChild(celda(usuario.ultimo_acceso_texto));

    const tdAccion = document.createElement("td");
    tdAccion.className = "text-center";
    const boton = document.createElement("button");
    boton.type = "button";
    const desactivado = usuario.estado === "desactivado";
    boton.className = "btn btn-sm " + (desactivado ? "btn-outline-success" : "btn-outline-danger");
    boton.textContent = desactivado ? "Reactivar" : "Desactivar";
    boton.dataset.accion = desactivado ? "reactivar" : "desactivar";
    boton.dataset.id = String(usuario.id);
    boton.dataset.usuario = usuario.username;
    tdAccion.appendChild(boton);
    tr.appendChild(tdAccion);
    return tr;
  }

  async function cargarUsuarios() {
    const params = new URLSearchParams({
      q: $("buscarUsuario").value.trim(),
      estado: $("filtroEstado").value,
    });
    const res = await llamar("/api/admin/usuarios?" + params.toString());
    $("cargandoUsuarios").classList.add("d-none");
    if (!res.ok) {
      mostrarAviso(res.datos.error || "No se pudo cargar la lista de usuarios.", "error");
      return;
    }
    const usuarios = res.datos.usuarios || [];
    $("cuerpoUsuarios").replaceChildren(...usuarios.map(filaUsuario));
    $("estadoVacioUsuarios").classList.toggle("d-none", usuarios.length > 0);
  }

  async function cargarAuditoria() {
    const res = await llamar("/api/admin/usuarios/auditoria");
    if (!res.ok) {
      return;
    }
    const eventos = res.datos.eventos || [];
    const filas = eventos.map((evento) => {
      const tr = document.createElement("tr");
      tr.appendChild(celda(evento.fecha || ""));
      tr.appendChild(celda(evento.quien));
      tr.appendChild(celda(evento.accion));
      tr.appendChild(celda(evento.a_quien));
      return tr;
    });
    $("cuerpoAuditoria").replaceChildren(...filas);
    $("estadoVacioAuditoria").classList.toggle("d-none", eventos.length > 0);
  }

  async function recargar() {
    await Promise.all([cargarUsuarios(), cargarAuditoria()]);
  }

  async function alternarUsuario(boton) {
    const reactivar = boton.dataset.accion === "reactivar";
    const nombre = boton.dataset.usuario;
    const confirmado = await confirmar(
      reactivar
        ? {
            variant: "info",
            title: "Reactivar usuario",
            message: "¿Reactivar a " + nombre + "? Vuelve a tener acceso con el mismo rol y con su clave actual.",
            confirmText: "Reactivar",
          }
        : {
            variant: "danger",
            title: "Desactivar usuario",
            message: "¿Desactivar a " + nombre + "? Pierde el acceso de inmediato y se cierran sus sesiones activas. Sus datos se conservan; podés reactivarlo cuando quieras.",
            confirmText: "Desactivar",
          }
    );
    if (!confirmado) {
      return;
    }
    sinAviso();
    const accion = reactivar ? "reactivar" : "desactivar";
    const res = await llamar("/api/admin/usuarios/" + boton.dataset.id + "/" + accion, "POST");
    if (!res.ok) {
      mostrarAviso(res.datos.error || "No se pudo completar la acción. No se aplicó ningún cambio.", "error");
      await recargar();
      return;
    }
    mostrarAviso(reactivar ? nombre + " volvió a tener acceso." : nombre + " quedó desactivado.", "ok");
    await recargar();
  }

  function limpiarErroresAlta() {
    for (const campo of ["altaUsuario", "altaRol"]) {
      $(campo).classList.remove("is-invalid");
    }
    $("altaUsuarioError").textContent = "";
    $("altaRolError").textContent = "";
  }

  function mostrarErroresAlta(campos) {
    if (campos.username) {
      $("altaUsuario").classList.add("is-invalid");
      $("altaUsuarioError").textContent = campos.username;
    }
    if (campos.role) {
      $("altaRol").classList.add("is-invalid");
      $("altaRolError").textContent = campos.role;
    }
  }

  function textoVencimiento(iso) {
    if (!iso) {
      return "";
    }
    return new Date(iso).toLocaleString("es-AR", {
      timeZone: "America/Argentina/Buenos_Aires",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function mostrarClaveTemporal(datos) {
    $("claveUsuarioNombre").textContent = datos.usuario.username;
    $("claveVence").textContent = textoVencimiento(datos.clave_temporal_vence);
    $("clave_temporal_nueva").textContent = datos.clave_temporal;
    $("panelClaveTemporal").classList.remove("d-none");
    $("panelAltaUsuario").classList.add("d-none");
    $("btnNuevoUsuario").setAttribute("aria-expanded", "false");
    $("panelClaveTemporal").scrollIntoView({ block: "nearest" });
  }

  function ocultarClaveTemporal() {
    // Al cerrar, la clave deja de estar en el DOM: no se vuelve a mostrar.
    $("clave_temporal_nueva").textContent = "";
    $("claveUsuarioNombre").textContent = "";
    $("claveVence").textContent = "";
    $("panelClaveTemporal").classList.add("d-none");
  }

  async function enviarAlta(evento) {
    evento.preventDefault();
    limpiarErroresAlta();
    sinAviso();
    const boton = $("btnCrearUsuario");
    boton.disabled = true;
    try {
      const res = await llamar("/api/admin/usuarios", "POST", {
        username: $("altaUsuario").value,
        role: $("altaRol").value,
      });
      if (res.status === 201) {
        $("formAltaUsuario").reset();
        mostrarClaveTemporal(res.datos);
        await recargar();
        return;
      }
      if (res.datos.campos) {
        mostrarErroresAlta(res.datos.campos);
      }
      mostrarAviso(res.datos.error || "No se pudo crear el usuario. No se aplicó ningún cambio.", "error");
    } finally {
      boton.disabled = false;
    }
  }

  async function copiarClave() {
    const texto = $("clave_temporal_nueva").textContent;
    const boton = $("btnCopiarClave");
    try {
      await navigator.clipboard.writeText(texto);
      boton.textContent = "Copiada";
    } catch (_) {
      // Sin acceso al portapapeles (HTTP): se selecciona el texto para copiarlo a mano.
      const rango = document.createRange();
      rango.selectNodeContents($("clave_temporal_nueva"));
      const seleccion = window.getSelection();
      seleccion.removeAllRanges();
      seleccion.addRange(rango);
      boton.textContent = "Seleccionada: copiala con Ctrl+C";
    }
  }

  function iniciar() {
    $("btnNuevoUsuario").addEventListener("click", () => {
      const panel = $("panelAltaUsuario");
      const abrir = panel.classList.contains("d-none");
      panel.classList.toggle("d-none", !abrir);
      $("btnNuevoUsuario").setAttribute("aria-expanded", String(abrir));
      if (abrir) {
        $("altaUsuario").focus();
      }
    });
    $("btnCancelarAlta").addEventListener("click", () => {
      $("panelAltaUsuario").classList.add("d-none");
      $("btnNuevoUsuario").setAttribute("aria-expanded", "false");
      limpiarErroresAlta();
    });
    $("formAltaUsuario").addEventListener("submit", enviarAlta);
    $("btnCerrarClave").addEventListener("click", ocultarClaveTemporal);
    $("btnCopiarClave").addEventListener("click", copiarClave);
    $("buscarUsuario").addEventListener("input", () => {
      clearTimeout(temporizadorBusqueda);
      temporizadorBusqueda = setTimeout(cargarUsuarios, 300);
    });
    $("filtroEstado").addEventListener("change", cargarUsuarios);
    $("cuerpoUsuarios").addEventListener("click", (evento) => {
      const boton = evento.target.closest("button[data-accion]");
      if (boton) {
        alternarUsuario(boton);
      }
    });
    recargar();
  }

  iniciar();
})();
