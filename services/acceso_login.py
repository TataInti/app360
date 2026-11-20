"""Registro de accesos y bloqueo por cuenta (C4): el login web y el de la API usan estas reglas.

Bloqueo (D6): 10 intentos fallidos dentro de una ventana de 15 minutos bloquean la cuenta durante
15 minutos. La ventana empieza en el primer fallo y se reinicia al vencer; no es deslizante por
fallo, porque eso obligaría a guardar cada fallo. Durante el bloqueo, cualquier intento recibe el
mismo rechazo que una clave incorrecta, aunque la clave sea la correcta, y no cambia el contador ni
extiende el bloqueo. Los usuarios inexistentes y las cuentas desactivadas no tienen estado: no
suman fallos ni se bloquean.

Transacción (igualación de tiempos): cada intento se confirma con un único COMMIT. El estado de la
cuenta y la fila de auditoría van juntos; la auditoría va en un punto de guardado, así que si falla
solo ella se deshace, el estado se conserva y el login responde igual. Así el camino de una cuenta
existente no hace más confirmaciones que el de una cuenta inexistente.

Auditoría (A1): login_ok y login_failed se escriben en user_audit_log con el usuario tal como se
escribió (sin caracteres no imprimibles, hasta 80), la IP y un motivo genérico. La clave no entra en
ningún campo. Los fallos se agrupan por IP, canal, motivo, cuenta y minuto: una sola fila con el
contador en repeticiones. Así una ráfaga de nombres inexistentes ocupa una fila por minuto y por IP.
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
    """Decide un inicio de sesión, aplica el bloqueo y registra el acceso en una sola transacción.

    canal: "web" o "api". Los rechazos son iguales para todos los motivos: solo el registro interno
    distingue el motivo. Si el estado no se puede leer o confirmar, el login se rechaza igual.
    """
    texto = username if isinstance(username, str) else ""
    clave = password if isinstance(password, str) else ""
    nombre = nombre_auditado(texto, clave)
    try:
        existente = User.query.filter_by(username=texto).first()
        activa = existente if existente is not None and existente.active is True else None
        # Mismo trabajo de hash en todos los casos (M4): el tiempo no revela si la cuenta existe ni si está bloqueada.
        coincide, vencida = security.comprobar_clave_login(activa, clave)
        if existente is None:
            return _rechazar(canal, ip, nombre, None, USUARIO_INEXISTENTE)
        if activa is None:
            return _rechazar(canal, ip, nombre, existente, CUENTA_INACTIVA)
        return _decidir_cuenta_activa(canal, ip, nombre, activa, coincide, vencida)
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


def _decidir_cuenta_activa(canal, ip, nombre, usuario, coincide, vencida):
    ahora = security.ahora()
    # Bloqueo de fila: los intentos de una cuenta se serializan y cada uno ve el contador del anterior.
    fila = User.query.filter_by(id=usuario.id).with_for_update().populate_existing().one_or_none()
    if fila is None or fila.active is not True:
        db.session.rollback()
        return _rechazar(canal, ip, nombre, None, CUENTA_INACTIVA, ahora)
    if esta_bloqueada(fila, ahora):
        # Durante el bloqueo no se cambia el contador ni se extiende el bloqueo.
        return _rechazar(canal, ip, nombre, fila, CUENTA_BLOQUEADA, ahora)
    if coincide and not vencida:
        pendiente = bool(fila.must_change_password)
        fila.failed_login_count = 0
        fila.failed_login_window_start = None
        fila.locked_until = None
        if canal == "web" or not pendiente:
            fila.last_login_at = ahora
        detalle = {"canal": canal, "cambio_clave_pendiente": pendiente}
        valores = _valores_evento("login_ok", canal, ip, nombre, fila, ahora, detalle, None)
        _cerrar_intento(valores, canal, ip, nombre)
        return Resultado(ok=True, usuario=fila, cambio_clave_pendiente=pendiente)
    motivo = CLAVE_TEMPORAL_VENCIDA if coincide else CLAVE_INCORRECTA
    _sumar_fallo(fila, ahora)
    return _rechazar(canal, ip, nombre, fila, motivo, ahora)


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


def _rechazar(canal, ip, nombre, usuario, motivo, ahora=None):
    """Registra el rechazo y confirma el intento. El motivo solo queda en la auditoría."""
    ahora = ahora or security.ahora()
    agrupacion = _agrupacion(canal, ip, motivo, usuario, ahora)
    valores = _valores_evento("login_failed", canal, ip, nombre, usuario, ahora, {"motivo": motivo, "canal": canal}, agrupacion)
    _cerrar_intento(valores, canal, ip, nombre)
    return Resultado(ok=False, motivo=motivo)


def _valores_evento(accion, canal, ip, nombre, usuario, ahora, detalle, agrupacion):
    """Fila de auditoría. El objetivo es la cuenta si existe; si no, queda sin objetivo (NULL)."""
    objetivo_id = usuario.id if usuario is not None else None
    return {
        "created_at": ahora,
        "actor_user_id": objetivo_id,
        "actor_username": nombre,
        "accion": accion,
        "target_user_id": objetivo_id,
        "target_username": usuario.username if usuario is not None else None,
        "detalle": detalle,
        "ip": ip,
        "clave_agrupacion": agrupacion,
        "repeticiones": 1,
    }


def _agrupacion(canal, ip, motivo, usuario, ahora):
    """Clave de agrupación de los fallos: IP, canal, motivo, cuenta (si existe) y minuto.

    El nombre escrito no forma parte de la clave: una ráfaga de nombres inexistentes ocupa una sola
    fila por minuto y por IP.
    """
    minuto = ahora.replace(second=0, microsecond=0)
    objetivo_id = usuario.id if usuario is not None else None
    return f"fallo|{ip or '-'}|{canal}|{motivo}|{objetivo_id or '-'}|{minuto:%Y%m%d%H%M}"


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


def _cerrar_intento(valores, canal, ip, nombre):
    """Confirma el intento con un único COMMIT: estado de la cuenta y auditoría juntos.

    El estado se envía a la base antes del punto de guardado: si falla, la excepción llega a
    autenticar() y el login se rechaza. La auditoría va en un punto de guardado: si falla, solo ella
    se deshace, el estado se confirma igual, queda un evento de seguridad y el login responde igual.
    """
    db.session.flush()
    try:
        with db.session.begin_nested():
            _escribir_evento(valores)
    except Exception:
        security.log_security_event(
            "AUDITORIA_LOGIN_NO_REGISTRADA",
            f"No se pudo registrar un acceso ({valores['accion']}) en la auditoría; el login responde igual",
            user=nombre,
            ip=ip,
            extra={"canal": canal, "accion": valores["accion"]},
        )
    db.session.commit()
