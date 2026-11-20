"""MFA opcional (C6 de administración de usuarios): activación, códigos de respaldo y segundo paso de login.

Reglas:
- El secreto TOTP (20 bytes) se guarda en users.mfa_secret. El paquete cryptography no está en
  requirements.txt, así que no hay cifrado en reposo: quien lea la base puede generar códigos (riesgo
  declarado en el PR; decisión para Ciro).
- Un código TOTP no se acepta dos veces: users.mfa_last_step guarda el último paso aceptado y se
  reclama con un UPDATE condicional (dos envíos simultáneos: gana uno).
- Un código de respaldo se marca usado con un UPDATE condicional (used_at IS NULL).
- Activar el MFA suma users.mfa_activado_en a la huella de sesión: las otras sesiones web del usuario
  dejan de valer. Los JWT no cambian (siguen su vida normal; ver docs/USUARIOS_PERMISOS.md).
- Un paso de login pendiente vive en la sesión firmada, no autoriza ninguna ruta y vence a los 5 minutos.
"""

import hashlib
import hmac
import re
import secrets
import threading
from collections import deque
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, g, jsonify, redirect, request, session, url_for
from sqlalchemy import or_

import security
from models import db
from models.core.user import User
from models.core.user_mfa_backup_code import UserMfaBackupCode
from services import totp

MINUTOS_SECRETO_PENDIENTE = 10
CANTIDAD_RESPALDOS = 10
LONGITUD_RESPALDO = 10
# Sin caracteres ambiguos: no hay 0, O, 1, I ni L.
ALFABETO_RESPALDO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CLAVE_PENDIENTE = "mfa_pendiente"
MINUTOS_PASO_PENDIENTE = 5
INTENTOS_PASO_PENDIENTE = 5
VENTANA_INTENTOS_IP = timedelta(minutes=10)
INTENTOS_POR_IP = 5
MENSAJE_CODIGO = "Código incorrecto o vencido."
METODO_APP = "código de la aplicación"
METODO_RESPALDO = "código de respaldo"
ROLES_CON_MFA_OBLIGATORIO = ("admin", "manager", "gerente")
ENDPOINTS_PENDIENTE = frozenset({"auth.login_mfa", "auth.logout", "static", "api_rest.health_check"})
ENDPOINTS_MFA_PROPIO = frozenset({
    "mfa_bp.seguridad",
    "mfa_bp.activar",
    "mfa_bp.confirmar",
    "mfa_bp.desactivar",
    "mfa_bp.regenerar",
    "auth.logout",
    "static",
    "api_rest.health_check",
})


class ErrorMfa(Exception):
    def __init__(self, codigo, mensaje, status=400, campos=None):
        super().__init__(codigo)
        self.codigo = codigo
        self.mensaje = mensaje
        self.status = status
        self.campos = campos


def _aware(valor):
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


def _bloquear_usuario(usuario_id):
    return User.query.filter_by(id=usuario_id).with_for_update().populate_existing().one_or_none()


# -----------------------------------------------------------------------------
# Límite por IP del segundo paso (proceso de la aplicación, como el canje de C5)
# -----------------------------------------------------------------------------
_lock_ip = threading.Lock()
_intentos_ip = {}


def limite_ip_superado(ip, ahora):
    with _lock_ip:
        cola = _intentos_ip.get(ip or "-")
        if not cola:
            return False
        while cola and cola[0] <= ahora - VENTANA_INTENTOS_IP:
            cola.popleft()
        return len(cola) >= INTENTOS_POR_IP


def registrar_intento_ip(ip, ahora):
    with _lock_ip:
        _intentos_ip.setdefault(ip or "-", deque()).append(ahora)


# -----------------------------------------------------------------------------
# Códigos de respaldo
# -----------------------------------------------------------------------------
def _hash_respaldo(salt, codigo):
    return hashlib.sha256(f"{salt}:{codigo}".encode("utf-8")).hexdigest()


def _normalizar_respaldo(texto):
    return re.sub(r"[^A-Z0-9]", "", texto.upper()) if isinstance(texto, str) else ""


def _generar_codigos_respaldo():
    codigos = []
    while len(codigos) < CANTIDAD_RESPALDOS:
        candidato = "".join(secrets.choice(ALFABETO_RESPALDO) for _ in range(LONGITUD_RESPALDO))
        if candidato not in codigos:
            codigos.append(candidato)
    return codigos


def _emitir_respaldos(usuario, ahora):
    """Crea los códigos nuevos (solo hashes en base) y devuelve los textos para mostrar una vez."""
    codigos = _generar_codigos_respaldo()
    for codigo in codigos:
        salt = secrets.token_hex(16)
        db.session.add(
            UserMfaBackupCode(
                user_id=usuario.id,
                salt=salt,
                code_hash=_hash_respaldo(salt, codigo),
                created_at=ahora,
            )
        )
    return [codigo[:5] + "-" + codigo[5:] for codigo in codigos]


def _consumir_respaldo(usuario, texto, ahora):
    norm = _normalizar_respaldo(texto)
    if len(norm) != LONGITUD_RESPALDO:
        return False
    hallado = None
    for fila in UserMfaBackupCode.query.filter_by(user_id=usuario.id, used_at=None).all():
        if hmac.compare_digest(fila.code_hash, _hash_respaldo(fila.salt, norm)) and hallado is None:
            hallado = fila.id
    if hallado is None:
        return False
    filas = (
        UserMfaBackupCode.query.filter(
            UserMfaBackupCode.id == hallado, UserMfaBackupCode.used_at.is_(None)
        ).update({"used_at": ahora}, synchronize_session=False)
    )
    return filas == 1


# -----------------------------------------------------------------------------
# TOTP con reclamo atómico del paso
# -----------------------------------------------------------------------------
def _reclamar_paso_totp(usuario, secreto_b32, codigo, ahora):
    """True si el código es válido en la ventana y su paso no se usó antes. Reclama el paso."""
    secreto = totp.secreto_desde_base32(secreto_b32)
    for paso in sorted(totp.pasos_coincidentes(secreto, codigo, ahora.timestamp())):
        filas = (
            User.query.filter(
                User.id == usuario.id,
                or_(User.mfa_last_step.is_(None), User.mfa_last_step < paso),
            ).update({"mfa_last_step": paso}, synchronize_session=False)
        )
        if filas == 1:
            usuario.mfa_last_step = paso
            return True
    return False


def _codigo_seis_digitos(texto):
    return isinstance(texto, str) and re.fullmatch(r"[0-9]{6}", texto.strip()) is not None


def verificar_segundo_factor(usuario, codigo, ahora):
    """Devuelve METODO_APP, METODO_RESPALDO o None. Un código ya usado no sirve de nuevo."""
    texto = codigo.strip() if isinstance(codigo, str) else ""
    if _codigo_seis_digitos(texto):
        if usuario.mfa_secret and _reclamar_paso_totp(usuario, usuario.mfa_secret, texto, ahora):
            return METODO_APP
        return None
    if _consumir_respaldo(usuario, texto, ahora):
        return METODO_RESPALDO
    return None


def _limpiar_mfa(fila):
    fila.mfa_enabled = False
    fila.mfa_secret = None
    fila.mfa_secret_pendiente = None
    fila.mfa_pendiente_expira = None


def _auditar(actor, accion, objetivo, detalle=None):
    from services.usuarios_admin import registrar_auditoria

    registrar_auditoria(actor, accion, objetivo, detalle or {})


# -----------------------------------------------------------------------------
# Autoservicio: activar, confirmar, desactivar, regenerar
# -----------------------------------------------------------------------------
def estado(usuario, ahora=None):
    ahora = ahora or security.ahora()
    pendiente = bool(
        usuario.mfa_secret_pendiente
        and usuario.mfa_pendiente_expira is not None
        and _aware(usuario.mfa_pendiente_expira) > ahora
    )
    restantes = UserMfaBackupCode.query.filter_by(user_id=usuario.id, used_at=None).count()
    return {"activo": usuario.mfa_enabled is True, "pendiente": pendiente, "respaldos_restantes": restantes}


def iniciar_activacion(usuario, clave, ahora):
    """Paso 1: valida la clave actual y deja un secreto PENDIENTE de 10 minutos. Devuelve (base32, otpauth)."""
    if usuario.mfa_enabled is True:
        raise ErrorMfa("MFA_YA_ACTIVO", "Ya tenés el MFA activado.", 409)
    if usuario.must_change_password:
        raise ErrorMfa("CLAVE_TEMPORAL", "Primero cambiá tu clave temporal.", 403)
    if not usuario.check_password(clave if isinstance(clave, str) else ""):
        raise ErrorMfa("CLAVE_INCORRECTA", "La clave actual no es correcta.", 400, {"clave_actual": "La clave actual no es correcta."})
    secreto = totp.secreto_a_base32(totp.generar_secreto())
    usuario.mfa_secret_pendiente = secreto
    usuario.mfa_pendiente_expira = ahora + timedelta(minutes=MINUTOS_SECRETO_PENDIENTE)
    db.session.commit()
    return secreto, totp.uri_otpauth(secreto, usuario.username)


def confirmar_activacion(usuario_id, codigo, ahora):
    """Paso 2: un código válido activa el MFA y emite los códigos de respaldo (se muestran una vez)."""
    fila = _bloquear_usuario(usuario_id)
    if fila is None or fila.active is not True:
        db.session.rollback()
        raise ErrorMfa("SESION_NO_VALIDA", "Iniciá sesión de nuevo.", 401)
    if fila.mfa_enabled is True:
        db.session.rollback()
        raise ErrorMfa("MFA_YA_ACTIVO", "Ya tenés el MFA activado.", 409)
    if not fila.mfa_secret_pendiente or fila.mfa_pendiente_expira is None or _aware(fila.mfa_pendiente_expira) <= ahora:
        db.session.rollback()
        raise ErrorMfa("SECRETO_VENCIDO", "El secreto venció. Empezá de nuevo desde «Activar MFA».", 409)
    texto = codigo.strip() if isinstance(codigo, str) else ""
    if not _codigo_seis_digitos(texto) or not _reclamar_paso_totp(fila, fila.mfa_secret_pendiente, texto, ahora):
        db.session.rollback()
        raise ErrorMfa("CODIGO_INCORRECTO", MENSAJE_CODIGO, 400, {"codigo": MENSAJE_CODIGO})
    fila.mfa_secret = fila.mfa_secret_pendiente
    fila.mfa_secret_pendiente = None
    fila.mfa_pendiente_expira = None
    fila.mfa_enabled = True
    fila.mfa_activado_en = ahora
    UserMfaBackupCode.query.filter_by(user_id=fila.id).delete(synchronize_session=False)
    respaldos = _emitir_respaldos(fila, ahora)
    _auditar(fila, "user_mfa_enabled", fila)
    db.session.commit()
    return respaldos


def desactivar(usuario_id, clave, codigo, ahora):
    fila = _bloquear_usuario(usuario_id)
    if fila is None or fila.active is not True:
        db.session.rollback()
        raise ErrorMfa("SESION_NO_VALIDA", "Iniciá sesión de nuevo.", 401)
    if fila.mfa_enabled is not True:
        db.session.rollback()
        raise ErrorMfa("MFA_NO_ACTIVO", "El MFA no está activado.", 409)
    if not fila.check_password(clave if isinstance(clave, str) else ""):
        db.session.rollback()
        raise ErrorMfa("CLAVE_INCORRECTA", "La clave actual no es correcta.", 400, {"clave_actual": "La clave actual no es correcta."})
    metodo = verificar_segundo_factor(fila, codigo, ahora)
    if metodo is None:
        db.session.rollback()
        raise ErrorMfa("CODIGO_INCORRECTO", MENSAJE_CODIGO, 400, {"codigo": MENSAJE_CODIGO})
    _limpiar_mfa(fila)
    UserMfaBackupCode.query.filter_by(user_id=fila.id).delete(synchronize_session=False)
    _auditar(fila, "user_mfa_disabled", fila, {"metodo": metodo})
    db.session.commit()
    return metodo


def regenerar_respaldos(usuario_id, clave, codigo, ahora):
    """Invalida los códigos anteriores y emite diez nuevos. Pide clave y un código de la aplicación."""
    fila = _bloquear_usuario(usuario_id)
    if fila is None or fila.active is not True:
        db.session.rollback()
        raise ErrorMfa("SESION_NO_VALIDA", "Iniciá sesión de nuevo.", 401)
    if fila.mfa_enabled is not True:
        db.session.rollback()
        raise ErrorMfa("MFA_NO_ACTIVO", "El MFA no está activado.", 409)
    if not fila.check_password(clave if isinstance(clave, str) else ""):
        db.session.rollback()
        raise ErrorMfa("CLAVE_INCORRECTA", "La clave actual no es correcta.", 400, {"clave_actual": "La clave actual no es correcta."})
    texto = codigo.strip() if isinstance(codigo, str) else ""
    if not _codigo_seis_digitos(texto) or not _reclamar_paso_totp(fila, fila.mfa_secret, texto, ahora):
        db.session.rollback()
        raise ErrorMfa("CODIGO_INCORRECTO", MENSAJE_CODIGO, 400, {"codigo": MENSAJE_CODIGO})
    UserMfaBackupCode.query.filter_by(user_id=fila.id).delete(synchronize_session=False)
    respaldos = _emitir_respaldos(fila, ahora)
    _auditar(fila, "user_mfa_backup_regenerated", fila)
    db.session.commit()
    return respaldos


# -----------------------------------------------------------------------------
# Segundo paso del login web: estado pendiente en la sesión firmada
# -----------------------------------------------------------------------------
def iniciar_pendiente_web(sesion, usuario, ahora):
    sesion.clear()
    sesion[CLAVE_PENDIENTE] = {"uid": usuario.id, "inicio": ahora.timestamp(), "intentos": 0}


def pendiente_vigente(sesion, ahora):
    pendiente = sesion.get(CLAVE_PENDIENTE)
    if not isinstance(pendiente, dict):
        return None
    if ahora.timestamp() - float(pendiente.get("inicio", 0)) >= MINUTOS_PASO_PENDIENTE * 60:
        sesion.pop(CLAVE_PENDIENTE, None)
        return None
    return pendiente


def descartar_pendiente(sesion):
    sesion.pop(CLAVE_PENDIENTE, None)


def contar_fallo_pendiente(sesion, pendiente):
    """True si se alcanzó el máximo de fallos: el estado pendiente se descarta."""
    pendiente["intentos"] = int(pendiente.get("intentos", 0)) + 1
    sesion[CLAVE_PENDIENTE] = pendiente
    return pendiente["intentos"] >= INTENTOS_PASO_PENDIENTE


def guardia_mfa_pendiente():
    """before_request: con un paso de MFA pendiente, solo /login/mfa, /logout, /static y /api/health."""
    if CLAVE_PENDIENTE not in session:
        return None
    if request.endpoint in ENDPOINTS_PENDIENTE:
        return None
    if pendiente_vigente(session, security.ahora()) is None:
        return None
    if "/api/" in request.path:
        return jsonify({"error": "Sesión requerida", "codigo": "MFA_PENDIENTE"}), 401
    return redirect(url_for("auth.login_mfa"))


def guardia_mfa_obligatorio():
    """Ajuste MFA_OBLIGATORIO_ADMIN (M6, apagado por defecto): exige MFA a admin, manager y gerente."""
    if not current_app.config.get("MFA_OBLIGATORIO_ADMIN"):
        return None
    usuario = g.get("usuario_sesion")
    if usuario is None or usuario.role not in ROLES_CON_MFA_OBLIGATORIO or usuario.mfa_enabled is True:
        return None
    if request.endpoint in ENDPOINTS_MFA_PROPIO:
        return None
    if "/api/" in request.path:
        return jsonify({"error": "Activá el MFA para continuar", "codigo": "MFA_OBLIGATORIO"}), 403
    flash("Activá el MFA para continuar.", "warning")
    return redirect(url_for("mfa_bp.seguridad"))
