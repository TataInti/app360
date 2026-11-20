"""Registro de accesos y bloqueo por cuenta (C4): el login web y el de la API usan estas reglas.

Bloqueo (D6): 10 intentos fallidos dentro de una ventana de 15 minutos bloquean la cuenta durante
15 minutos. La ventana empieza en el primer fallo y se reinicia al vencer; no es deslizante por
fallo, porque eso obligaría a guardar cada fallo. Durante el bloqueo, cualquier intento recibe el
mismo rechazo que una clave incorrecta, aunque la clave sea la correcta, y no cambia el contador ni
extiende el bloqueo. Los usuarios inexistentes y las cuentas desactivadas no tienen estado: no
suman fallos ni se bloquean.

Auditoría (A1): login_ok y login_failed se escriben en user_audit_log con el usuario tal como se
escribió (sin caracteres no imprimibles, hasta 80), la IP y un motivo genérico. La clave no entra en
ningún campo. Los fallos se agrupan por IP, motivo, cuenta y minuto: una sola fila con el contador
en repeticiones. Así una ráfaga de nombres inexistentes ocupa una fila por minuto y por IP. La
escritura es de mejor esfuerzo: si falla, el login responde igual y queda un evento de seguridad.
"""

from dataclasses import dataclass
from datetime import timedelta, timezone

import security
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog

UMBRAL_FALLOS = 10
VENTANA_FALLOS = timedelta(minutes=15)
DURACION_BLOQUEO = timedelta(minutes=15)

CLAVE_INCORRECTA = "clave_incorrecta"
USUARIO_INEXISTENTE = "usuario_inexistente"
CUENTA_INACTIVA = "cuenta_inactiva"
CUENTA_BLOQUEADA = "cuenta_bloqueada"
CLAVE_TEMPORAL_VENCIDA = "clave_temporal_vencida"
ETIQUETAS_MOTIVO = {
    CLAVE_INCORRECTA: "clave incorrecta",
    USUARIO_INEXISTENTE: "usuario inexistente",
    CUENTA_INACTIVA: "cuenta desactivada",
    CUENTA_BLOQUEADA: "cuenta bloqueada",
    CLAVE_TEMPORAL_VENCIDA: "clave temporal vencida",
}
LARGO_USUARIO_AUDITADO = 80
LARGO_MINIMO_CLAVE_OMITIDA = 4
TEXTO_OMITIDO = "(dato omitido)"
TEXTO_VACIO = "(vacío)"


@dataclass(frozen=True)
class Resultado:
    """ok: la clave es válida y la cuenta puede entrar. usuario y cambio_clave_pendiente solo si ok."""

    ok: bool
    usuario: object = None
    motivo: str = None
    cambio_clave_pendiente: bool = False


def _aware(valor):
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=timezone.utc)


def esta_bloqueada(usuario, ahora=None):
    """True mientras locked_until siga en el futuro."""
    if usuario is None or usuario.locked_until is None:
        return False
    return _aware(usuario.locked_until) > (ahora or security.ahora())


def nombre_auditado(texto, clave):
    """El usuario tal como se escribió, sin caracteres no imprimibles y hasta 80.

    Si la clave (de al menos 4 caracteres) aparece dentro del nombre, el nombre no se guarda: así
    la auditoría nunca contiene la clave ni una parte de ella.
    """
    texto = texto if isinstance(texto, str) else ""
    clave = clave if isinstance(clave, str) else ""
    if clave and len(clave) >= LARGO_MINIMO_CLAVE_OMITIDA and clave in texto:
        return TEXTO_OMITIDO
    limpio = "".join(caracter for caracter in texto if caracter.isprintable())
    return limpio[:LARGO_USUARIO_AUDITADO] or TEXTO_VACIO


def autenticar(username, password, canal, ip=None):
    """Decide un inicio de sesión, aplica el bloqueo y registra el acceso. Nunca lanza por la auditoría.

    canal: "web" o "api". Los rechazos son iguales para todos los motivos: solo el registro interno
    distingue el motivo.
    """
    texto = username if isinstance(username, str) else ""
    clave = password if isinstance(password, str) else ""
    existente = User.query.filter_by(username=texto).first()
    activa = existente if existente is not None and existente.active is True else None
    # Mismo trabajo de hash en todos los casos (M4): el tiempo no revela si la cuenta existe ni si está bloqueada.
    coincide, vencida = security.comprobar_clave_login(activa, clave)
    nombre = nombre_auditado(texto, clave)
    if existente is None:
        return _rechazar(canal, ip, nombre, None, USUARIO_INEXISTENTE)
    if activa is None:
        return _rechazar(canal, ip, nombre, existente, CUENTA_INACTIVA)
    return _decidir_cuenta_activa(canal, ip, nombre, activa, coincide, vencida)


def _decidir_cuenta_activa(canal, ip, nombre, usuario, coincide, vencida):
    ahora = security.ahora()
    try:
        # Bloqueo de fila: los intentos de una cuenta se serializan y cada uno ve el contador del anterior.
        fila = User.query.filter_by(id=usuario.id).with_for_update().populate_existing().one_or_none()
        if fila is None or fila.active is not True:
            db.session.rollback()
            return _rechazar(canal, ip, nombre, None, CUENTA_INACTIVA)
        if esta_bloqueada(fila, ahora):
            # Durante el bloqueo no se cambia el contador ni se extiende el bloqueo.
            db.session.commit()
            return _rechazar(canal, ip, nombre, fila, CUENTA_BLOQUEADA)
        if coincide and not vencida:
            pendiente = bool(fila.must_change_password)
            id_usuario, nombre_usuario = fila.id, fila.username
            fila.failed_login_count = 0
            fila.failed_login_window_start = None
            fila.locked_until = None
            if canal == "web" or not pendiente:
                fila.last_login_at = ahora
            db.session.commit()
            _auditar_acceso_correcto(canal, ip, nombre, id_usuario, nombre_usuario, pendiente)
            return Resultado(ok=True, usuario=fila, cambio_clave_pendiente=pendiente)
        motivo = CLAVE_TEMPORAL_VENCIDA if coincide else CLAVE_INCORRECTA
        _sumar_fallo(fila, ahora)
        db.session.commit()
        return _rechazar(canal, ip, nombre, fila, motivo)
    except Exception:
        db.session.rollback()
        security.log_security_event(
            "LOGIN_ESTADO_NO_ACTUALIZADO",
            "No se pudo actualizar el estado de acceso de la cuenta; el login se rechaza",
            user=nombre,
            ip=ip,
            extra={"canal": canal},
        )
        return Resultado(ok=False)


def _sumar_fallo(fila, ahora):
    """Suma un fallo a la ventana vigente. Al llegar al umbral, bloquea la cuenta."""
    inicio = fila.failed_login_window_start
    ventana_vencida = inicio is None or _aware(inicio) + VENTANA_FALLOS <= ahora
    if ventana_vencida or fila.locked_until is not None:
        # Ventana nueva: el primer fallo la abre. Un bloqueo ya vencido se levanta aquí.
        fila.failed_login_window_start = ahora
        fila.failed_login_count = 1
        fila.locked_until = None
    else:
        fila.failed_login_count = (fila.failed_login_count or 0) + 1
    if fila.failed_login_count >= UMBRAL_FALLOS:
        fila.locked_until = ahora + DURACION_BLOQUEO


def _rechazar(canal, ip, nombre, usuario, motivo):
    _auditar_fallo(canal, ip, nombre, usuario, motivo)
    return Resultado(ok=False, motivo=motivo)


def _escribir_evento(valores):
    """Inserta la fila de auditoría. Si trae clave_agrupacion y ya existe, suma una repetición (atómico)."""
    tabla = UserAuditLog.__table__
    if db.session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as insertar
    else:
        from sqlalchemy.dialects.sqlite import insert as insertar
    sentencia = insertar(tabla).values(**valores)
    if valores.get("clave_agrupacion") is not None:
        sentencia = sentencia.on_conflict_do_update(
            index_elements=[tabla.c.clave_agrupacion],
            index_where=tabla.c.clave_agrupacion.isnot(None),
            set_={"repeticiones": tabla.c.repeticiones + 1},
        )
    db.session.execute(sentencia)


def _mejor_esfuerzo(accion, canal, ip, nombre, escribir):
    """Escribe y confirma. Si falla, deshace solo la auditoría: el login no cambia y queda un evento de seguridad."""
    try:
        escribir()
        db.session.commit()
    except Exception:
        db.session.rollback()
        security.log_security_event(
            "AUDITORIA_LOGIN_NO_REGISTRADA",
            f"No se pudo registrar un acceso ({accion}) en la auditoría; el login responde igual",
            user=nombre,
            ip=ip,
            extra={"canal": canal, "accion": accion},
        )


def _auditar_acceso_correcto(canal, ip, nombre, usuario_id, usuario_nombre, pendiente):
    valores = {
        "created_at": security.ahora(),
        "actor_user_id": usuario_id,
        "actor_username": nombre,
        "accion": "login_ok",
        "target_user_id": usuario_id,
        "target_username": usuario_nombre,
        "detalle": {"canal": canal, "cambio_clave_pendiente": pendiente},
        "ip": ip,
        "clave_agrupacion": None,
        "repeticiones": 1,
    }
    _mejor_esfuerzo("login_ok", canal, ip, nombre, lambda: _escribir_evento(valores))


def _auditar_fallo(canal, ip, nombre, usuario, motivo):
    def escribir():
        ahora = security.ahora()
        objetivo_id = usuario.id if usuario is not None else None
        objetivo_nombre = usuario.username if usuario is not None else None
        minuto = ahora.replace(second=0, microsecond=0)
        # Agrupación: IP, canal, motivo, cuenta (si existe) y minuto. El nombre escrito no forma parte de la clave.
        agrupacion = f"fallo|{ip or '-'}|{canal}|{motivo}|{objetivo_id or '-'}|{minuto:%Y%m%d%H%M}"
        _escribir_evento(
            {
                "created_at": ahora,
                "actor_user_id": objetivo_id,
                "actor_username": nombre,
                "accion": "login_failed",
                "target_user_id": objetivo_id,
                "target_username": objetivo_nombre,
                "detalle": {"motivo": motivo, "canal": canal},
                "ip": ip,
                "clave_agrupacion": agrupacion,
                "repeticiones": 1,
            }
        )

    _mejor_esfuerzo("login_failed", canal, ip, nombre, escribir)
