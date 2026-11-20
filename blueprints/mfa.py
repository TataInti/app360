"""Seguridad de la cuenta (C6): activar, confirmar, desactivar y regenerar el MFA del propio usuario.

Requiere sesión web normal (la clave temporal pendiente la bloquea el guardia de C1). Cada respuesta que
muestra un secreto o códigos de respaldo va con Cache-Control: no-store y no se registra en logs.
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from extensions import limiter
from models import db
import security
from services import mfa
from services.totp import agrupar_en_bloques

mfa_bp = Blueprint("mfa_bp", __name__)


def ahora():
    """Reloj de seguridad resuelto en cada llamada (las pruebas lo fijan con security.ahora)."""
    return security.ahora()

LIMITE_ACCION = "5 per 10 minutes"


@mfa_bp.after_request
def _sin_cache(respuesta):
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _usuario():
    return g.get("usuario_sesion")


def _pantalla(paso, **contexto):
    contexto.setdefault("errores", {})
    contexto.setdefault("mensaje", None)
    return render_template(
        "mi_cuenta_seguridad.html",
        estado=mfa.estado(_usuario()),
        paso=paso,
        **contexto,
    )


def _error(error, paso):
    db.session.rollback()
    return _pantalla(paso, errores=error.campos or {}, mensaje=error.mensaje), error.status


@mfa_bp.route("/mi-cuenta/seguridad")
def seguridad():
    if _usuario() is None:
        flash("Iniciá sesión para continuar.", "warning")
        return redirect(url_for("auth.login"))
    return _pantalla("inicio")


@mfa_bp.route("/mi-cuenta/seguridad/activar", methods=["POST"])
@limiter.limit(LIMITE_ACCION, methods=["POST"])
def activar():
    if _usuario() is None:
        return redirect(url_for("auth.login"))
    try:
        secreto, uri = mfa.iniciar_activacion(_usuario(), request.form.get("clave_actual", ""), ahora())
    except mfa.ErrorMfa as error:
        return _error(error, "inicio")
    # El secreto viaja solo en esta respuesta: no queda en la sesión ni se vuelve a mostrar.
    return _pantalla("confirmar", secreto=agrupar_en_bloques(secreto), uri=uri)


@mfa_bp.route("/mi-cuenta/seguridad/confirmar", methods=["POST"])
@limiter.limit(LIMITE_ACCION, methods=["POST"])
def confirmar():
    if _usuario() is None:
        return redirect(url_for("auth.login"))
    try:
        respaldos = mfa.confirmar_activacion(_usuario().id, request.form.get("codigo", ""), ahora())
    except mfa.ErrorMfa as error:
        return _error(error, "confirmar")
    return _pantalla("respaldos", respaldos=respaldos)


@mfa_bp.route("/mi-cuenta/seguridad/desactivar", methods=["POST"])
@limiter.limit(LIMITE_ACCION, methods=["POST"])
def desactivar():
    if _usuario() is None:
        return redirect(url_for("auth.login"))
    try:
        mfa.desactivar(_usuario().id, request.form.get("clave_actual", ""), request.form.get("codigo", ""), ahora())
    except mfa.ErrorMfa as error:
        return _error(error, "inicio")
    flash("MFA desactivado. Tu cuenta vuelve a entrar solo con tu clave.", "success")
    return redirect(url_for("mfa_bp.seguridad"))


@mfa_bp.route("/mi-cuenta/seguridad/regenerar", methods=["POST"])
@limiter.limit(LIMITE_ACCION, methods=["POST"])
def regenerar():
    if _usuario() is None:
        return redirect(url_for("auth.login"))
    try:
        respaldos = mfa.regenerar_respaldos(_usuario().id, request.form.get("clave_actual", ""), request.form.get("codigo", ""), ahora())
    except mfa.ErrorMfa as error:
        return _error(error, "inicio")
    return _pantalla("respaldos", respaldos=respaldos)
