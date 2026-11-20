from flask import Blueprint, flash, g, make_response, redirect, render_template, request, session, url_for

import security
from config import Config
from extensions import limiter
from models import db
from models.core.user import User
from security import (
    SESION_HUELLA_CLAVE,
    SIN_ACCESO_ROUTE,
    datos_de_sesion_web,
    first_allowed_route,
    hay_sesion_web,
    huella_sesion,
    log_login_attempt,
    log_security_event,
    sesion_web_vigente,
)
from services.acceso_login import autenticar, completar_mfa, nombre_auditado
from services.mfa import (
    MENSAJE_CODIGO,
    contar_fallo_pendiente,
    descartar_pendiente,
    iniciar_pendiente_web,
    limite_ip_superado,
    pendiente_vigente,
    registrar_intento_ip,
)
from services.politica_clave import errores_clave_nueva

auth_bp = Blueprint("auth", __name__)


def ahora():
    """Reloj de seguridad resuelto en cada llamada (las pruebas lo fijan con security.ahora)."""
    return security.ahora()


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
        # Mismas reglas que la API (C4): bloqueo por cuenta, registro de accesos y tiempo igualado.
        resultado = autenticar(username, password, canal="web", ip=request.remote_addr)
        if not resultado.ok and resultado.motivo == "mfa_requerido":
            # Clave correcta con MFA: el segundo paso se pide antes de emitir la sesión (C6).
            iniciar_pendiente_web(session, resultado.usuario, ahora())
            return redirect(url_for("auth.login_mfa"))
        if resultado.ok:
            user = resultado.usuario
            session.update(datos_de_sesion_web(user))
            log_login_attempt(nombre_auditado(username, password), success=True, ip=request.remote_addr)
            if user.must_change_password:
                flash("Primero cambiá tu clave temporal.", "warning")
                return redirect(url_for("auth.cambiar_clave"))
            flash("Sesión iniciada correctamente.", "success")
            route = first_allowed_route(user.role)
            return redirect(route)

        log_login_attempt(nombre_auditado(username, password), success=False, ip=request.remote_addr)
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
        # El mismo bloqueo del restablecimiento serializa ambas operaciones y refresca
        # password_hash/token_version antes de validar la clave actual.
        usuario_id = usuario.id
        usuario = (
            User.query.filter_by(id=usuario_id)
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )
        if usuario is None or usuario.active is not True:
            db.session.rollback()
            session.clear()
            flash("Iniciá sesión para cambiar tu clave.", "warning")
            return redirect(url_for("auth.login"))
        g.usuario_sesion = usuario
        obligatorio = usuario.must_change_password
        errores = _errores_cambio_clave(usuario, actual, nueva, repetida)
        if errores:
            db.session.rollback()
            return (
                render_template(
                    "cambiar_clave.html",
                    obligatorio=obligatorio,
                    errores=errores,
                ),
                400,
            )

        usuario.set_password(nueva)  # también registra password_changed_at
        usuario.must_change_password = False
        usuario.temp_password_expires_at = None
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


@auth_bp.route("/login/mfa", methods=["GET", "POST"])
def login_mfa():
    """Segundo paso del login con MFA (C6): código de la aplicación o de respaldo.

    Sin paso pendiente vigente vuelve a la clave. Tras 5 fallos (o 5 minutos) se descarta el paso pendiente.
    """
    instante = ahora()
    pendiente = pendiente_vigente(session, instante)
    if pendiente is None:
        flash("Volvé a ingresar tu clave.", "warning")
        return redirect(url_for("auth.login"))
    con_error = False
    if request.method == "POST":
        ip = request.remote_addr
        if limite_ip_superado(ip, instante):
            con_error = True
        else:
            registrar_intento_ip(ip, instante)
            resultado = completar_mfa(pendiente["uid"], request.form.get("codigo", ""), canal="web", ip=ip)
            if resultado.ok:
                usuario = resultado.usuario
                descartar_pendiente(session)
                session.update(datos_de_sesion_web(usuario))
                log_login_attempt(usuario.username, success=True, ip=ip)
                if usuario.must_change_password:
                    flash("Primero cambiá tu clave temporal.", "warning")
                    return redirect(url_for("auth.cambiar_clave"))
                flash("Sesión iniciada correctamente.", "success")
                return redirect(first_allowed_route(usuario.role))
            con_error = True
        if con_error:
            if contar_fallo_pendiente(session, pendiente):
                descartar_pendiente(session)
                flash("Demasiados intentos. Volvé a ingresar tu clave.", "warning")
                return redirect(url_for("auth.login"))
            flash(MENSAJE_CODIGO, "warning")
    respuesta = make_response(
        render_template("login_mfa.html", title=Config.LOGIN_TITLE),
        400 if con_error else 200,
    )
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@auth_bp.route(SIN_ACCESO_ROUTE)
def sin_acceso():
    """Pantalla para usuarios sin módulos: no redirige de vuelta al login."""
    if not session.get("user"):
        return redirect(url_for("auth.login"))
    return render_template("sin_acceso.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Cierra la sesión con POST y CSRF (D15). GET no toca la sesión: redirige al login.

    El login reenvía a la pantalla de inicio si la sesión sigue viva, y muestra el formulario si no.
    """
    if request.method == "GET":
        return redirect(url_for("auth.login"))
    user = session.get("user")
    session.clear()
    if user:
        log_security_event('LOGOUT', f"User '{user}' logged out", user=user)
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
