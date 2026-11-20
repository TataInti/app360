/* Administración > Usuarios (C2 y C3): lista con filtros, alta con clave temporal (se muestra una sola vez),
   cambio de rol, restablecimiento de clave, desactivar y reactivar. Todo texto que viene de la API se
   escribe con textContent. La clave temporal vive solo en el panel de confirmación del DOM: no va a la
   URL, al almacenamiento local ni a la consola. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const yo = Number($("pantallaUsuarios").dataset.yo || "0");
  const CLASES_ESTADO = {
    activo: "bg-success",
    desactivado: "bg-secondary",
    cambiar_clave: "bg-warning text-dark",
    clave_vencida: "bg-danger",
  };
  const MOTIVO_PROPIA = "Es tu cuenta: pedile a otro administrador que lo haga.";
  const usuariosPorId = new Map();
  let usuarioEnRol = null;
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

  function notaFila(texto) {
    const nota = document.createElement("div");
    nota.className = "small text-muted mt-1";
    nota.textContent = texto;
    return nota;
  }

  function botonAccion(texto, clases, datos, deshabilitado, motivo) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "btn btn-sm " + clases;
    boton.textContent = texto;
    Object.assign(boton.dataset, datos);
    if (deshabilitado) {
      boton.disabled = true;
      boton.title = motivo;
    }
    return boton;
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
    if (usuario.estado === "cambiar_clave" && usuario.clave_temporal_vence_texto) {
      tdEstado.appendChild(notaFila("Clave temporal vence el " + usuario.clave_temporal_vence_texto));
    }
    if (usuario.estado === "clave_vencida") {
      tdEstado.appendChild(notaFila("Usá «Restablecer clave» para generar una nueva."));
    }
    if (usuario.bloqueada) {
      const bloqueo = document.createElement("span");
      bloqueo.className = "badge bg-danger ms-1";
      bloqueo.textContent = "Bloqueada hasta " + usuario.bloqueada_hasta_texto;
      tdEstado.appendChild(bloqueo);
    }
    tr.appendChild(tdEstado);

    tr.appendChild(celda(usuario.ultimo_acceso_texto));

    const propia = usuario.id === yo;
    const desactivado = usuario.estado === "desactivado";
    const datos = { id: String(usuario.id), usuario: usuario.username };
    const tdAccion = document.createElement("td");
    tdAccion.className = "text-center";
    const grupo = document.createElement("div");
    grupo.className = "d-flex flex-wrap gap-1 justify-content-center";
    grupo.appendChild(botonAccion("Cambiar rol", "btn-outline-primary", { ...datos, accion: "rol" }, propia, MOTIVO_PROPIA));
    grupo.appendChild(
      botonAccion(
        "Restablecer clave",
        "btn-outline-warning",
        { ...datos, accion: "restablecer" },
        propia || desactivado,
        propia ? MOTIVO_PROPIA : "Reactivalo primero para restablecer su clave."
      )
    );
    grupo.appendChild(
      botonAccion(
        desactivado ? "Reactivar" : "Desactivar",
        desactivado ? "btn-outline-success" : "btn-outline-danger",
        { ...datos, accion: desactivado ? "reactivar" : "desactivar" },
        propia,
        MOTIVO_PROPIA
      )
    );
    if (usuario.bloqueada) {
      grupo.appendChild(botonAccion("Desbloquear", "btn-outline-danger", { ...datos, accion: "desbloquear" }, false));
    }
    tdAccion.appendChild(grupo);
    if (propia) {
      tdAccion.appendChild(notaFila(MOTIVO_PROPIA));
    }
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
    usuariosPorId.clear();
    usuarios.forEach((usuario) => usuariosPorId.set(usuario.id, usuario));
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

  function mostrarErrorRol(texto) {
    const el = $("modalRolError");
    el.textContent = texto || "";
    el.classList.toggle("d-block", Boolean(texto));
    $("modalRolSelect").classList.toggle("is-invalid", Boolean(texto));
  }

  function actualizarTextoRol() {
    if (!usuarioEnRol) {
      return;
    }
    const select = $("modalRolSelect");
    const etiqueta = select.options[select.selectedIndex]?.textContent || "";
    const nombre = usuarioEnRol.username;
    $("modalRolTexto").textContent =
      select.value === usuarioEnRol.rol
        ? nombre + " ya tiene el rol " + etiqueta + ". No se cambia nada."
        : "¿Cambiar el rol de " + nombre + " a " + etiqueta + "? El rol define a qué módulos puede entrar. El cambio se aplica desde su próxima acción.";
  }

  function abrirCambioRol(usuario) {
    usuarioEnRol = usuario;
    const select = $("modalRolSelect");
    // Un rol que ya no se asigna (por ejemplo «manager») queda visible y preseleccionado; no se ofrece a otros.
    select.querySelectorAll("option[data-extra]").forEach((opcion) => opcion.remove());
    if (![...select.options].some((opcion) => opcion.value === usuario.rol)) {
      const opcion = document.createElement("option");
      opcion.value = usuario.rol;
      opcion.textContent = usuario.rol_nombre + " (actual, no asignable)";
      opcion.dataset.extra = "1";
      select.appendChild(opcion);
    }
    select.value = usuario.rol;
    $("modalRolTitulo").textContent = "Cambiar rol de " + usuario.username;
    mostrarErrorRol("");
    actualizarTextoRol();
    bootstrap.Modal.getOrCreateInstance($("modalRol")).show();
  }

  async function enviarRol(evento) {
    evento.preventDefault();
    if (!usuarioEnRol) {
      return;
    }
    const boton = $("btnGuardarRol");
    const nombre = usuarioEnRol.username;
    boton.disabled = true;
    mostrarErrorRol("");
    try {
      const res = await llamar("/api/admin/usuarios/" + usuarioEnRol.id + "/rol", "POST", {
        role: $("modalRolSelect").value,
      });
      if (!res.ok) {
        mostrarErrorRol(res.datos.campos?.role || res.datos.error || "No se pudo cambiar el rol. No se aplicó ningún cambio.");
        return;
      }
      bootstrap.Modal.getOrCreateInstance($("modalRol")).hide();
      mostrarAviso(
        res.datos.cambiado
          ? nombre + " ahora tiene el rol " + res.datos.usuario.rol_nombre + ". El cambio se aplica desde su próxima acción."
          : nombre + " ya tenía ese rol. No se cambió nada.",
        "ok"
      );
      await recargar();
    } finally {
      boton.disabled = false;
    }
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

  function mostrarClaveTemporal(datos, titulo) {
    $("claveTitulo").textContent = titulo;
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

  async function desbloquearUsuario(boton) {
    const nombre = boton.dataset.usuario;
    const confirmado = await confirmar({
      variant: "warning",
      title: "Desbloquear cuenta",
      message: "¿Desbloquear a " + nombre + "? Se borran los intentos fallidos y puede entrar de inmediato con su clave actual.",
      confirmText: "Desbloquear",
    });
    if (!confirmado) {
      return;
    }
    sinAviso();
    const res = await llamar("/api/admin/usuarios/" + boton.dataset.id + "/desbloquear", "POST");
    if (!res.ok) {
      mostrarAviso(res.datos.error || "No se pudo desbloquear la cuenta. No se aplicó ningún cambio.", "error");
      await recargar();
      return;
    }
    mostrarAviso("La cuenta de " + nombre + " quedó desbloqueada.", "ok");
    await recargar();
  }

  async function restablecerClave(boton) {
    const nombre = boton.dataset.usuario;
    const confirmado = await confirmar({
      variant: "warning",
      title: "Restablecer clave",
      message: "¿Restablecer la clave de " + nombre + "? Se genera una clave temporal nueva, la clave actual deja de funcionar, se cierran sus sesiones activas y deberá cambiarla al ingresar.",
      confirmText: "Restablecer",
    });
    if (!confirmado) {
      return;
    }
    sinAviso();
    const res = await llamar("/api/admin/usuarios/" + boton.dataset.id + "/restablecer-clave", "POST");
    if (!res.ok) {
      mostrarAviso(res.datos.error || "No se pudo restablecer la clave. No se aplicó ningún cambio.", "error");
      await recargar();
      return;
    }
    mostrarClaveTemporal(res.datos, "Clave restablecida");
    await recargar();
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
        mostrarClaveTemporal(res.datos, "Usuario creado");
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
      if (!boton || boton.disabled) {
        return;
      }
      if (boton.dataset.accion === "rol") {
        const usuario = usuariosPorId.get(Number(boton.dataset.id));
        if (usuario) {
          abrirCambioRol(usuario);
        }
      } else if (boton.dataset.accion === "restablecer") {
        restablecerClave(boton);
      } else if (boton.dataset.accion === "desbloquear") {
        desbloquearUsuario(boton);
      } else {
        alternarUsuario(boton);
      }
    });
    $("formRol").addEventListener("submit", enviarRol);
    $("modalRolSelect").addEventListener("change", actualizarTextoRol);
    recargar();
  }

  iniciar();
})();
