"""Administración de usuarios de App360 (C2 y C3): alta, activación, rol, clave y auditoría.

Reglas que cumple el servidor (la pantalla solo las refleja):
- Alta: usuario único sin distinguir mayúsculas, rol asignable y clave temporal de 16 caracteres
  generada con secrets. La clave se devuelve una sola vez: no se guarda en claro y no va a la
  auditoría ni a los logs. Queda obligación de cambio y vencimiento a las 72 h (D1).
- Desactivar: no se desactiva al último administrador activo (las filas de administradores se
  bloquean con FOR UPDATE), no se desactiva a uno mismo (D5), se suma token_version (corta los
  JWT) y se registra deactivated_at.
- Reactivar: limpia deactivated_at y suma token_version: la sesión web y los JWT de antes de la
  baja quedan revocados. No restablece la clave.
- Cambiar rol (C3): solo roles asignables; nadie cambia su propio rol (D5); el último administrador
  activo no pasa a un rol sin administración (409, con el mismo bloqueo). No suma token_version:
  el rol se lee de la base en cada petición y rige desde la siguiente acción.
- Restablecer clave (C3): clave temporal nueva de 72 h, mostrada una vez. Suma token_version (corta
  las sesiones web y los JWT previos) y obliga a cambiarla al ingresar. No se hace a uno mismo ni a
  una cuenta desactivada.
- Cada acción escribe su fila en user_audit_log dentro de la misma transacción: si la auditoría
  falla, la acción no se aplica.
- C4: el login (services/acceso_login.py) registra login_ok y login_failed como mejor esfuerzo y
  aplica el bloqueo por cuenta. Desbloquear (user_unlocked) es atómico. El visor filtra y pagina la
  auditoría (consultar_auditoria).
"""

import re
import secrets
from datetime import date, datetime, timedelta, timezone

from functools import wraps

import sqlalchemy as sa
from flask import current_app, has_app_context, has_request_context, request
from sqlalchemy.exc import IntegrityError, OperationalError

import security
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from models.core.user_login_attempt import UserLoginAttempt
from services.acceso_login import ETIQUETAS_MOTIVO, esta_bloqueada

# Los tres roles siguen contando para conservar al último administrador activo.
ROLES_ADMINISTRACION = ("admin", "manager", "gerente")
ROLES_ADMINISTRADORES = ("admin", "manager")
CODIGO_JERARQUIA_INSUFICIENTE = "JERARQUIA_INSUFICIENTE"
MENSAJE_JERARQUIA_INSUFICIENTE = (
    "Esta cuenta la administra un administrador. Pedile a un administrador que haga este cambio."
)

# Roles que se ofrecen en el alta y en el cambio de rol. «manager» no se asigna (D12); si ya existe, se muestra.
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
MENSAJE_ROL_NO_ASIGNABLE = "Ese rol ya no se asigna. Elegí «Administrador» u otro rol de la lista."

ESTADO_ACTIVO = "activo"
ESTADO_DESACTIVADO = "desactivado"
ESTADO_CAMBIAR_CLAVE = "cambiar_clave"
ESTADO_CLAVE_VENCIDA = "clave_vencida"
ESTADO_BLOQUEADA = "bloqueada"
ESTADOS_FILTRO = (
    "todos",
    ESTADO_ACTIVO,
    ESTADO_DESACTIVADO,
    ESTADO_CAMBIAR_CLAVE,
    ESTADO_CLAVE_VENCIDA,
    ESTADO_BLOQUEADA,
)
ETIQUETAS_ESTADO = {
    ESTADO_ACTIVO: "Activo",
    ESTADO_DESACTIVADO: "Desactivado",
    ESTADO_CAMBIAR_CLAVE: "Debe cambiar la clave",
    ESTADO_CLAVE_VENCIDA: "Clave temporal vencida",
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
    "user_role_changed": "Cambio de rol",
    "user_password_reset": "Restablecimiento de clave",
    "user_unlocked": "Desbloqueo",
    "user_access_changed": "Acceso modificado",
    "login_ok": "Login correcto",
    "login_failed": "Login fallido",
}
ACCIONES_FILTRO = (("todas", "Todas las acciones"), *ACCIONES_AUDITADAS.items())
# Solo estos datos de contexto entran al detalle de auditoría. Nunca claves, hashes ni tokens.
CAMPOS_DETALLE_PERMITIDOS = frozenset(
    {
        "rol", "vence", "de", "a", "motivo", "canal", "intentos", "cambio_clave_pendiente",
        "modulo", "nivel_anterior", "nivel_nuevo",
    }
)
LIMITE_AUDITORIA = 50
PATRON_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PATRON_PAGINA = re.compile(r"[0-9]{1,12}")
ETIQUETAS_CANAL = {"web": "web", "api": "API"}
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


# Identificador estable y reservado para serializar TODAS las mutaciones de cuentas.
# Se pasa como bigint con signo a pg_advisory_xact_lock; no cambiarlo sin coordinar a los cortes C4/C5/C6.
BLOQUEO_ADVISORY_USUARIOS_KEY = 714_360_036_043
SQLSTATES_CONCURRENCIA = frozenset({"40P01", "40001"})
CODIGO_OPERACION_CONCURRENTE = "OPERACION_CONCURRENTE"
MENSAJE_OPERACION_CONCURRENTE = (
    "Otro administrador está modificando esta cuenta; reintentá en unos segundos"
)


def bloquear_mutaciones_usuarios():
    """Adquiere el lock transaccional común antes de cualquier FOR UPDATE de usuarios.

    PostgreSQL serializa con una constante bigint compartida por administración, cambio propio
    de clave y futuros flujos de recuperación/desbloqueo/MFA. En SQLite es un no-op. La base
    libera el lock al commit o rollback de esta transacción.
    """
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": BLOQUEO_ADVISORY_USUARIOS_KEY},
        )


def _sqlstate_operacional(error):
    original = getattr(error, "orig", None)
    return getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)


def es_error_concurrencia(error):
    """True solo para deadlock/serialization de PostgreSQL, no para cualquier OperationalError."""
    if not isinstance(error, OperationalError):
        return False
    return str(_sqlstate_operacional(error) or "").upper() in SQLSTATES_CONCURRENCIA


def reintentar_operacion_concurrente(func):
    """Reejecuta una vez la operación completa ante deadlock/serialización.

    Rollback libera primero locks y escrituras parciales. Si el segundo intento falla, el caller
    recibe OPERACION_CONCURRENTE (409), nunca el texto/parametría interna del error SQL.
    """
    @wraps(func)
    def envuelta(*args, **kwargs):
        for intento in range(2):
            try:
                return func(*args, **kwargs)
            except OperationalError as error:
                db.session.rollback()
                if not es_error_concurrencia(error):
                    raise
                if has_app_context():
                    current_app.logger.warning(
                        "Conflicto concurrente en administración de usuarios: exception=%s sqlstate=%s intento=%s",
                        type(error).__name__,
                        _sqlstate_operacional(error) or "n/a",
                        intento + 1,
                    )
                if intento == 1:
                    raise ErrorUsuarios(
                        CODIGO_OPERACION_CONCURRENTE,
                        MENSAJE_OPERACION_CONCURRENTE,
                        409,
                    ) from None
        raise AssertionError("bucle de reintentos agotado")

    return envuelta


def puede_administrar(actor, objetivo, rol_nuevo=None):
    """Autoriza la jerarquía común a toda acción administrativa sobre cuentas ajenas.

    admin y el alias legacy manager administran cualquier cuenta. gerente solo administra
    cuentas que no sean admin/manager y no puede asignar esos roles. `objetivo=None` permite
    validar altas. La función no reemplaza reglas propias (autocambio, último admin, estado)
    ni la guardia de autenticación; centraliza únicamente la jerarquía para reutilizarla en
    cambios futuros de recuperación, desbloqueo y MFA. Devuelve (ok, código, mensaje).
    """
    rol_actor = getattr(actor, "role", None)
    if rol_actor in ROLES_ADMINISTRADORES:
        return True, None, None
    if rol_actor == "gerente":
        rol_objetivo = getattr(objetivo, "role", None)
        if rol_objetivo in ROLES_ADMINISTRADORES or rol_nuevo in ROLES_ADMINISTRADORES:
            return False, CODIGO_JERARQUIA_INSUFICIENTE, MENSAJE_JERARQUIA_INSUFICIENTE
        return True, None, None
    return False, CODIGO_JERARQUIA_INSUFICIENTE, MENSAJE_JERARQUIA_INSUFICIENTE


def _exigir_jerarquia(actor, objetivo, rol_nuevo=None):
    ok, codigo, mensaje = puede_administrar(actor, objetivo, rol_nuevo)
    if not ok:
        raise ErrorUsuarios(codigo, mensaje, 403)


def roles_asignables_para(actor):
    """Lista de roles que el actor puede asignar, compartida por la API y la pantalla."""
    if getattr(actor, "role", None) == "gerente":
        return [(codigo, nombre) for codigo, nombre in ROLES_ASIGNABLES if codigo not in ROLES_ADMINISTRADORES]
    return list(ROLES_ASIGNABLES)


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
        return ESTADO_CLAVE_VENCIDA if security.clave_temporal_vencida(usuario) else ESTADO_CAMBIAR_CLAVE
    return ESTADO_ACTIVO


def _con_zona(valor):
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


def _iso(valor):
    return None if valor is None else _con_zona(valor).isoformat()


def _texto_fecha(valor):
    return None if valor is None else _con_zona(valor).astimezone(ZONA_VISUAL).strftime("%d/%m/%Y %H:%M")


def _texto_corto(valor):
    """Vencimiento de la clave temporal para la lista: dd/mm hh:mm, hora de Argentina."""
    return None if valor is None else _con_zona(valor).astimezone(ZONA_VISUAL).strftime("%d/%m %H:%M")


def _texto_hora(valor):
    """Hora de Argentina (hh:mm) para «Bloqueada hasta»."""
    return None if valor is None else _con_zona(valor).astimezone(ZONA_VISUAL).strftime("%H:%M")


def _bloqueos_ip_vigentes(usuario_id, ahora=None):
    """Cantidad de IPs con bloqueo por par activo y su vencimiento más lejano."""
    ahora = ahora or security.ahora()
    cantidad, hasta = (
        db.session.query(sa.func.count(UserLoginAttempt.ip), sa.func.max(UserLoginAttempt.locked_until))
        .filter(UserLoginAttempt.user_id == usuario_id, UserLoginAttempt.locked_until > ahora)
        .one()
    )
    return int(cantidad or 0), _con_zona(hasta) if hasta is not None else None


def serializar_usuario(usuario):
    ahora = security.ahora()
    estado = estado_usuario(usuario)
    global_bloqueada = esta_bloqueada(usuario, ahora)
    bloqueadas_ips, bloqueo_ip_hasta = _bloqueos_ip_vigentes(usuario.id, ahora)
    bloqueada = global_bloqueada or bloqueadas_ips > 0
    bloqueo_hasta = usuario.locked_until if global_bloqueada else bloqueo_ip_hasta
    vence = usuario.temp_password_expires_at if usuario.must_change_password else None
    return {
        "id": usuario.id,
        "username": usuario.username,
        "rol": usuario.role,
        "rol_nombre": ETIQUETAS_ROL.get(usuario.role, usuario.role),
        "estado": estado,
        "estado_nombre": ETIQUETAS_ESTADO[estado],
        "ultimo_acceso": _iso(usuario.last_login_at),
        "ultimo_acceso_texto": _texto_fecha(usuario.last_login_at) or "Nunca",
        "clave_temporal_vence": _iso(vence),
        "clave_temporal_vence_texto": _texto_corto(vence),
        "bloqueada": bloqueada,
        "bloqueo_global": global_bloqueada,
        "bloqueadas_ips": bloqueadas_ips,
        "bloqueada_hasta": _iso(bloqueo_hasta) if bloqueada else None,
        "bloqueada_hasta_texto": _texto_hora(bloqueo_hasta) if bloqueada else None,
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
    falla, la excepción llega al llamador, que deshace la transacción entera. Sin actor (scripts),
    la acción queda como «Sistema».
    """
    if accion not in ACCIONES_AUDITADAS:
        raise ValueError(f"Acción de auditoría desconocida: {accion}")
    ip = request.remote_addr if has_request_context() else None
    ip = ip[:45] if isinstance(ip, str) else None
    evento = UserAuditLog(
        created_at=security.ahora(),
        actor_user_id=getattr(actor, "id", None),
        actor_username=getattr(actor, "username", None),
        accion=accion,
        target_user_id=getattr(target, "id", None),
        target_username=getattr(target, "username", None),
        detalle=_detalle_seguro(detalle),
        ip=ip,
    )
    db.session.add(evento)
    db.session.flush()
    security.log_security_event(
        "USER_ADMIN_ACTION",
        f"Administración de usuarios: {accion}",
        user=evento.actor_username or "Sistema",
        ip=evento.ip,
        extra={"accion": accion, "objetivo": evento.target_username},
    )
    return evento


def guardar_accesos_usuario(actor, usuario, permisos):
    """Guarda las excepciones de módulos de un usuario y audita cada módulo realmente modificado.

    Los permisos individuales se suman a los del rol; «none» retira solo la excepción individual.
    Las filas de auditoría se escriben en la misma transacción que el cambio: el llamador hace
    commit una sola vez, y si algo falla deshace todo. Devuelve la cantidad de módulos modificados.
    """
    from models.core.user_permission import UserModulePermission

    ok, codigo, mensaje = puede_administrar(actor, usuario)
    if not ok:
        raise ErrorUsuarios(codigo, mensaje, 403)
    modulos_rol = security.ACCESS_MAP.get(usuario.role, [])
    todo_el_rol = "all" in modulos_rol
    cambios = 0
    for modulo, nivel in permisos.items():
        if modulo not in security.MANAGED_MODULES or nivel not in ("view", "edit", "none"):
            continue
        if todo_el_rol or modulo in modulos_rol:
            continue
        existente = UserModulePermission.query.filter_by(user_id=usuario.id, module=modulo).first()
        anterior = existente.access_level if existente else "none"
        if anterior == nivel:
            continue
        if nivel == "none":
            db.session.delete(existente)
        elif existente:
            existente.access_level = nivel
        else:
            db.session.add(UserModulePermission(user_id=usuario.id, module=modulo, access_level=nivel))
        registrar_auditoria(
            actor,
            "user_access_changed",
            usuario,
            {"modulo": modulo, "nivel_anterior": anterior, "nivel_nuevo": nivel},
        )
        cambios += 1
    return cambios


def _error_usuario_existente():
    return ErrorUsuarios(
        "USERNAME_TAKEN",
        "Ese nombre de usuario ya existe. No distingue mayúsculas de minúsculas.",
        409,
        {"username": "Ese nombre ya está en uso."},
    )


@reintentar_operacion_concurrente
def crear_usuario(actor, username, role):
    """Alta con clave temporal. Devuelve (usuario, clave, vence). La clave no se vuelve a mostrar."""
    bloquear_mutaciones_usuarios()
    nombre = normalizar_usuario(username)
    rol = role.strip() if isinstance(role, str) else ""
    _exigir_jerarquia(actor, None, rol)
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
    """Administradores activos con bloqueo de fila (FOR UPDATE): dos cambios simultáneos se serializan."""
    return (
        User.query.filter(User.role.in_(ROLES_ADMINISTRACION), User.active.is_(True))
        .order_by(User.id)
        .populate_existing()
        .with_for_update()
        .all()
    )


def _id_usuario(objetivo):
    return getattr(objetivo, "id", objetivo)


def _usuario_bloqueado(usuario_id):
    """Lee el estado vigente de una cuenta y serializa sus escrituras PostgreSQL."""
    return (
        User.query.filter_by(id=usuario_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


@reintentar_operacion_concurrente
def desactivar_usuario(actor, usuario):
    bloquear_mutaciones_usuarios()
    administradores = _administradores_activos_bloqueados()
    usuario = _usuario_bloqueado(_id_usuario(usuario))
    if usuario is None:
        raise ErrorUsuarios("USUARIO_NO_ENCONTRADO", "No encontramos ese usuario.", 404)
    _exigir_jerarquia(actor, usuario)
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


@reintentar_operacion_concurrente
def reactivar_usuario(actor, usuario):
    bloquear_mutaciones_usuarios()
    usuario = _usuario_bloqueado(_id_usuario(usuario))
    if usuario is None:
        raise ErrorUsuarios("USUARIO_NO_ENCONTRADO", "No encontramos ese usuario.", 404)
    _exigir_jerarquia(actor, usuario)
    if usuario.active is True:
        raise ErrorUsuarios("YA_ACTIVO", "Ese usuario ya está activo.", 409)
    usuario.active = True
    usuario.deactivated_at = None
    # Suma la versión de token: la huella de sesión y los JWT de antes de la baja no vuelven a valer.
    usuario.token_version = (usuario.token_version or 0) + 1
    registrar_auditoria(actor, "user_reactivated", usuario, {"rol": usuario.role})
    db.session.commit()
    return usuario


@reintentar_operacion_concurrente
def cambiar_rol(actor, usuario_id, nuevo_rol):
    """Cambia el rol de una cuenta. Devuelve (usuario, rol_anterior, cambiado).

    Reglas: solo roles asignables; nadie cambia su propio rol; el último administrador activo no
    pasa a un rol sin administración. Si el rol no cambia, no escribe nada (ni auditoría ni versión).
    Los administradores se bloquean antes de leer la cuenta objetivo: dos cambios simultáneos se
    serializan y el segundo ve el estado que dejó el primero. No suma token_version: el rol se lee
    de la base en cada petición.
    """
    bloquear_mutaciones_usuarios()
    rol = nuevo_rol.strip() if isinstance(nuevo_rol, str) else ""
    administradores = _administradores_activos_bloqueados()
    usuario = _usuario_bloqueado(usuario_id)
    if usuario is None:
        raise ErrorUsuarios("USUARIO_NO_ENCONTRADO", "No encontramos ese usuario.", 404)
    if actor.id == usuario.id:
        raise ErrorUsuarios(
            "AUTOCAMBIO_ROL",
            "No podés cambiar tu propio rol. Pedile a otro administrador que lo haga.",
            403,
        )
    _exigir_jerarquia(actor, usuario, rol)
    anterior = usuario.role
    if rol == anterior:
        db.session.rollback()
        return usuario, anterior, False
    if not rol:
        raise ErrorUsuarios("DATOS_INVALIDOS", "Revisá los datos marcados.", 400, {"role": "Elegí un rol."})
    if rol not in ROLES_ASIGNABLES_CODIGOS:
        mensaje = MENSAJE_ROL_NO_ASIGNABLE if rol == ROL_NO_ASIGNABLE else "Elegí un rol de la lista."
        raise ErrorUsuarios("ROL_INVALIDO", "Ese rol no está disponible para asignar.", 400, {"role": mensaje})
    if usuario.active is True and anterior in ROLES_ADMINISTRACION and rol not in ROLES_ADMINISTRACION:
        if not any(a.id != usuario.id for a in administradores):
            raise ErrorUsuarios(
                "ULTIMO_ADMINISTRADOR",
                "No se puede: el sistema debe conservar al menos un administrador activo.",
                409,
            )
    usuario.role = rol
    registrar_auditoria(actor, "user_role_changed", usuario, {"de": anterior, "a": rol})
    db.session.commit()
    return usuario, anterior, True


@reintentar_operacion_concurrente
def restablecer_clave(actor, usuario_id):
    """Genera una clave temporal nueva para otra cuenta activa. Devuelve (usuario, clave, vence).

    La clave viaja solo en la respuesta de esta acción. Suma token_version: las sesiones web y los
    JWT previos dejan de valer, y la clave anterior deja de servir. Obliga a cambiarla al ingresar.
    """
    # Primero el lock advisory global; después FOR UPDATE y lectura del estado vigente.
    bloquear_mutaciones_usuarios()
    usuario = _usuario_bloqueado(usuario_id)
    if usuario is None:
        raise ErrorUsuarios("USUARIO_NO_ENCONTRADO", "No encontramos ese usuario.", 404)
    _exigir_jerarquia(actor, usuario)
    if actor.id == usuario.id:
        raise ErrorUsuarios("AUTORESET", "Para cambiar tu clave usá «Cambiar mi clave» en tu menú.", 403)
    if usuario.active is not True:
        raise ErrorUsuarios(
            "USUARIO_INACTIVO",
            "Ese usuario está desactivado. Reactivalo primero y después restablecé su clave.",
            409,
        )
    clave = generar_clave_temporal()
    ahora = security.ahora()
    vence = ahora + timedelta(hours=HORAS_CLAVE_TEMPORAL)
    usuario.set_password(clave)
    usuario.password_changed_at = ahora
    usuario.must_change_password = True
    usuario.temp_password_expires_at = vence
    usuario.token_version = (usuario.token_version or 0) + 1
    registrar_auditoria(actor, "user_password_reset", usuario, {"vence": vence.isoformat()})
    db.session.commit()
    return usuario, clave, vence


@reintentar_operacion_concurrente
def desbloquear_usuario(actor, usuario):
    """Levanta el bloqueo por intentos fallidos (A3): borra contador, ventana y fin del bloqueo.

    Se serializa con el resto de mutaciones de cuentas (bloquear_mutaciones_usuarios) y respeta la
    jerarquía puede_administrar: un gerente no desbloquea cuentas admin ni manager. Bloquea la fila
    antes de leer el estado. Si la cuenta no está bloqueada, responde 409 NO_BLOQUEADA y no escribe nada.
    """
    bloquear_mutaciones_usuarios()
    fila = _usuario_bloqueado(_id_usuario(usuario))
    if fila is None:
        raise ErrorUsuarios("USUARIO_NO_ENCONTRADO", "No encontramos ese usuario.", 404)
    _exigir_jerarquia(actor, fila)
    ahora = security.ahora()
    cantidad_pares, _ = _bloqueos_ip_vigentes(fila.id, ahora)
    if not esta_bloqueada(fila, ahora) and cantidad_pares == 0:
        raise ErrorUsuarios("NO_BLOQUEADA", "Esa cuenta no está bloqueada.", 409)
    intentos = fila.failed_login_count or 0
    fila.failed_login_count = 0
    fila.failed_login_window_start = None
    fila.locked_until = None
    db.session.query(UserLoginAttempt).filter_by(user_id=fila.id).delete(synchronize_session=False)
    registrar_auditoria(actor, "user_unlocked", fila, {"intentos": intentos})
    db.session.commit()
    return fila


def _tabla_auditoria_existe():
    return sa.inspect(db.session.connection()).has_table(UserAuditLog.__tablename__)


def activar_cuenta_existente(usuario):
    """Pone active=True sobre una cuenta que ya existe (scripts de alta). Devuelve True si cambió.

    Solo una reactivación suma token_version (corta los JWT y las sesiones de antes de la baja) y,
    si la tabla de auditoría existe, se registra. Una cuenta ya activa no cambia.
    """
    bloquear_mutaciones_usuarios()
    if usuario.active is True:
        return False
    usuario.active = True
    usuario.deactivated_at = None
    usuario.token_version = (usuario.token_version or 0) + 1
    if _tabla_auditoria_existe():
        registrar_auditoria(None, "user_reactivated", usuario, {"rol": usuario.role})
    return True


def listar_usuarios(q="", estado="todos"):
    consulta = User.query
    texto = q.strip().lower()[:80] if isinstance(q, str) else ""
    if texto:
        escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        consulta = consulta.filter(User.username.ilike(f"%{escapado}%", escape="\\"))
    usuarios = consulta.order_by(User.username).all()
    if estado in ESTADOS_FILTRO and estado != "todos":
        # El estado depende del reloj (clave temporal vencida y bloqueo): se filtra con la misma regla que la columna.
        if estado == ESTADO_BLOQUEADA:
            ahora = security.ahora()
            usuarios = [
                usuario
                for usuario in usuarios
                if esta_bloqueada(usuario, ahora) or _bloqueos_ip_vigentes(usuario.id, ahora)[0] > 0
            ]
        else:
            usuarios = [usuario for usuario in usuarios if estado_usuario(usuario) == estado]
    return usuarios


def _fecha_o_error(valor, campo, errores):
    """Fecha AAAA-MM-DD entre 2000 y 2999. Vacía → None. Inválida → anota el error y devuelve None."""
    if valor in (None, ""):
        return None
    if isinstance(valor, str) and PATRON_FECHA.fullmatch(valor):
        try:
            fecha = date.fromisoformat(valor)
        except ValueError:
            fecha = None
        if fecha is not None and 2000 <= fecha.year <= 2999:
            return fecha
    errores[campo] = "Usá una fecha válida (día, mes y año)."
    return None


def _pagina_o_error(valor, errores):
    if valor in (None, ""):
        return 1
    if isinstance(valor, str) and PATRON_PAGINA.fullmatch(valor) and int(valor) >= 1:
        return int(valor)
    errores["pagina"] = "La página tiene que ser un número mayor que cero."
    return 1


def _inicio_local(dia):
    """Medianoche de Argentina de ese día, en UTC."""
    return datetime(dia.year, dia.month, dia.day, tzinfo=ZONA_VISUAL).astimezone(timezone.utc)


def _rol(codigo):
    return ETIQUETAS_ROL.get(codigo, codigo or "—")


def _texto_vencimiento(iso):
    if not iso:
        return ""
    try:
        vence = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"Clave temporal válida hasta {_texto_fecha(vence)}"


ETIQUETAS_NIVEL_ACCESO = {"none": "Sin acceso", "view": "Ver", "edit": "Editar"}


def _texto_detalle(fila):
    """Detalle legible en español, sin JSON crudo. Solo usa los campos permitidos."""
    detalle = fila.detalle if isinstance(fila.detalle, dict) else {}
    accion = fila.accion
    if accion == "user_role_changed":
        return f"Rol: {_rol(detalle.get('de'))} → {_rol(detalle.get('a'))}"
    if accion in ("user_created", "user_deactivated", "user_reactivated"):
        return f"Rol: {_rol(detalle.get('rol'))}" if detalle.get("rol") else ""
    if accion == "user_access_changed":
        modulo = security.MANAGED_MODULES.get(detalle.get("modulo"), detalle.get("modulo") or "—")
        anterior = ETIQUETAS_NIVEL_ACCESO.get(detalle.get("nivel_anterior"), "—")
        nuevo = ETIQUETAS_NIVEL_ACCESO.get(detalle.get("nivel_nuevo"), "—")
        return f"{modulo}: {anterior} → {nuevo}"
    if accion == "user_password_reset":
        return _texto_vencimiento(detalle.get("vence"))
    if accion == "user_unlocked":
        return f"Intentos fallidos antes del desbloqueo: {detalle.get('intentos', 0)}"
    if accion == "login_ok":
        texto = f"Canal: {ETIQUETAS_CANAL.get(detalle.get('canal'), '—')}"
        return texto + ". Debe cambiar la clave" if detalle.get("cambio_clave_pendiente") else texto
    if accion == "login_failed":
        veces = fila.repeticiones or 1
        palabra = "intento" if veces == 1 else "intentos"
        motivo = ETIQUETAS_MOTIVO.get(detalle.get("motivo"), "—")
        canal = ETIQUETAS_CANAL.get(detalle.get("canal"), "—")
        return f"Motivo: {motivo}, {veces} {palabra} · Canal: {canal}"
    return ""


def _evento(fila):
    return {
        "id": fila.id,
        "fecha": _texto_fecha(fila.created_at),
        "fecha_iso": _iso(fila.created_at),
        "quien": fila.actor_username or "Sistema",
        "accion": ACCIONES_AUDITADAS.get(fila.accion, fila.accion),
        "accion_codigo": fila.accion,
        "a_quien": fila.target_username or "—",
        "detalle": _texto_detalle(fila),
        "ip": fila.ip or "—",
        "repeticiones": fila.repeticiones or 1,
    }


def consultar_auditoria(q="", accion="todas", desde=None, hasta=None, pagina=None):
    """Eventos de auditoría, del más nuevo al más viejo, de 50 en 50 (A4).

    Filtros: usuario (actor o destino, sin distinguir mayúsculas), acción y fechas (días de Argentina,
    incluidos). Página fuera de rango → lista vacía. Parámetros inválidos → ErrorUsuarios 400.
    """
    errores = {}
    texto = q.strip().lower()[:80] if isinstance(q, str) else ""
    codigo = accion if accion not in (None, "") else "todas"
    if codigo != "todas" and codigo not in ACCIONES_AUDITADAS:
        errores["accion"] = "Elegí una acción de la lista."
    dia_desde = _fecha_o_error(desde, "desde", errores)
    dia_hasta = _fecha_o_error(hasta, "hasta", errores)
    if dia_desde and dia_hasta and dia_desde > dia_hasta:
        errores["hasta"] = "La fecha hasta no puede ser anterior a la fecha desde."
    numero = _pagina_o_error(pagina, errores)
    if errores:
        raise ErrorUsuarios("PARAMETROS_INVALIDOS", "Revisá los filtros marcados.", 400, errores)

    consulta = UserAuditLog.query
    if texto:
        escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        patron = f"%{escapado}%"
        consulta = consulta.filter(
            sa.or_(
                UserAuditLog.actor_username.ilike(patron, escape="\\"),
                UserAuditLog.target_username.ilike(patron, escape="\\"),
            )
        )
    if codigo != "todas":
        consulta = consulta.filter(UserAuditLog.accion == codigo)
    if dia_desde:
        consulta = consulta.filter(UserAuditLog.created_at >= _inicio_local(dia_desde))
    if dia_hasta:
        consulta = consulta.filter(UserAuditLog.created_at < _inicio_local(dia_hasta + timedelta(days=1)))
    total = consulta.count()
    filas = (
        consulta.order_by(UserAuditLog.created_at.desc(), UserAuditLog.id.desc())
        .offset((numero - 1) * LIMITE_AUDITORIA)
        .limit(LIMITE_AUDITORIA)
        .all()
    )
    return {
        "eventos": [_evento(fila) for fila in filas],
        "total": total,
        "pagina": numero,
        "por_pagina": LIMITE_AUDITORIA,
        "paginas": max(1, -(-total // LIMITE_AUDITORIA)),
    }
