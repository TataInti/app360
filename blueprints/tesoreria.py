from datetime import datetime, timedelta, time, date
import io
from decimal import Decimal

from flask import Blueprint, request, jsonify, render_template, session, send_file

from models import (
    ArqueoCaja,
    InstrumentoPago,
    MovimientoCaja,
    User,
    db,
)
from models.tesoreria import LogArqueo, ArqueoDetalle
from models.gastos import CategoriaGasto, Proveedor
from security import protect_blueprint

tesoreria_bp = Blueprint("tesoreria", __name__)

protect_blueprint(tesoreria_bp, "tesoreria")


# RUTAS WEB
@tesoreria_bp.route("/tesoreria", methods=["GET"])
def tesoreria_dashboard():
    """Dashboard principal de Tesorería"""
    return render_template("tesoreria_panel.html")


@tesoreria_bp.route("/tesoreria/arqueos", methods=["GET"])
def tesoreria_arqueos():
    """Vista de arqueos de caja"""
    return render_template("tesoreria_arqueos.html")


@tesoreria_bp.route("/tesoreria/movimientos", methods=["GET"])
def tesoreria_movimientos():
    """Vista de movimientos"""
    return render_template("tesoreria_movimientos.html")


# Endpoints para Tesorería Multicanal

@tesoreria_bp.route("/api/tesoreria/instrumentos", methods=["GET"])
def instrumentos_listar():
    """Listar instrumentos de pago disponibles"""
    instrumentos = InstrumentoPago.query.filter_by(activo=True).all()
    return jsonify({
        "instrumentos": [{
            "id": i.id,
            "nombre": i.nombre,
            "descripcion": i.descripcion
        } for i in instrumentos]
    })


@tesoreria_bp.route("/api/tesoreria/instrumentos", methods=["POST"])
def instrumentos_crear():
    """Crear nuevo instrumento de pago"""
    data = request.get_json()
    nombre = data.get("nombre")
    descripcion = data.get("descripcion", "")

    if not nombre:
        return jsonify({"error": "Nombre requerido"}), 400

    if InstrumentoPago.query.filter_by(nombre=nombre).first():
        return jsonify({"error": "Instrumento ya existe"}), 400

    instrumento = InstrumentoPago(nombre=nombre, descripcion=descripcion)
    db.session.add(instrumento)
    db.session.commit()

    return jsonify({
        "message": "Instrumento creado",
        "instrumento": {
            "id": instrumento.id,
            "nombre": instrumento.nombre,
            "descripcion": instrumento.descripcion
        }
    }), 201


@tesoreria_bp.route("/api/tesoreria/movimientos", methods=["GET"])
def movimientos_listar():
    """Listar movimientos de caja con filtros"""
    # Filtros
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    tipo = request.args.get("tipo")  # ingreso/egreso
    instrumento_id = request.args.get("instrumento_id")
    arqueo_id = request.args.get("arqueo_id")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    query = MovimientoCaja.query.filter(MovimientoCaja.estado != "anulado")

    if fecha_desde:
        query = query.filter(MovimientoCaja.fecha_hora >= datetime.strptime(fecha_desde, "%Y-%m-%d"))
    if fecha_hasta:
        query = query.filter(MovimientoCaja.fecha_hora <= datetime.strptime(fecha_hasta + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
    if tipo:
        query = query.filter(MovimientoCaja.tipo == tipo)
    if instrumento_id:
        query = query.filter(MovimientoCaja.instrumento_id == instrumento_id)
    if arqueo_id:
        query = query.filter(MovimientoCaja.arqueo_id == arqueo_id)

    movimientos = query.order_by(MovimientoCaja.fecha_hora.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "movimientos": [{
            "id": m.id,
            "fecha_hora": m.fecha_hora.isoformat(),
            "tipo": m.tipo,
            "monto": float(m.monto),
            "descripcion": m.descripcion,
            "instrumento": m.instrumento.nombre,
            "categoria_gasto": m.categoria_gasto.nombre if m.categoria_gasto else None,
            "proveedor": m.proveedor.nombre if m.proveedor else None,
            "referencia": m.referencia,
            "cliente_proveedor": m.cliente_proveedor,
            "estado": m.estado,
            "motivo_anulacion": m.motivo_anulacion,
            "usuario": m.usuario.username if m.usuario else None
        } for m in movimientos.items],
        "total": movimientos.total,
        "pages": movimientos.pages,
        "current_page": movimientos.page
    })


@tesoreria_bp.route("/api/tesoreria/movimientos/resumen-instrumento", methods=["GET"])
def movimientos_resumen_instrumento():
    """Resumen de movimientos agrupados por instrumento con filtros de fecha y usuario"""
    from sqlalchemy import func
    
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    usuario_id = request.args.get("usuario_id")
    
    # Por defecto: hoy
    if not fecha_desde and not fecha_hasta:
        fecha_desde = date.today().isoformat()
        fecha_hasta = date.today().isoformat()
    
    dt_desde = datetime.combine(datetime.strptime(fecha_desde, "%Y-%m-%d").date(), datetime.min.time()) if fecha_desde else datetime.combine(date.today(), datetime.min.time())
    dt_hasta = datetime.combine(datetime.strptime(fecha_hasta, "%Y-%m-%d").date(), datetime.max.time()) if fecha_hasta else datetime.combine(date.today(), datetime.max.time())
    
    query = db.session.query(
        InstrumentoPago.nombre.label('instrumento'),
        func.sum(MovimientoCaja.monto).label('total')
    ).join(
        InstrumentoPago, MovimientoCaja.instrumento_id == InstrumentoPago.id
    ).filter(
        MovimientoCaja.estado != "anulado",
        MovimientoCaja.fecha_hora >= dt_desde,
        MovimientoCaja.fecha_hora <= dt_hasta
    )
    
    if usuario_id:
        query = query.filter(MovimientoCaja.usuario_id == usuario_id)
    
    query = query.group_by(
        InstrumentoPago.nombre
    ).order_by(
        func.sum(MovimientoCaja.monto).desc()
    )
    
    resultados = query.all()
    
    return jsonify({
        "movimientos": [{
            "instrumento": row.instrumento,
            "total": float(row.total or 0)
        } for row in resultados],
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta
    })


@tesoreria_bp.route("/api/tesoreria/movimientos/exportar", methods=["GET"])
def movimientos_exportar():
    """Exportar movimientos de caja a Excel"""
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"error": "Pandas no instalado"}), 500

    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    tipo = request.args.get("tipo")
    instrumento_id = request.args.get("instrumento_id")
    arqueo_id = request.args.get("arqueo_id")

    query = MovimientoCaja.query.filter(MovimientoCaja.estado != "anulado")

    if fecha_desde:
        query = query.filter(MovimientoCaja.fecha_hora >= datetime.strptime(fecha_desde, "%Y-%m-%d"))
    if fecha_hasta:
        query = query.filter(
            MovimientoCaja.fecha_hora <= datetime.strptime(
                fecha_hasta + " 23:59:59", "%Y-%m-%d %H:%M:%S"
            )
        )
    if tipo:
        query = query.filter(MovimientoCaja.tipo == tipo)
    if instrumento_id:
        query = query.filter(MovimientoCaja.instrumento_id == instrumento_id)
    if arqueo_id:
        query = query.filter(MovimientoCaja.arqueo_id == arqueo_id)

    movimientos = query.order_by(MovimientoCaja.fecha_hora.desc()).all()

    data = []
    for m in movimientos:
        data.append({
            "Fecha/Hora": m.fecha_hora,
            "Tipo": m.tipo,
            "Monto": float(m.monto),
            "Instrumento": m.instrumento.nombre if m.instrumento else "",
            "Categoría Gasto": m.categoria_gasto.nombre if m.categoria_gasto else "",
            "Proveedor": m.proveedor.nombre if m.proveedor else "",
            "Descripcion": m.descripcion,
            "Referencia": m.referencia or "",
            "Cliente/Proveedor": m.cliente_proveedor or "",
            "Usuario": m.usuario.username if m.usuario else ""
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Movimientos", index=False)

    output.seek(0)
    fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tesoreria_movimientos_{fecha_actual}.xlsx"

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@tesoreria_bp.route("/api/tesoreria/movimientos", methods=["POST"])
def movimientos_crear():
    """Crear nuevo movimiento de caja"""
    data = request.get_json()

    tipo = data.get("tipo")
    monto = data.get("monto")
    descripcion = data.get("descripcion")
    instrumento_id = data.get("instrumento_id")
    categoria_gasto_id = data.get("categoria_gasto_id")
    proveedor_id = data.get("proveedor_id")
    usuario_id = data.get("usuario_id")
    if not usuario_id:
        session_user = session.get("user")
        if session_user:
            usuario = User.query.filter_by(username=session_user).first()
            if usuario:
                usuario_id = usuario.id

    if not usuario_id:
        return jsonify({"error": "Usuario no encontrado"}), 401

    if tipo not in ["ingreso", "egreso"]:
        return jsonify({"error": "Tipo debe ser 'ingreso' o 'egreso'"}), 400

    if not monto or not descripcion or not instrumento_id:
        return jsonify({"error": "Monto, descripción e instrumento requeridos"}), 400

    try:
        monto = Decimal(str(monto))
    except:
        return jsonify({"error": "Monto inválido"}), 400

    instrumento = InstrumentoPago.query.get(instrumento_id)
    if not instrumento:
        return jsonify({"error": "Instrumento no encontrado"}), 404

    movimiento = MovimientoCaja(
        tipo=tipo,
        monto=monto,
        descripcion=descripcion,
        instrumento_id=instrumento_id,
        categoria_gasto_id=categoria_gasto_id,
        proveedor_id=proveedor_id,
        usuario_id=usuario_id,
        referencia=data.get("referencia"),
        cliente_proveedor=data.get("cliente_proveedor")
    )

    db.session.add(movimiento)
    db.session.commit()

    return jsonify({
        "message": "Movimiento registrado",
        "movimiento": {
            "id": movimiento.id,
            "tipo": movimiento.tipo,
            "monto": float(movimiento.monto),
            "descripcion": movimiento.descripcion,
            "instrumento": movimiento.instrumento.nombre
        }
    }), 201


# ── Anulación de movimientos ──────────────────────────────

@tesoreria_bp.route("/api/tesoreria/movimientos/<int:mov_id>/solicitar-anulacion", methods=["POST"])
def movimiento_solicitar_anulacion(mov_id):
    """Solicitar anulación de un movimiento (soft-delete con autorización)."""
    movimiento = MovimientoCaja.query.get_or_404(mov_id)

    if movimiento.estado != "activo":
        return jsonify({"error": f"Movimiento ya está en estado '{movimiento.estado}'"}), 400

    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return jsonify({"error": "Motivo de anulación requerido"}), 400

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Sesión inválida, re-logueá"}), 401

    user_role = session.get("role", "")
    # Roles con permiso de anulación directa (sin paso de autorización)
    # caja requiere autorización de un admin/gerente
    auto_authorize = user_role in ("admin", "manager", "gerente")

    if auto_authorize:
        movimiento.estado = "anulado"
        movimiento.motivo_anulacion = motivo
        movimiento.anulado_por_id = user_id
        movimiento.autorizado_por_id = user_id
        movimiento.fecha_anulacion = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Movimiento anulado"})

    movimiento.estado = "pendiente_anulacion"
    movimiento.motivo_anulacion = motivo
    movimiento.anulado_por_id = user_id
    db.session.commit()

    return jsonify({"message": "Solicitud de anulación enviada, pendiente de autorización"})


@tesoreria_bp.route("/api/tesoreria/movimientos/<int:mov_id>/autorizar-anulacion", methods=["POST"])
def movimiento_autorizar_anulacion(mov_id):
    """Autorizar anulación — solo admin/manager/gerente."""
    user_role = session.get("role")
    if user_role not in ("admin", "manager", "gerente"):
        return jsonify({"error": "Solo un administrador puede autorizar anulaciones"}), 403

    movimiento = MovimientoCaja.query.get_or_404(mov_id)

    if movimiento.estado != "pendiente_anulacion":
        return jsonify({"error": "El movimiento no tiene solicitud de anulación pendiente"}), 400

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Sesión inválida"}), 401

    movimiento.estado = "anulado"
    movimiento.autorizado_por_id = user_id
    movimiento.fecha_anulacion = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Anulación autorizada"})


@tesoreria_bp.route("/api/tesoreria/movimientos/<int:mov_id>/rechazar-anulacion", methods=["POST"])
def movimiento_rechazar_anulacion(mov_id):
    """Rechazar solicitud de anulación — volver a activo."""
    user_role = session.get("role")
    if user_role not in ("admin", "manager", "gerente"):
        return jsonify({"error": "Solo un administrador puede rechazar anulaciones"}), 403

    movimiento = MovimientoCaja.query.get_or_404(mov_id)

    if movimiento.estado != "pendiente_anulacion":
        return jsonify({"error": "El movimiento no tiene solicitud pendiente"}), 400

    movimiento.estado = "activo"
    movimiento.motivo_anulacion = None
    movimiento.anulado_por_id = None
    db.session.commit()

    return jsonify({"message": "Solicitud de anulación rechazada, movimiento restaurado"})


@tesoreria_bp.route("/api/tesoreria/arqueos", methods=["GET"])
def arqueos_listar():
    """Listar arqueos de caja"""
    fecha = request.args.get("fecha")
    turno = request.args.get("turno")

    query = ArqueoCaja.query

    if fecha:
        query = query.filter(ArqueoCaja.fecha == datetime.strptime(fecha, "%Y-%m-%d").date())
    if turno:
        query = query.filter(ArqueoCaja.turno == turno)

    arqueos = query.order_by(ArqueoCaja.fecha.desc(), ArqueoCaja.turno).all()

    return jsonify({
        "arqueos": [{
            "id": a.id,
            "fecha": a.fecha.isoformat(),
            "turno": a.turno,
            "saldo_inicial": float(a.saldo_inicial),
            "ingresos_total": float(a.ingresos_total),
            "egresos_total": float(a.egresos_total),
            "saldo_final": float(a.saldo_final),
            "diferencia": float(a.diferencia),
            "usuario": a.usuario.username if a.usuario else None
        } for a in arqueos]
    })


@tesoreria_bp.route("/api/tesoreria/arqueos/exportar", methods=["GET"])
def arqueos_exportar():
    """Exportar arqueos de caja a Excel"""
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"error": "Pandas no instalado"}), 500

    fecha = request.args.get("fecha")
    turno = request.args.get("turno")

    query = ArqueoCaja.query

    if fecha:
        query = query.filter(ArqueoCaja.fecha == datetime.strptime(fecha, "%Y-%m-%d").date())
    if turno:
        query = query.filter(ArqueoCaja.turno == turno)

    arqueos = query.order_by(ArqueoCaja.fecha.desc(), ArqueoCaja.turno).all()

    data = []
    for a in arqueos:
        data.append({
            "Fecha": a.fecha,
            "Turno": a.turno,
            "Saldo Inicial": float(a.saldo_inicial),
            "Ingresos": float(a.ingresos_total),
            "Egresos": float(a.egresos_total),
            "Saldo Final": float(a.saldo_final),
            "Diferencia": float(a.diferencia),
            "Usuario": a.usuario.username if a.usuario else "",
            "Observaciones": a.observaciones or ""
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Arqueos", index=False)

    output.seek(0)
    fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tesoreria_arqueos_{fecha_actual}.xlsx"

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@tesoreria_bp.route("/api/tesoreria/arqueos", methods=["POST"])
def arqueos_crear():
    """Crear nuevo arqueo de caja con detalle por instrumento"""
    data = request.get_json()

    fecha_str = data.get("fecha")
    turno = data.get("turno")
    saldo_inicial = data.get("saldo_inicial", 0)
    saldo_final = data.get("saldo_final")
    detalles_input = data.get("detalles", [])  # [{instrumento_id, conteo_real}]

    usuario_id = session.get("user_id")
    if not usuario_id:
        return jsonify({"error": "Sesión expirada"}), 401

    if not fecha_str or not turno or saldo_final is None:
        return jsonify({"error": "Fecha, turno y saldo final requeridos"}), 400

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        saldo_inicial = Decimal(str(saldo_inicial)) if saldo_inicial else Decimal("0")
        saldo_final = Decimal(str(saldo_final))
    except Exception as e:
        return jsonify({"error": f"Datos numéricos inválidos: {str(e)}"}), 400

    if ArqueoCaja.query.filter_by(fecha=fecha, turno=turno).first():
        return jsonify({"error": "Ya existe arqueo para esa fecha y turno"}), 400

    usuario = User.query.get(usuario_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404

    try:
        # Rango horario según turno
        fecha_inicio = datetime.combine(fecha, time(0, 0, 0))
        if turno == "mañana":
            fecha_fin = datetime.combine(fecha, time(13, 59, 59))
        elif turno == "tarde":
            fecha_inicio = datetime.combine(fecha, time(14, 0, 0))
            fecha_fin = datetime.combine(fecha, time(21, 59, 59))
        else:  # noche
            fecha_inicio = datetime.combine(fecha, time(22, 0, 0))
            fecha_fin = datetime.combine(fecha + timedelta(days=1), time(5, 59, 59))

        # Filtro base: solo movimientos activos (excluir anulados/pendientes)
        base_filter = [
            MovimientoCaja.fecha_hora >= fecha_inicio,
            MovimientoCaja.fecha_hora <= fecha_fin,
            MovimientoCaja.estado == "activo",
        ]

        ingresos = db.session.query(db.func.sum(MovimientoCaja.monto)).filter(
            *base_filter, MovimientoCaja.tipo == "ingreso"
        ).scalar() or 0

        egresos = db.session.query(db.func.sum(MovimientoCaja.monto)).filter(
            *base_filter, MovimientoCaja.tipo == "egreso"
        ).scalar() or 0

        arqueo = ArqueoCaja(
            fecha=fecha,
            turno=turno,
            usuario_id=usuario_id,
            saldo_inicial=saldo_inicial,
            ingresos_total=Decimal(str(ingresos)),
            egresos_total=Decimal(str(egresos)),
            saldo_final=saldo_final,
            diferencia=saldo_final - (saldo_inicial + Decimal(str(ingresos)) - Decimal(str(egresos))),
            observaciones=data.get("observaciones")
        )
        db.session.add(arqueo)
        db.session.flush()  # obtener arqueo.id

        # Detalle por instrumento
        saldos_por_inst = db.session.query(
            MovimientoCaja.instrumento_id,
            db.func.sum(db.case(
                (MovimientoCaja.tipo == "ingreso", MovimientoCaja.monto), else_=0
            )) - db.func.sum(db.case(
                (MovimientoCaja.tipo == "egreso", MovimientoCaja.monto), else_=0
            ))
        ).filter(*base_filter).group_by(MovimientoCaja.instrumento_id).all()

        calc_map = {inst_id: float(saldo) for inst_id, saldo in saldos_por_inst}

        # Crear detalle: si hay detalles_input, usamos el conteo_real del usuario;
        # si no, generamos detalle con conteo_real = saldo_calculado (sin diferencia)
        instrumentos_activos = InstrumentoPago.query.filter_by(activo=True).all()
        conteos = {d["instrumento_id"]: float(d.get("conteo_real", 0)) for d in detalles_input}

        for inst in instrumentos_activos:
            saldo_calc = calc_map.get(inst.id, 0)
            conteo = conteos.get(inst.id, saldo_calc)  # default: sin diferencia
            detalle = ArqueoDetalle(
                arqueo_id=arqueo.id,
                instrumento_id=inst.id,
                conteo_real=Decimal(str(conteo)),
                saldo_calculado=Decimal(str(saldo_calc)),
                diferencia=Decimal(str(conteo)) - Decimal(str(saldo_calc))
            )
            db.session.add(detalle)

        db.session.commit()

        return jsonify({
            "message": "Arqueo creado",
            "arqueo": {
                "id": arqueo.id,
                "fecha": arqueo.fecha.isoformat(),
                "turno": arqueo.turno,
                "saldo_final": float(arqueo.saldo_final),
                "diferencia": float(arqueo.diferencia)
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear arqueo: {str(e)}"}), 500


@tesoreria_bp.route("/api/tesoreria/estado", methods=["GET"])
def estado_caja():
    """Obtener estado actual de caja por instrumento"""
    fecha = request.args.get("fecha", datetime.now().date().isoformat())

    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except:
        return jsonify({"error": "Fecha inválida"}), 400

    # Saldos por instrumento
    saldos = db.session.query(
        InstrumentoPago.nombre,
        db.func.sum(db.case((MovimientoCaja.tipo == "ingreso", MovimientoCaja.monto), else_=0)) -
        db.func.sum(db.case((MovimientoCaja.tipo == "egreso", MovimientoCaja.monto), else_=0))
    ).join(MovimientoCaja).filter(
        db.func.date(MovimientoCaja.fecha_hora) == fecha_obj,
        MovimientoCaja.estado != "anulado",
    ).group_by(InstrumentoPago.nombre).all()

    estado = {instrumento: float(saldo) for instrumento, saldo in saldos}

    return jsonify({
        "fecha": fecha,
        "estado_por_instrumento": estado,
        "total_caja": sum(estado.values())
    })


@tesoreria_bp.route("/api/tesoreria/arqueos/<int:id>/detalle", methods=["GET"])
def arqueo_detalle(id):
    """Obtener detalle por instrumento de un arqueo"""
    arqueo = ArqueoCaja.query.get_or_404(id)
    detalles = ArqueoDetalle.query.filter_by(arqueo_id=id).all()

    return jsonify({
        "arqueo_id": id,
        "detalles": [{
            "instrumento": d.instrumento.nombre if d.instrumento else "?",
            "conteo_real": float(d.conteo_real),
            "saldo_calculado": float(d.saldo_calculado),
            "diferencia": float(d.diferencia)
        } for d in detalles]
    })


# =============================================================================
# Endpoints para EDICIÓN DE ARQUEOS (Solo Admin)
# =============================================================================

def require_admin():
    """Helper para verificar que el usuario sea admin"""
    if "user" not in session:
        return jsonify({"error": "No autenticado"}), 401
    if session.get("role") not in ["admin", "manager", "gerente"]:
        return jsonify({"error": "Acceso denegado. Se requiere rol de administrador."}), 403
    return None


@tesoreria_bp.route("/api/tesoreria/arqueos/<int:id>", methods=["PUT"])
def arqueos_editar(id):
    """Editar arqueo de caja (solo admin, solo día actual, requiere justificación)"""
    # Verificar permisos admin
    auth_error = require_admin()
    if auth_error:
        return auth_error
    
    arqueo = ArqueoCaja.query.get_or_404(id)
    data = request.get_json()
    
    # Validar que sea del día actual
    if arqueo.fecha != date.today():
        return jsonify({"error": "Solo se pueden editar arqueos del día actual"}), 400
    
    # Validar justificación requerida
    justificacion = data.get("justificacion")
    if not justificacion or not justificacion.strip():
        return jsonify({"error": "Campo requerido: justificacion"}), 400
    
    try:
        # Guardar estado anterior
        campos_anteriores = {
            "saldo_inicial": float(arqueo.saldo_inicial),
            "saldo_final": float(arqueo.saldo_final),
            "observaciones": arqueo.observaciones
        }
        
        # Actualizar campos permitidos
        if "saldo_inicial" in data:
            arqueo.saldo_inicial = Decimal(str(data["saldo_inicial"]))
        if "saldo_final" in data:
            arqueo.saldo_final = Decimal(str(data["saldo_final"]))
        if "observaciones" in data:
            arqueo.observaciones = data["observaciones"]
        
        # Recalcular diferencia automáticamente
        saldo_esperado = arqueo.saldo_inicial + arqueo.ingresos_total - arqueo.egresos_total
        arqueo.diferencia = arqueo.saldo_final - saldo_esperado
        
        # Actualizar campos de auditoría
        usuario_id = session.get("user_id")
        arqueo.editado_por_id = usuario_id
        arqueo.fecha_edicion = datetime.utcnow()
        
        # Crear log de edición
        campos_nuevos = {
            "saldo_inicial": float(arqueo.saldo_inicial),
            "saldo_final": float(arqueo.saldo_final),
            "observaciones": arqueo.observaciones
        }
        
        log = LogArqueo(
            arqueo_id=id,
            usuario_id=usuario_id,
            campos_anteriores=campos_anteriores,
            campos_nuevos=campos_nuevos,
            justificacion=justificacion.strip()
        )
        
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Arqueo actualizado correctamente",
            "arqueo": {
                "id": arqueo.id,
                "saldo_inicial": float(arqueo.saldo_inicial),
                "saldo_final": float(arqueo.saldo_final),
                "diferencia": float(arqueo.diferencia),
                "observaciones": arqueo.observaciones
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar arqueo: {str(e)}"}), 500


@tesoreria_bp.route("/api/tesoreria/arqueos/<int:id>/logs", methods=["GET"])
def arqueos_logs(id):
    """Obtener historial de ediciones de un arqueo"""
    arqueo = ArqueoCaja.query.get_or_404(id)
    logs = LogArqueo.query.filter_by(arqueo_id=id).order_by(LogArqueo.fecha_edicion.desc()).all()
    
    return jsonify({
        "logs": [{
            "id": log.id,
            "fecha": log.fecha_edicion.isoformat(),
            "usuario": log.usuario.username if log.usuario else "Desconocido",
            "justificacion": log.justificacion,
            "cambios": {
                "anterior": log.campos_anteriores,
                "nuevo": log.campos_nuevos
            }
        } for log in logs]
    })
