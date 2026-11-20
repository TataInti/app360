"""Administración > Usuarios (C2 y C3): pantalla, API JSON, alta, activación, rol, clave y auditoría.

Todas las rutas exigen administración (admin, manager, gerente). Anónimo: 401 JSON en la API (la
guardia de app.py responde antes del CSRF) y login en la pantalla. Sin rol de administración: 403 en
la pantalla y en la API. Las respuestas no se guardan en caché (Cache-Control: no-store), porque el
alta y el restablecimiento devuelven una clave temporal.
"""

from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import db
from security import es_ruta_api
from services import usuarios_admin as ua

admin_usuarios_bp = Blueprint("admin_usuarios", __name__)


def _error(codigo, mensaje, status, campos=None):
    cuerpo = {"error": mensaje, "codigo": codigo}
    if campos:
        cuerpo["campos"] = campos
    return jsonify(cuerpo), status


def _responder_error(error):
    return _error(error.codigo, error.mensaje, error.status, error.campos)


def _fallo_interno(accion, error=None):
    # No se registra str(error): SQLAlchemy puede incluir parámetros de la consulta.
    db.session.rollback()
    origen = getattr(error, "orig", None)
    sqlstate = getattr(origen, "pgcode", None) or getattr(origen, "sqlstate", None)
    current_app.logger.error(
        "Falló una acción de administración de usuarios: accion=%s exception=%s sqlstate=%s",
        accion,
        type(error).__name__ if error is not None else "desconocida",
        sqlstate or "n/a",
    )
    return _error("ERROR_INTERNO", "No se pudo completar la acción. No se aplicó ningún cambio.", 500)


def admin_usuarios_required(f):
    """Guardia de Administración > Usuarios: solo administradores (admin, manager, gerente)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session or g.get("usuario_sesion") is None:
            if es_ruta_api():
                return _error("SESION_REQUERIDA", "Iniciá sesión para continuar.", 401)
            flash("Debe iniciar sesión.", "warning")
            return redirect(url_for("auth.login"))
        if session.get("role") not in ua.ROLES_ADMINISTRACION:
            if es_ruta_api():
                return _error("SIN_PERMISO", "Esta acción es solo para administradores.", 403)
            return render_template("admin/sin_permiso_admin.html"), 403
        return f(*args, **kwargs)

    return decorated


@admin_usuarios_bp.after_request
def _sin_cache(respuesta):
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@admin_usuarios_bp.route("/admin/usuarios")
@admin_usuarios_required
def pantalla():
    return render_template("admin/usuarios.html", roles=ua.roles_asignables_para(g.usuario_sesion))


@admin_usuarios_bp.route("/api/admin/usuarios", methods=["GET"])
@admin_usuarios_required
def listar():
    estado = request.args.get("estado", "todos")
    if estado not in ua.ESTADOS_FILTRO:
        estado = "todos"
    usuarios = ua.listar_usuarios(q=request.args.get("q", ""), estado=estado)
    return jsonify(
        {
            "usuarios": [ua.serializar_usuario(u) for u in usuarios],
            "total": len(usuarios),
            "roles_asignables": [
                {"codigo": codigo, "nombre": nombre}
                for codigo, nombre in ua.roles_asignables_para(g.usuario_sesion)
            ],
        }
    )


@admin_usuarios_bp.route("/api/admin/usuarios", methods=["POST"])
@admin_usuarios_required
def crear():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return _error("DATOS_INVALIDOS", "Enviá el alta como JSON con usuario y rol.", 400)
    try:
        usuario, clave, vence = ua.crear_usuario(g.usuario_sesion, datos.get("username"), datos.get("role"))
    except ua.ErrorUsuarios as error:
        db.session.rollback()
        return _responder_error(error)
    except Exception as error:
        return _fallo_interno("alta", error)
    # La clave temporal viaja solo en esta respuesta: no va a la URL, a los logs ni a la auditoría.
    cuerpo = {
        "usuario": ua.serializar_usuario(usuario),
        "clave_temporal": clave,
        "clave_temporal_vence": vence.isoformat(),
    }
    return jsonify(cuerpo), 201


def _cambiar_estado(usuario_id, operacion, nombre):
    try:
        usuario = operacion(g.usuario_sesion, usuario_id)
    except ua.ErrorUsuarios as error:
        db.session.rollback()
        return _responder_error(error)
    except Exception as error:
        return _fallo_interno(nombre, error)
    return jsonify({"usuario": ua.serializar_usuario(usuario)})


@admin_usuarios_bp.route("/api/admin/usuarios/<int:usuario_id>/desactivar", methods=["POST"])
@admin_usuarios_required
def desactivar(usuario_id):
    return _cambiar_estado(usuario_id, ua.desactivar_usuario, "desactivación")


@admin_usuarios_bp.route("/api/admin/usuarios/<int:usuario_id>/reactivar", methods=["POST"])
@admin_usuarios_required
def reactivar(usuario_id):
    return _cambiar_estado(usuario_id, ua.reactivar_usuario, "reactivación")


@admin_usuarios_bp.route("/api/admin/usuarios/<int:usuario_id>/rol", methods=["POST"])
@admin_usuarios_required
def cambiar_rol(usuario_id):
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        datos = {}
    try:
        usuario, anterior, cambiado = ua.cambiar_rol(g.usuario_sesion, usuario_id, datos.get("role"))
    except ua.ErrorUsuarios as error:
        db.session.rollback()
        return _responder_error(error)
    except Exception as error:
        return _fallo_interno("cambio de rol", error)
    return jsonify(
        {
            "usuario": ua.serializar_usuario(usuario),
            "rol_anterior": anterior,
            "cambiado": cambiado,
        }
    )


@admin_usuarios_bp.route("/api/admin/usuarios/<int:usuario_id>/restablecer-clave", methods=["POST"])
@admin_usuarios_required
def restablecer_clave(usuario_id):
    try:
        usuario, clave, vence = ua.restablecer_clave(g.usuario_sesion, usuario_id)
    except ua.ErrorUsuarios as error:
        db.session.rollback()
        return _responder_error(error)
    except Exception as error:
        return _fallo_interno("restablecimiento de clave", error)
    # La clave temporal viaja solo en esta respuesta (no-store): no va a la URL, a los logs ni a la auditoría.
    return jsonify(
        {
            "usuario": ua.serializar_usuario(usuario),
            "clave_temporal": clave,
            "clave_temporal_vence": vence.isoformat(),
        }
    )


@admin_usuarios_bp.route("/api/admin/usuarios/auditoria", methods=["GET"])
@admin_usuarios_required
def auditoria():
    return jsonify({"eventos": ua.auditoria_reciente()})
