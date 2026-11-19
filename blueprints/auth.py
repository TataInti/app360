from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from datetime import datetime, timezone

from config import Config
from extensions import limiter
from models import User, db
from security import (
    SESION_HUELLA_CLAVE,
    SIN_ACCESO_ROUTE,
    datos_de_sesion_web,
    first_allowed_route,
    hay_sesion_web,
    huella_sesion,
    log_login_attempt,
    log_security_event,
    registrar_ultimo_acceso,
    sesion_web_vigente,
    verificar_clave_login,
)
from services.politica_clave import errores_clave_nueva

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    # Import limiter here to avoid circular imports
    from app import limiter
    
    # La revalidación global no pasa por esta vista: una sesión previa se valida aquí.
    # Si está vencida, sesion_web_vigente() la limpia y el formulario sigue disponible.
    if hay_sesion_web() and sesion_web_vigente():
        if g.usuario_sesion.must_change_password:
            return redirect(url_for("auth.cambiar_clave"))
        route = first_allowed_route(session.get("role"))
        return redirect(route)

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()

        # Mismo trabajo de hash con o sin usuario: el tiempo de respuesta no revela si existe.
        if verificar_clave_login(user, password):
            registrar_ultimo_acceso(user)
            session.update(datos_de_sesion_web(user))
            log_login_attempt(username, success=True, ip=request.remote_addr)
            if user.must_change_password:
                flash("Primero cambiá tu clave temporal.", "warning")
                return redirect(url_for("auth.cambiar_clave"))
            flash("Sesión iniciada correctamente.", "success")
            route = first_allowed_route(user.role)
            return redirect(route)

        log_login_attempt(username, success=False, ip=request.remote_addr)
        flash("Usuario o contraseña incorrectos.", "warning")

    return render_template(
        "login.html",
        title=Config.LOGIN_TITLE,
    )


@auth_bp.route("/cambiar-clave", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def cambiar_clave():
    """Cambio de clave propia, con la clave actual. Para cualquier usuario con sesión (C1)."""
    usuario = g.get("usuario_sesion")
    if usuario is None:
        flash("Iniciá sesión para cambiar tu clave.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        actual = request.form.get("clave_actual", "")
        nueva = request.form.get("clave_nueva", "")
        repetida = request.form.get("repetir_clave", "")
        errores = _errores_cambio_clave(usuario, actual, nueva, repetida)
        if errores:
            return (
                render_template(
                    "cambiar_clave.html",
                    obligatorio=usuario.must_change_password,
                    errores=errores,
                ),
                400,
            )

        usuario.set_password(nueva)
        usuario.password_changed_at = datetime.now(timezone.utc)
        usuario.must_change_password = False
        db.session.commit()
        # La sesión actual sigue abierta: su huella se recalcula con la clave nueva. Las otras
        # sesiones guardan la huella vieja y dejan de valer en su próxima petición (D9).
        session[SESION_HUELLA_CLAVE] = huella_sesion(usuario)
        log_security_event("PASSWORD_CHANGED", "El usuario cambió su clave", user=usuario.username)
        flash("Clave actualizada. Cerramos tus otras sesiones.", "success")
        return redirect(first_allowed_route(usuario.role))

    return render_template(
        "cambiar_clave.html",
        obligatorio=usuario.must_change_password,
        errores={},
    )


def _errores_cambio_clave(usuario, actual, nueva, repetida):
    """Errores por campo. La clave nueva se evalúa solo si la actual es correcta."""
    if not actual:
        return {"clave_actual": "Ingresá tu clave actual."}
    if not usuario.check_password(actual):
        log_security_event(
            "PASSWORD_CHANGE_FAILED",
            "Clave actual incorrecta al intentar cambiarla",
            user=usuario.username,
        )
        return {"clave_actual": "La clave actual no es correcta."}
    return errores_clave_nueva(nueva, repetida, usuario.username, actual)


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
