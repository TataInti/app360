from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, request, jsonify, render_template

from models import (
    ArqueoCaja,
    InstrumentoPago,
    MovimientoCaja,
    User,
    db,
)
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

    query = MovimientoCaja.query

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
            "referencia": m.referencia,
            "cliente_proveedor": m.cliente_proveedor,
            "usuario": m.usuario.username if m.usuario else None
        } for m in movimientos.items],
        "total": movimientos.total,
        "pages": movimientos.pages,
        "current_page": movimientos.page
    })


@tesoreria_bp.route("/api/tesoreria/movimientos", methods=["POST"])
def movimientos_crear():
    """Crear nuevo movimiento de caja"""
    data = request.get_json()

    tipo = data.get("tipo")
    monto = data.get("monto")
    descripcion = data.get("descripcion")
    instrumento_id = data.get("instrumento_id")
    usuario_id = data.get("usuario_id", 1)  # Default admin user

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


@tesoreria_bp.route("/api/tesoreria/arqueos", methods=["POST"])
def arqueos_crear():
    """Crear nuevo arqueo de caja"""
    data = request.get_json()

    fecha_str = data.get("fecha")
    turno = data.get("turno")
    saldo_inicial = data.get("saldo_inicial", 0)
    saldo_final = data.get("saldo_final")
    usuario_id = data.get("usuario_id", 1)

    if not fecha_str or not turno or saldo_final is None:
        return jsonify({"error": "Fecha, turno y saldo final requeridos"}), 400

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        saldo_inicial = Decimal(str(saldo_inicial))
        saldo_final = Decimal(str(saldo_final))
    except:
        return jsonify({"error": "Datos numéricos inválidos"}), 400

    # Verificar que no exista arqueo para esa fecha y turno
    if ArqueoCaja.query.filter_by(fecha=fecha, turno=turno).first():
        return jsonify({"error": "Ya existe arqueo para esa fecha y turno"}), 400

    # Calcular ingresos y egresos del día/turno
    fecha_inicio = datetime.combine(fecha, datetime.min.time())
    if turno == "mañana":
        fecha_fin = datetime.combine(fecha, datetime(23, 59, 59).time().replace(hour=13, minute=59, second=59))
    elif turno == "tarde":
        fecha_inicio = datetime.combine(fecha, datetime.min.time().replace(hour=14))
        fecha_fin = datetime.combine(fecha, datetime(23, 59, 59).time().replace(hour=21, minute=59, second=59))
    else:  # noche
        fecha_inicio = datetime.combine(fecha, datetime.min.time().replace(hour=22))
        fecha_fin = datetime.combine(fecha + timedelta(days=1), datetime.min.time().replace(hour=5, minute=59, second=59))

    ingresos = db.session.query(db.func.sum(MovimientoCaja.monto)).filter(
        MovimientoCaja.fecha_hora >= fecha_inicio,
        MovimientoCaja.fecha_hora <= fecha_fin,
        MovimientoCaja.tipo == "ingreso"
    ).scalar() or 0

    egresos = db.session.query(db.func.sum(MovimientoCaja.monto)).filter(
        MovimientoCaja.fecha_hora >= fecha_inicio,
        MovimientoCaja.fecha_hora <= fecha_fin,
        MovimientoCaja.tipo == "egreso"
    ).scalar() or 0

    arqueo = ArqueoCaja(
        fecha=fecha,
        turno=turno,
        usuario_id=usuario_id,
        saldo_inicial=saldo_inicial,
        ingresos_total=Decimal(str(ingresos)),
        egresos_total=Decimal(str(egresos)),
        saldo_final=saldo_final,
        diferencia=saldo_final - (saldo_inicial + Decimal(str(ingresos)) - Decimal(str(egresos)))
    )

    db.session.add(arqueo)
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
        db.func.date(MovimientoCaja.fecha_hora) == fecha_obj
    ).group_by(InstrumentoPago.nombre).all()

    estado = {instrumento: float(saldo) for instrumento, saldo in saldos}

    return jsonify({
        "fecha": fecha,
        "estado_por_instrumento": estado,
        "total_caja": sum(estado.values())
    })