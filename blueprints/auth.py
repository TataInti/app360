from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import Config
from models import User
from security import SIN_ACCESO_ROUTE, first_allowed_route, log_login_attempt

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    # Import limiter here to avoid circular imports
    from app import limiter
    
    if session.get("user"):
        route = first_allowed_route(session.get("role"))
        return redirect(route)

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()

        if user and user.check_password(password):
            session["user"] = user.username
            session["user_id"] = user.id
            session["role"] = user.role
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


@auth_bp.route("/logout")
def logout():
    user = session.get("user")
    session.pop("user", None)
    session.pop("role", None)
    if user:
        from security import log_security_event
        log_security_event('LOGOUT', f"User '{user}' logged out", user=user)
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))

