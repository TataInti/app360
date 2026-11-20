/* Recuperación de clave (C5): toma el token del fragmento del enlace (#token), lo copia al campo oculto
   y borra el fragmento de la barra de direcciones. El servidor nunca recibe el token en la URL. */
(function () {
  "use strict";

  const campo = document.getElementById("token");
  const formulario = document.getElementById("formRecuperar");
  const aviso = document.getElementById("sinEnlace");
  if (!campo || !formulario) {
    return;
  }

  const fragmento = window.location.hash.slice(1);
  if (fragmento) {
    campo.value = fragmento;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }

  const hayToken = campo.value.length > 0;
  formulario.hidden = !hayToken;
  if (aviso && hayToken) {
    aviso.hidden = true;
  }
})();
