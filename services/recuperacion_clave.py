"""Recuperación de clave con enlace de un solo uso (C5 de administración de usuarios).

Emitir (administrador o gerente, otra cuenta activa): el enlace se muestra una vez y solo se guarda su
SHA-256. Efecto D2: la clave anterior se reemplaza por un valor aleatorio que nadie conoce y se suma
token_version; las sesiones y los JWT previos dejan de valer y la cuenta queda sin clave utilizable hasta
el canje o un restablecimiento. Un enlace nuevo revoca los vigentes del mismo usuario.

Canje (público, con el token como credencial): el UPDATE condicional marca used_at en la misma
transacción que cambia la clave; dos canjes simultáneos del mismo token, solo uno gana. Un token válido
con una clave que no cumple la política no se consume. Los canjes fallidos se agrupan en
user_audit_log (recovery_failed) sin el token ni la clave.
"""

import hashlib
import secrets
from datetime import timedelta

from flask import current_app, has_request_context, request
from werkzeug.security import check_password_hash

import security
from models import db
from models.core.user import User
from models.core.user_recovery_token import UserRecoveryToken
from services import usuarios_admin as ua
from services.acceso_login import _escribir_evento
from services.politica_clave import errores_clave_nueva

TTL_MINIMO = 5
TTL_MAXIMO = 1440
TTL_DEFAULT = 30
EMISIONES_MAXIMAS = 5
VENTANA_EMISIONES = timedelta(minutes=10)
LONGITUD_TOKEN_MINIMA = 32
LONGITUD_TOKEN_MAXIMA = 128
ALFABETO_TOKEN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
RUTA_RECUPERACION = "/recuperar-clave"
MENSAJE_INVALIDO = "No pudimos usar este enlace. Pedile a tu administrador que te genere uno nuevo."
ACCION_FALLO = "recovery_failed"


def hash_del_enlace(texto):
    """SHA-256 del token en hexadecimal (64 caracteres). Es lo único que se guarda."""
    return hashlib.sha256(texto.encode("utf-8", "replace")).hexdigest()


def base_publica():
    """Dirección pública para el enlace: APP_PUBLIC_URL, o SERVER_NAME con el esquema preferido.

    Nunca usa cabeceras de la petición (Host, X-Forwarded-Host). Sin configuración devuelve None y la
    emisión se rechaza antes de tocar la base.
    """
    configurada = current_app.config.get("APP_PUBLIC_URL")
    if isinstance(configurada, str) and configurada.startswith(("https://", "http://")):
        return configurada.rstrip("/")
    servidor = current_app.config.get("SERVER_NAME")
    if servidor:
        esquema = current_app.config.get("PREFERRED_URL_SCHEME") or "https"
        return f"{esquema}://{servidor}"
    return None


def ttl_valido(valor):
    """Minutos de vigencia entre 5 y 1440. Acepta entero o texto de dígitos. Otro valor → None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, str) and 0 < len(valor.strip()) <= 6 and valor.strip().isdigit():
        valor = int(valor.strip())
    if isinstance(valor, int) and TTL_MINIMO <= valor <= TTL_MAXIMO:
        return valor
    return None


def _usuario_bloqueado(usuario_id):
    """Fila del usuario con bloqueo: dos emisiones o revocaciones sobre la misma cuenta se serializan."""
    return User.query.filter_by(id=usuario_id).with_for_update().populate_existing().one_or_none()


def _emisiones_recientes(actor, ahora):
    return UserRecoveryToken.query.filter(
        UserRecoveryToken.created_by_user_id == actor.id,
        UserRecoveryToken.created_at > ahora - VENTANA_EMISIONES,
    ).count()


def _vigente(fila, ahora):
    return (
        fila.used_at is None
        and fila.revoked_at is None
        and ua._con_zona(fila.expires_at) > ahora
    )


def emitir(actor, usuario_id, ttl):
    """Emite un enlace para otra cuenta activa. Devuelve (usuario, datos) con datos del enlace.

    datos: enlace (URL con el token en el fragmento), vence (ISO), ttl (minutos) y recuperacion_id.
    El token no se guarda ni se audita: solo viaja en esta respuesta.
    """
    base = base_publica()
    if base is None:
        raise ua.ErrorUsuarios(
            "SIN_DIRECCION_PUBLICA",
            "Falta configurar la dirección pública de la app (APP_PUBLIC_URL). No se generó ningún enlace.",
            409,
        )
    minutos = ttl_valido(ttl)
    if minutos is None:
        raise ua.ErrorUsuarios(
            "DATOS_INVALIDOS",
            "Revisá los datos marcados.",
            400,
            {"ttl": f"Elegí una vigencia entre {TTL_MINIMO} y {TTL_MAXIMO} minutos."},
        )
    usuario = _usuario_bloqueado(usuario_id)
    if usuario is None:
        raise ua.ErrorUsuarios("USUARIO_NO_ENCONTRADO", "No encontramos ese usuario.", 404)
    if actor.id == usuario.id:
        raise ua.ErrorUsuarios(
            "AUTOOBJETIVO",
            "No generás enlaces para tu propia cuenta. Para cambiar tu clave usá «Cambiar mi clave» en tu menú.",
            403,
        )
    if usuario.active is not True:
        raise ua.ErrorUsuarios(
            "USUARIO_INACTIVO",
            "Ese usuario está desactivado. Reactivalo primero para generarle un enlace.",
            409,
        )
    ahora = security.ahora()
    if _emisiones_recientes(actor, ahora) >= EMISIONES_MAXIMAS:
        raise ua.ErrorUsuarios(
            "LIMITE_EMISIONES",
            "Generaste varios enlaces en los últimos 10 minutos. Esperá un rato antes de generar otro.",
            429,
        )

    reemplazados = ua.revocar_enlaces_vigentes(usuario, ahora)
    token = secrets.token_urlsafe(32)
    vence = ahora + timedelta(minutes=minutos)
    fila = UserRecoveryToken(
        user_id=usuario.id,
        token_hash=hash_del_enlace(token),
        created_at=ahora,
        expires_at=vence,
        created_by_user_id=actor.id,
        created_by_username=actor.username,
        ip=request.remote_addr if has_request_context() else None,
    )
    db.session.add(fila)
    db.session.flush()
    # Efecto D2: la clave anterior deja de servir. La clave aleatoria se descarta aquí mismo.
    usuario.set_password(secrets.token_urlsafe(48))
    usuario.password_changed_at = ahora
    usuario.token_version = (usuario.token_version or 0) + 1
    ua.registrar_auditoria(
        actor,
        "user_recovery_issued",
        usuario,
        {"ttl": minutos, "recuperacion_id": fila.id, "reemplazados": reemplazados},
    )
    datos = {
        "enlace": f"{base}{RUTA_RECUPERACION}#{token}",
        "vence": ua._con_zona(vence).isoformat(),
        "ttl": minutos,
        "recuperacion_id": fila.id,
    }
    db.session.commit()
    return usuario, datos


def revocar(actor, usuario_id, recuperacion_id):
    """Revoca el enlace vigente. Id inexistente o no vigente → 409 RECOVERY_NOT_ACTIVE."""
    ahora = security.ahora()
    fila = (
        UserRecoveryToken.query.filter_by(id=recuperacion_id, user_id=usuario_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if fila is None or not _vigente(fila, ahora):
        db.session.rollback()
        raise ua.ErrorUsuarios(
            "RECOVERY_NOT_ACTIVE",
            "Ese enlace ya no está vigente. No se cambió nada.",
            409,
        )
    usuario = db.session.get(User, usuario_id, populate_existing=True)
    fila.revoked_at = ahora
    ua.registrar_auditoria(actor, "user_recovery_revoked", usuario, {"recuperacion_id": fila.id})
    db.session.commit()
    return usuario


def _forma_valida(texto):
    """Largo entre 32 y 128 y solo caracteres URL-safe. Sin regex: recorrido lineal."""
    return LONGITUD_TOKEN_MINIMA <= len(texto) <= LONGITUD_TOKEN_MAXIMA and all(
        caracter in ALFABETO_TOKEN for caracter in texto
    )


def _motivo_invalido(forma_ok, fila, usuario, ahora):
    if not forma_ok:
        return "formato"
    if fila is None:
        return "inexistente"
    if fila.revoked_at is not None:
        return "revocado"
    if fila.used_at is not None:
        return "usado"
    if ua._con_zona(fila.expires_at) <= ahora:
        return "vencido"
    if usuario is None or usuario.active is not True:
        return "usuario_inactivo"
    return None


def _verificacion_equivalente(clave):
    """Trabajo de hash igual al del canje correcto, para que los rechazos no tarden menos."""
    check_password_hash(security.HASH_FICTICIO, clave)


def _registrar_fallo(motivo, ip, ahora, usuario_id=None, nombre=None):
    """Fallo de canje agrupado como en C4: IP, motivo, cuenta (si se conoce) y minuto. Sin token."""
    minuto = ahora.replace(second=0, microsecond=0)
    agrupacion = f"recuperacion|{ip or '-'}|{motivo}|{usuario_id or '-'}|{minuto:%Y%m%d%H%M}"
    valores = {
        "created_at": ahora,
        "actor_user_id": None,
        "actor_username": None,
        "accion": ACCION_FALLO,
        "target_user_id": usuario_id,
        "target_username": nombre,
        "detalle": {"motivo": motivo},
        "ip": ip,
        "clave_agrupacion": agrupacion,
        "repeticiones": 1,
    }
    try:
        with db.session.begin_nested():
            _escribir_evento(valores)
    except Exception:
        security.log_security_event(
            "AUDITORIA_RECUPERACION_NO_REGISTRADA",
            "No se pudo registrar un canje fallido de recuperación; la respuesta no cambia",
            ip=ip,
            extra={"motivo": motivo},
        )
    db.session.commit()


def _consumir_y_cambiar(fila_id, usuario_id, clave, ahora, ip):
    try:
        consumidos = UserRecoveryToken.query.filter(
            UserRecoveryToken.id == fila_id,
            UserRecoveryToken.used_at.is_(None),
            UserRecoveryToken.revoked_at.is_(None),
            UserRecoveryToken.expires_at > ahora,
        ).update({UserRecoveryToken.used_at: ahora}, synchronize_session=False)
        if consumidos != 1:
            # Otro canje o una revocación llegó primero: mismo rechazo genérico.
            db.session.rollback()
            _registrar_fallo("ya_consumido", ip, ahora, usuario_id)
            return "invalido", "ya_consumido"
        usuario = User.query.filter_by(id=usuario_id).with_for_update().populate_existing().one()
        if usuario.active is not True:
            nombre = usuario.username
            db.session.rollback()
            _registrar_fallo("usuario_inactivo", ip, ahora, usuario_id, nombre)
            return "invalido", "usuario_inactivo"
        usuario.set_password(clave)
        usuario.password_changed_at = ahora
        usuario.must_change_password = False
        usuario.temp_password_expires_at = None
        usuario.failed_login_count = 0
        usuario.failed_login_window_start = None
        usuario.locked_until = None
        usuario.token_version = (usuario.token_version or 0) + 1
        ua.registrar_auditoria(usuario, "user_recovery_redeemed", usuario, {"recuperacion_id": fila_id})
        db.session.commit()
        return "ok", usuario
    except Exception:
        db.session.rollback()
        raise


def canjear(token_crudo, clave, repetida, ip=None):
    """Canje público. Devuelve ("ok", usuario), ("politica", errores) o ("invalido", motivo).

    El motivo solo va a la auditoría: la respuesta HTTP es la misma para todos los motivos inválidos.
    Un token válido con una clave que no cumple la política responde con errores de campo y no se consume.
    """
    ahora = security.ahora()
    texto = token_crudo.strip() if isinstance(token_crudo, str) else ""
    clave = clave if isinstance(clave, str) else ""
    repetida = repetida if isinstance(repetida, str) else ""
    forma_ok = _forma_valida(texto)
    # Siempre una consulta por hash, también con formato inválido: el tiempo no revela el motivo.
    fila = UserRecoveryToken.query.filter_by(token_hash=hash_del_enlace(texto[:LONGITUD_TOKEN_MAXIMA])).one_or_none()
    usuario = db.session.get(User, fila.user_id, populate_existing=True) if fila is not None else None
    motivo = _motivo_invalido(forma_ok, fila, usuario, ahora)
    if motivo is not None:
        _verificacion_equivalente(clave)
        _registrar_fallo(
            motivo,
            ip,
            ahora,
            usuario.id if usuario is not None else None,
            usuario.username if usuario is not None else None,
        )
        return "invalido", motivo
    errores = errores_clave_nueva(clave, repetida, usuario.username, None)
    if errores:
        _verificacion_equivalente(clave)
        return "politica", errores
    return _consumir_y_cambiar(fila.id, usuario.id, clave, ahora, ip)
