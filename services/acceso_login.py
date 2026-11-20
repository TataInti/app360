"""Registro de accesos y bloqueo por cuenta/IP (C4): web y API comparten las mismas reglas.

Bloqueo (D6): 10 fallos en 15 minutos desde una IP bloquean ese par (cuenta, IP) durante 15 minutos.
Además, 40 fallos en 15 minutos sumando las IP bloquean la cuenta globalmente durante 15 minutos.
Las ventanas son fijas. Durante cualquiera de los bloqueos todo intento recibe el mismo rechazo que
una clave incorrecta, aunque la clave sea correcta, y no se extiende el bloqueo. Un acierto reinicia
el par de esa IP y el contador global si no está bloqueado. Inexistentes e inactivos no acumulan estado.

Transacción (igualación de tiempos): cada intento se confirma con un único COMMIT. El estado y la fila
de auditoría van juntos; la auditoría va en un punto de guardado, así que si falla solo ella se deshace.
Inexistentes e inactivos verifican el mismo hash ficticio y, antes de confirmar la auditoría, ejecutan un
UPSERT ficticio de costo equivalente dentro de un savepoint que se revierte. Todos los intentos terminan
con un único COMMIT; el UPDATE no-op del agregado de auditoría es común a todos los rechazos.

Auditoría (A1): login_ok y login_failed se escriben en user_audit_log con el usuario tal como se
escribió (sin caracteres no imprimibles, hasta 80), la IP truncada a 45 y un motivo genérico. La clave
no entra en ningún campo. Los fallos se agrupan por IP, canal, motivo, cuenta y minuto: una sola fila
con el contador en repeticiones. Las IP largas nunca hacen fallar el login.
"""

from dataclasses import dataclass
from datetime import timedelta, timezone
import secrets
import sqlalchemy as sa
from sqlalchemy import delete, func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import security
from models import db
from models.core.user import User
from models.core.user_audit_log import UserAuditLog
from models.core.user_login_attempt import UserLoginAttempt

UMBRAL_FALLOS = 10
UMBRAL_FALLOS_GLOBALES = 40
VENTANA_FALLOS = timedelta(minutes=15)
DURACION_BLOQUEO = timedelta(minutes=15)
LIMITE_PARES_IP = 50_000
LIMPIEZA_PARES_MAXIMA = 100
CLAVE_BLOQUEO_CAPACIDAD_PARES = 1_331_897_168

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


def _ip_normalizada(ip):
    """La columna ip es VARCHAR(45); el login nunca falla por una IP más larga."""
    return ip[:45] if isinstance(ip, str) else None


def _ip_par(ip):
    return ip if ip is not None else "-"


def _limpiar_pares_vencidos(ahora):
    """Limpia hasta 100 pares inactivos por más de un día, dentro de la transacción actual."""
    tabla = UserLoginAttempt.__table__
    candidatos = (
        select(tabla.c.user_id, tabla.c.ip)
        .where(tabla.c.updated_at < ahora - timedelta(days=1))
        .order_by(tabla.c.updated_at.asc())
        .limit(LIMPIEZA_PARES_MAXIMA)
    )
    db.session.execute(
        delete(tabla).where(tuple_(tabla.c.user_id, tabla.c.ip).in_(candidatos))
    )


def _hay_capacidad_para_par(user_id, ip):
    """Reserva el límite global de 50 000 pares sin sobrepasarlo bajo concurrencia PostgreSQL."""
    tabla = UserLoginAttempt.__table__
    existe = db.session.execute(
        select(tabla.c.user_id).where(tabla.c.user_id == user_id, tabla.c.ip == ip).limit(1)
    ).first()
    if existe:
        return True
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(CAST(:clave AS BIGINT))"),
            {"clave": CLAVE_BLOQUEO_CAPACIDAD_PARES},
        )
        existe = db.session.execute(
            select(tabla.c.user_id).where(tabla.c.user_id == user_id, tabla.c.ip == ip).limit(1)
        ).first()
        if existe:
            return True
    cantidad = db.session.execute(select(func.count()).select_from(tabla)).scalar_one()
    return cantidad < LIMITE_PARES_IP


def _upsert_intento_par(user_id, ip, ahora):
    """Suma un fallo por par con UPSERT condicional; devuelve False si se alcanzó el tope."""
    ip = _ip_par(ip)
    tabla = UserLoginAttempt.__table__
    if not _hay_capacidad_para_par(user_id, ip):
        return False
    insertar = pg_insert if db.session.get_bind().dialect.name == "postgresql" else sqlite_insert
    sentencia = insertar(tabla).values(
        user_id=user_id,
        ip=ip,
        failed_count=1,
        window_start=ahora,
        locked_until=None,
        updated_at=ahora,
    )
    bloqueo_vigente = sa.and_(tabla.c.locked_until.isnot(None), tabla.c.locked_until > ahora)
    ventana_vencida = sa.or_(
        tabla.c.window_start <= ahora - VENTANA_FALLOS,
        tabla.c.locked_until.isnot(None),
    )
    contador = sa.case(
        (bloqueo_vigente, tabla.c.failed_count),
        (ventana_vencida, 1),
        else_=tabla.c.failed_count + 1,
    )
    inicio = sa.case(
        (bloqueo_vigente, tabla.c.window_start),
        (ventana_vencida, ahora),
        else_=tabla.c.window_start,
    )
    bloqueo = sa.case(
        (bloqueo_vigente, tabla.c.locked_until),
        (ventana_vencida, None),
        ((tabla.c.failed_count + 1) >= UMBRAL_FALLOS, ahora + DURACION_BLOQUEO),
        else_=None,
    )
    sentencia = sentencia.on_conflict_do_update(
        index_elements=[tabla.c.user_id, tabla.c.ip],
        set_={
            "failed_count": contador,
            "window_start": inicio,
            "locked_until": bloqueo,
            "updated_at": ahora,
        },
    )
    db.session.execute(sentencia)
    return True


def _tocar_par_sin_fallo(user_id, ip, ahora, *, crear=True):
    """Escritura de costo equivalente sin alterar contadores ni extender un bloqueo."""
    ip = _ip_par(ip)
    tabla = UserLoginAttempt.__table__
    existe = db.session.execute(
        select(tabla.c.user_id).where(tabla.c.user_id == user_id, tabla.c.ip == ip).limit(1)
    ).first()
    if existe:
        db.session.execute(
            update(tabla)
            .where(tabla.c.user_id == user_id, tabla.c.ip == ip)
            .values(updated_at=ahora)
        )
        return True
    if not crear or not _hay_capacidad_para_par(user_id, ip):
        return False
    insertar = pg_insert if db.session.get_bind().dialect.name == "postgresql" else sqlite_insert
    sentencia = insertar(tabla).values(
        user_id=user_id,
        ip=ip,
        failed_count=0,
        window_start=ahora,
        locked_until=None,
        updated_at=ahora,
    )
    db.session.execute(
        sentencia.on_conflict_do_update(
            index_elements=[tabla.c.user_id, tabla.c.ip],
            set_={"updated_at": ahora},
        )
    )
    return True


def _escritura_de_rechazo_sin_cuenta(ip, ahora):
    """Actualiza contadores ficticios bajo savepoint y revierte todo antes del COMMIT real."""
    _limpiar_pares_vencidos(ahora)
    candidatos = db.session.execute(select(User.id).order_by(User.id).limit(64)).scalars().all()
    if not candidatos:
        return
    user_id = secrets.choice(candidatos)
    ip_ficticia = f"__c4_timing_{secrets.token_hex(8)}"
    savepoint = db.session.begin_nested()
    try:
        fila = (
            User.query.filter_by(id=user_id)
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if fila is None:
            return
        _sumar_fallo(fila, ahora)
        _par_de_usuario(fila.id, ip_ficticia)
        _upsert_intento_par(fila.id, ip_ficticia, ahora)
        db.session.flush()
    finally:
        savepoint.rollback()


def _escritura_de_rechazo_bloqueado(fila, ip, ahora):
    """Iguala el trabajo de escritura sin sumar ni extender contadores durante el bloqueo."""
    tabla_usuario = User.__table__
    db.session.execute(
        update(tabla_usuario)
        .where(tabla_usuario.c.id == fila.id)
        .values(failed_login_count=tabla_usuario.c.failed_login_count)
    )
    _tocar_par_sin_fallo(fila.id, ip, ahora, crear=False)


def _par_de_usuario(user_id, ip):
    return (
        UserLoginAttempt.query.filter_by(user_id=user_id, ip=_ip_par(ip))
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )


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
    """Decide un login por par (cuenta, IP) y por tope global; web y API comparten la regla."""
    texto = username if isinstance(username, str) else ""
    clave = password if isinstance(password, str) else ""
    ip = _ip_normalizada(ip)
    nombre = nombre_auditado(texto, clave)
    try:
        existente = User.query.filter_by(username=texto).first()
        activa = existente if existente is not None and existente.active is True else None
        # Todo caso realiza una verificación de hash con el mismo costo, aun si no hay cuenta activa.
        coincide, vencida = security.comprobar_clave_login(activa, clave)
        if existente is None:
            ahora = security.ahora()
            _escritura_de_rechazo_sin_cuenta(ip, ahora)
            return _rechazar(canal, ip, nombre, None, USUARIO_INEXISTENTE, ahora)
        if activa is None:
            ahora = security.ahora()
            _escritura_de_rechazo_sin_cuenta(ip, ahora)
            return _rechazar(canal, ip, nombre, existente, CUENTA_INACTIVA, ahora)
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
    # Se serializa por usuario; el UPSERT del par protege además su clave compuesta entre workers.
    fila = User.query.filter_by(id=usuario.id).with_for_update().populate_existing().one_or_none()
    if fila is None or fila.active is not True:
        db.session.rollback()
        _escritura_de_rechazo_sin_cuenta(ip, ahora)
        return _rechazar(canal, ip, nombre, None, CUENTA_INACTIVA, ahora)
    _limpiar_pares_vencidos(ahora)
    if esta_bloqueada(fila, ahora):
        _escritura_de_rechazo_bloqueado(fila, ip, ahora)
        return _rechazar(canal, ip, nombre, fila, CUENTA_BLOQUEADA, ahora)
    par = _par_de_usuario(fila.id, ip)
    if par is not None and par.locked_until is not None and _aware(par.locked_until) > ahora:
        _escritura_de_rechazo_bloqueado(fila, ip, ahora)
        return _rechazar(canal, ip, nombre, fila, CUENTA_BLOQUEADA, ahora)
    if coincide and not vencida:
        pendiente = bool(fila.must_change_password)
        fila.failed_login_count = 0
        fila.failed_login_window_start = None
        fila.locked_until = None
        if par is not None:
            par.failed_count = 0
            par.window_start = ahora
            par.locked_until = None
            par.updated_at = ahora
        if canal == "web" or not pendiente:
            fila.last_login_at = ahora
        detalle = {"canal": canal, "cambio_clave_pendiente": pendiente}
        valores = _valores_evento("login_ok", canal, ip, nombre, fila, ahora, detalle, None)
        _cerrar_intento(valores, canal, ip, nombre)
        return Resultado(ok=True, usuario=fila, cambio_clave_pendiente=pendiente)
    motivo = CLAVE_TEMPORAL_VENCIDA if coincide else CLAVE_INCORRECTA
    _sumar_fallo(fila, ahora)
    _upsert_intento_par(fila.id, ip, ahora)
    return _rechazar(canal, ip, nombre, fila, motivo, ahora)


def _sumar_fallo(fila, ahora):
    """Suma un fallo global a la ventana vigente; 40 fallos bloquean la cuenta para todas las IPs."""
    inicio = fila.failed_login_window_start
    ventana_vencida = inicio is None or _aware(inicio) + VENTANA_FALLOS <= ahora
    if ventana_vencida or fila.locked_until is not None:
        fila.failed_login_window_start = ahora
        fila.failed_login_count = 1
        fila.locked_until = None
    else:
        fila.failed_login_count = (fila.failed_login_count or 0) + 1
    if fila.failed_login_count >= UMBRAL_FALLOS_GLOBALES:
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
    if valores.get("accion") == "login_failed" and valores.get("clave_agrupacion") is not None:
        # Escritura de costo equivalente en todos los rechazos, incluso si no existe una fila de users.
        # No cambia el agregado y queda dentro del mismo savepoint/COMMIT de auditoría.
        db.session.execute(
            update(tabla)
            .where(tabla.c.clave_agrupacion == valores["clave_agrupacion"])
            .values(repeticiones=tabla.c.repeticiones)
        )


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
