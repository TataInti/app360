from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import Config
from models import User
from security import (
    SIN_ACCESO_ROUTE,
    datos_de_sesion_web,
    first_allowed_route,
    hay_sesion_web,
    log_login_attempt,
    log_security_event,
    sesion_web_vigente,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    # Import limiter here to avoid circular imports
    from app import limiter
    
    # La revalidación global no pasa por esta vista: una sesión previa se valida aquí.
    # Si está vencida, sesion_web_vigente() la limpia y el formulario sigue disponible.
    if hay_sesion_web() and sesion_web_vigente():
        route = first_allowed_route(session.get("role"))
        return redirect(route)

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()

        if user and user.check_password(password):
            session.update(datos_de_sesion_web(user))
            log_login_attempt(username, success=True, ip=request.remote_addr)
            flash("Sesión iniciada correctamente.", "success")
            route = first_allowed_route(user.role)
            return redirect(route)

        log_login_attempt(username, success=False, ip=request.remote_addr)
        flash("Usuario o contraseña incorrectos.", "warning")

    return render_template(
        "login.html",
        title=Config.LOGIN_TITLE,
    )


@auth_bp.route(SIN_ACCESO_ROUTE)
def sin_acceso():
    """Pantalla para usuarios sin módulos: no redirige de vuelta al login."""
    if not session.get("user"):
        return redirect(url_for("auth.login"))
    return render_template("sin_acceso.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Cierra la sesión web por completo. GET se mantiene: lo usa el sidebar."""
    user = session.get("user")
    session.clear()
    if user:
        log_security_event('LOGOUT', f"User '{user}' logged out", user=user)
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))

