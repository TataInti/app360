"""Administración de usuarios de App360 (C2): alta con clave temporal, activación y auditoría.

Reglas que cumple el servidor (la pantalla solo las refleja):
- Alta: usuario único sin distinguir mayúsculas, rol asignable y clave temporal de 16 caracteres
  generada con secrets. La clave se devuelve una sola vez: no se guarda en claro y no va a la
  auditoría ni a los logs. Queda obligación de cambio y vencimiento a las 72 h (D1).
- Desactivar: no se desactiva al último administrador activo (las filas de administradores se
  bloquean con FOR UPDATE), no se desactiva a uno mismo (D5), se suma token_version (corta los
  JWT) y se registra deactivated_at.
- Reactivar: limpia deactivated_at. No restablece la clave.
- Cada acción escribe su fila en user_audit_log dentro de la misma transacción: si la auditoría
  falla, la acción no se aplica.
"""

import re
import secrets
from datetime import timedelta, timezone

from flask import has_request_context, request
from sqlalchemy.exc import IntegrityError

import security
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog

# Roles con acceso total (admin_required). Son los únicos que cuentan como administradores.
ROLES_ADMINISTRACION = ("admin", "manager", "gerente")

# Roles que se ofrecen en el alta. «manager» no se asigna a altas nuevas (D12); si ya existe, se muestra.
ROLES_ASIGNABLES = (
    ("admin", "Administrador"),
    ("gerente", "Gerente"),
    ("sales", "Ventas"),
    ("purchases", "Compras"),
    ("hr", "RRHH"),
    ("operations", "Operaciones"),
    ("finance", "Finanzas"),
    ("caja", "Caja"),
    ("director", "Director"),
    ("direccion", "Dirección"),
)
ROLES_ASIGNABLES_CODIGOS = frozenset(codigo for codigo, _ in ROLES_ASIGNABLES)
ROL_NO_ASIGNABLE = "manager"
ETIQUETAS_ROL = {**dict(ROLES_ASIGNABLES), ROL_NO_ASIGNABLE: "Administrador (manager)"}

ESTADO_ACTIVO = "activo"
ESTADO_DESACTIVADO = "desactivado"
ESTADO_CAMBIAR_CLAVE = "cambiar_clave"
ESTADOS_FILTRO = ("todos", ESTADO_ACTIVO, ESTADO_DESACTIVADO, ESTADO_CAMBIAR_CLAVE)
ETIQUETAS_ESTADO = {
    ESTADO_ACTIVO: "Activo",
    ESTADO_DESACTIVADO: "Desactivado",
    ESTADO_CAMBIAR_CLAVE: "Debe cambiar la clave",
}

HORAS_CLAVE_TEMPORAL = 72
LONGITUD_CLAVE_TEMPORAL = 16
# Sin caracteres ambiguos: no hay i, l, o, I, O, 0 ni 1.
ALFABETO_CLAVE_TEMPORAL = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"

PATRON_USUARIO = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")

ACCIONES_AUDITADAS = {
    "user_created": "Alta de usuario",
    "user_deactivated": "Desactivación",
    "user_reactivated": "Reactivación",
}
# Solo estos datos de contexto entran al detalle de auditoría. Nunca claves, hashes ni tokens.
CAMPOS_DETALLE_PERMITIDOS = frozenset({"rol", "vence"})
LIMITE_AUDITORIA = 50
# Hora de la pantalla: Argentina (UTC-3, sin horario de verano).
ZONA_VISUAL = timezone(timedelta(hours=-3))


class ErrorUsuarios(Exception):
    """Regla de negocio incumplida. El mensaje va en español y se devuelve tal cual."""

    def __init__(self, codigo, mensaje, status, campos=None):
        super().__init__(codigo)
        self.codigo = codigo
        self.mensaje = mensaje
        self.status = status
        self.campos = campos or {}


def normalizar_usuario(valor):
    return valor.strip().lower() if isinstance(valor, str) else ""


def validar_alta(usuario, rol):
    """Errores por campo {campo: mensaje}. Vacío si el alta es válida."""
    errores = {}
    if not usuario:
        errores["username"] = "Ingresá un nombre de usuario."
    elif len(usuario) < 3:
        errores["username"] = "El usuario tiene que tener al menos 3 caracteres."
    elif len(usuario) > 80:
        errores["username"] = "El usuario no puede tener más de 80 caracteres."
    elif not PATRON_USUARIO.fullmatch(usuario):
        errores["username"] = (
            "Usá solo letras sin tilde, números, punto, guion y guion bajo. "
            "Empezá con una letra o un número."
        )
    if not rol:
        errores["role"] = "Elegí un rol."
    elif rol == ROL_NO_ASIGNABLE:
        errores["role"] = "Ese rol ya no se asigna a usuarios nuevos. Elegí «Administrador»."
    elif rol not in ROLES_ASIGNABLES_CODIGOS:
        errores["role"] = "Elegí un rol de la lista."
    return errores


def generar_clave_temporal():
    return "".join(secrets.choice(ALFABETO_CLAVE_TEMPORAL) for _ in range(LONGITUD_CLAVE_TEMPORAL))


def estado_usuario(usuario):
    if usuario.active is not True:
        return ESTADO_DESACTIVADO
    if usuario.must_change_password:
        return ESTADO_CAMBIAR_CLAVE
    return ESTADO_ACTIVO


def _con_zona(valor):
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


def _iso(valor):
    return None if valor is None else _con_zona(valor).isoformat()


def _texto_fecha(valor):
    return None if valor is None else _con_zona(valor).astimezone(ZONA_VISUAL).strftime("%d/%m/%Y %H:%M")


def serializar_usuario(usuario):
    estado = estado_usuario(usuario)
    return {
        "id": usuario.id,
        "username": usuario.username,
        "rol": usuario.role,
        "rol_nombre": ETIQUETAS_ROL.get(usuario.role, usuario.role),
        "estado": estado,
        "estado_nombre": ETIQUETAS_ESTADO[estado],
        "ultimo_acceso": _iso(usuario.last_login_at),
        "ultimo_acceso_texto": _texto_fecha(usuario.last_login_at) or "Nunca",
        "clave_temporal_vence": _iso(usuario.temp_password_expires_at) if usuario.must_change_password else None,
    }


def _detalle_seguro(detalle):
    """Solo entran los campos permitidos; los textos se acortan. Así no pasa ninguna clave ni hash."""
    if not detalle:
        return None
    limpio = {}
    for campo, valor in detalle.items():
        if campo not in CAMPOS_DETALLE_PERMITIDOS:
            continue
        if isinstance(valor, str):
            limpio[campo] = valor[:200]
        elif valor is None or isinstance(valor, (int, bool)):
            limpio[campo] = valor
    return limpio or None


def registrar_auditoria(actor, accion, target=None, detalle=None):
    """Escribe la acción en user_audit_log y emite un evento de seguridad.

    Hace flush, no commit: la fila se confirma junto con la acción que describe. Si la escritura
    falla, la excepción llega al llamador, que deshace la transacción entera.
    """
    if accion not in ACCIONES_AUDITADAS:
        raise ValueError(f"Acción de auditoría desconocida: {accion}")
    evento = UserAuditLog(
        created_at=security.ahora(),
        actor_user_id=getattr(actor, "id", None),
        actor_username=getattr(actor, "username", None),
        accion=accion,
        target_user_id=getattr(target, "id", None),
        target_username=getattr(target, "username", None),
        detalle=_detalle_seguro(detalle),
        ip=request.remote_addr if has_request_context() else None,
    )
    db.session.add(evento)
    db.session.flush()
    security.log_security_event(
        "USER_ADMIN_ACTION",
        f"Administración de usuarios: {accion}",
        user=evento.actor_username,
        ip=evento.ip,
        extra={"accion": accion, "objetivo": evento.target_username},
    )
    return evento


def _error_usuario_existente():
    return ErrorUsuarios(
        "USERNAME_TAKEN",
        "Ya existe un usuario con ese nombre. No distingue mayúsculas de minúsculas.",
        409,
        {"username": "Ese nombre ya está en uso."},
    )


def crear_usuario(actor, username, role):
    """Alta con clave temporal. Devuelve (usuario, clave, vence). La clave no se vuelve a mostrar."""
    nombre = normalizar_usuario(username)
    rol = role.strip() if isinstance(role, str) else ""
    errores = validar_alta(nombre, rol)
    if errores:
        raise ErrorUsuarios("DATOS_INVALIDOS", "Revisá los datos marcados.", 400, errores)
    if db.session.query(User.id).filter(db.func.lower(User.username) == nombre).first() is not None:
        raise _error_usuario_existente()

    clave = generar_clave_temporal()
    vence = security.ahora() + timedelta(hours=HORAS_CLAVE_TEMPORAL)
    usuario = User(username=nombre, role=rol, active=True)
    usuario.set_password(clave)
    usuario.must_change_password = True
    usuario.password_changed_at = None
    usuario.temp_password_expires_at = vence
    usuario.deactivated_at = None
    usuario.token_version = 0
    try:
        db.session.add(usuario)
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise _error_usuario_existente()
    registrar_auditoria(actor, "user_created", usuario, {"rol": rol, "vence": vence.isoformat()})
    db.session.commit()
    return usuario, clave, vence


def _administradores_activos_bloqueados():
    """Administradores activos con bloqueo de fila (FOR UPDATE): dos bajas simultáneas se serializan."""
    return (
        User.query.filter(User.role.in_(ROLES_ADMINISTRACION), User.active.is_(True))
        .order_by(User.id)
        .populate_existing()
        .with_for_update()
        .all()
    )


def desactivar_usuario(actor, usuario):
    administradores = _administradores_activos_bloqueados()
    if usuario.active is not True:
        raise ErrorUsuarios("YA_DESACTIVADO", "Ese usuario ya está desactivado.", 409)
    if usuario.role in ROLES_ADMINISTRACION and not any(a.id != usuario.id for a in administradores):
        raise ErrorUsuarios(
            "ULTIMO_ADMINISTRADOR",
            "No se puede: el sistema debe conservar al menos un administrador activo.",
            409,
        )
    if actor.id == usuario.id:
        raise ErrorUsuarios(
            "AUTODESACTIVACION",
            "No podés desactivar tu propia cuenta. Pedile a otro administrador que lo haga.",
            403,
        )
    usuario.active = False
    usuario.deactivated_at = security.ahora()
    usuario.token_version = (usuario.token_version or 0) + 1
    registrar_auditoria(actor, "user_deactivated", usuario, {"rol": usuario.role})
    db.session.commit()
    return usuario


def reactivar_usuario(actor, usuario):
    if usuario.active is True:
        raise ErrorUsuarios("YA_ACTIVO", "Ese usuario ya está activo.", 409)
    usuario.active = True
    usuario.deactivated_at = None
    registrar_auditoria(actor, "user_reactivated", usuario, {"rol": usuario.role})
    db.session.commit()
    return usuario


def listar_usuarios(q="", estado="todos"):
    consulta = User.query
    texto = q.strip().lower()[:80] if isinstance(q, str) else ""
    if texto:
        escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        consulta = consulta.filter(User.username.ilike(f"%{escapado}%", escape="\\"))
    if estado == ESTADO_ACTIVO:
        consulta = consulta.filter(User.active.is_(True), User.must_change_password.is_(False))
    elif estado == ESTADO_DESACTIVADO:
        consulta = consulta.filter(User.active.isnot(True))
    elif estado == ESTADO_CAMBIAR_CLAVE:
        consulta = consulta.filter(User.active.is_(True), User.must_change_password.is_(True))
    return consulta.order_by(User.username).all()


def auditoria_reciente(limite=LIMITE_AUDITORIA):
    filas = (
        UserAuditLog.query.order_by(UserAuditLog.created_at.desc(), UserAuditLog.id.desc())
        .limit(limite)
        .all()
    )
    return [
        {
            "fecha": _texto_fecha(fila.created_at),
            "fecha_iso": _iso(fila.created_at),
            "quien": fila.actor_username or "Sistema",
            "accion": ACCIONES_AUDITADAS.get(fila.accion, fila.accion),
            "a_quien": fila.target_username or "—",
        }
        for fila in filas
    ]
