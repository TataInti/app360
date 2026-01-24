from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app

from config import Config
from models import User
from security import first_allowed_route, log_login_attempt

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
        
        # Debug logging
        current_app.logger.info(f"Login attempt for username: '{username}'")
        
        user = User.query.filter_by(username=username, active=True).first()
        
        # Debug logging
        if user:
            current_app.logger.info(f"User found: {user.username}, active: {user.active}, has_hash: {bool(user.password_hash)}")
            password_check = user.check_password(password)
            current_app.logger.info(f"Password check result: {password_check}")
        else:
            current_app.logger.warning(f"User not found for username: '{username}'")

        if user and user.check_password(password):
            session["user"] = user.username
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

