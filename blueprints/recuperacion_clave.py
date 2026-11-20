"""Canje público de la recuperación de clave (C5): GET y POST /recuperar-clave, sin sesión.

El enlace trae el token en el fragmento (#): el navegador no lo envía al servidor. Un JS mínimo lo copia
a un campo oculto y borra el fragmento de la barra. La respuesta no se guarda en caché y no envía Referer.
Las respuestas de fallo son iguales para todos los motivos (400, misma página, mismo mensaje).
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from extensions import limiter
from services import recuperacion_clave as rc

recuperacion_bp = Blueprint("recuperacion", __name__)


@recuperacion_bp.after_request
def _cabeceras(respuesta):
    respuesta.headers["Cache-Control"] = "no-store"
    # Los after_request de blueprint corren antes que los de la app: la app usa setdefault para no pisarla.
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta


def _pagina(token="", errores=None, status=200, mensaje=None):
    return (
        render_template("recuperar_clave.html", token=token, errores=errores or {}, mensaje=mensaje),
        status,
    )


@recuperacion_bp.route("/recuperar-clave", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def recuperar_clave():
    if request.method == "GET":
        return _pagina()
    token = request.form.get("token", "")
    resultado, dato = rc.canjear(
        token,
        request.form.get("new_password", ""),
        request.form.get("confirm", ""),
        ip=request.remote_addr,
    )
    if resultado == "ok":
        flash("Listo: tu clave quedó actualizada. Ingresá con tu nueva clave.", "success")
        return redirect(url_for("auth.login"))
    if resultado == "politica":
        return _pagina(token=token.strip(), errores=dato, status=400)
    return _pagina(mensaje=rc.MENSAJE_INVALIDO, status=400)
