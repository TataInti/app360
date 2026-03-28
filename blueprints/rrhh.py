from datetime import datetime, date, timedelta
from decimal import Decimal
import io

from flask import Blueprint, request, jsonify, send_file, render_template, flash, redirect, url_for

from models import (
    Adelanto,
    Asistencia,
    Employee,
    Turno,
    User,
    db,
)
from models.rrhh import LiquidacionSueldo, TurnoDia
from security import protect_blueprint

rrhh_bp = Blueprint("rrhh", __name__)

protect_blueprint(rrhh_bp, "rrhh")


# RUTAS WEB
@rrhh_bp.route("/rrhh", methods=["GET"])
def rrhh_panel():
    """Panel principal de RRHH"""
    return render_template("rrhh_panel.html")


@rrhh_bp.route("/rrhh/empleados", methods=["GET", "POST"])
def rrhh_empleados():
    """Vista de empleados"""
    from models.hr.employee import Employee
    from models.core import Location
    
    if request.method == "POST":
        try:
            data = request.form
            full_name = data.get("full_name", "").strip()
            # Separar nombre completo en first_name y last_name
            parts = full_name.split(" ", 1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""
            
            # Manejar rol: si es "Otro", usar el valor de role_otro
            role = data.get("role", "").strip()
            if role == "Otro":
                role = data.get("role_otro", "").strip() or "Otro"
            
            nuevo_empleado = Employee(
                first_name=first_name,
                last_name=last_name,
                position=role,
                email=data.get("email"),
                location_id=int(data.get("location_id")) if data.get("location_id") else None,
                is_active=data.get("active") == "on"
            )
            db.session.add(nuevo_empleado)
            db.session.commit()
            flash("Empleado creado exitosamente", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al crear empleado: {str(e)}", "danger")
        return redirect(url_for("rrhh.rrhh_empleados"))
    
    # GET: cargar empleados y ubicaciones
    employees = Employee.query.all()
    locations = Location.query.all()
    return render_template("rrhh_empleados.html", employees=employees, locations=locations)


@rrhh_bp.route("/rrhh/dotacion", methods=["GET"])
def rrhh_dotacion():
    """Vista de dotación"""
    return render_template("rrhh_dotacion.html")


@rrhh_bp.route("/rrhh/adelantos", methods=["GET"])
def rrhh_adelantos():
    """Vista de adelantos de salario"""
    return render_template("rrhh_adelantos.html")


@rrhh_bp.route("/rrhh/liquidaciones", methods=["GET"])
def rrhh_liquidaciones():
    """Vista de liquidación de sueldos"""
    return render_template("rrhh_liquidaciones.html")


@rrhh_bp.route("/rrhh/ausentismo", methods=["GET"])
def rrhh_ausentismo():
    """Vista de ausentismo"""
    return render_template("rrhh_ausentismo.html")


# Endpoints para Turnos

DIAS_SEMANA_NOMBRES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _serializar_turno_dia(td):
    return {
        "dia_semana": td.dia_semana,
        "nombre_dia": DIAS_SEMANA_NOMBRES[td.dia_semana],
        "activo": td.activo,
        "es_cortado": td.es_cortado,
        "hora_inicio_1": td.hora_inicio_1.strftime("%H:%M") if td.hora_inicio_1 else None,
        "hora_fin_1": td.hora_fin_1.strftime("%H:%M") if td.hora_fin_1 else None,
        "hora_inicio_2": td.hora_inicio_2.strftime("%H:%M") if td.hora_inicio_2 else None,
        "hora_fin_2": td.hora_fin_2.strftime("%H:%M") if td.hora_fin_2 else None,
    }


@rrhh_bp.route("/api/rrhh/turnos", methods=["GET"])
def turnos_listar():
    """Listar turnos activos"""
    turnos = Turno.query.filter_by(activo=True).order_by(Turno.nombre).all()

    return jsonify({
        "turnos": [{
            "id": t.id,
            "nombre": t.nombre,
            "descripcion": t.descripcion,
            "dias": [_serializar_turno_dia(d) for d in t.dias],
        } for t in turnos]
    })


@rrhh_bp.route("/api/rrhh/turnos", methods=["POST"])
def turnos_crear():
    """Crear nuevo turno"""
    data = request.get_json()

    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"error": "Campo requerido: nombre"}), 400

    # Verificar que no exista
    existente = Turno.query.filter_by(nombre=nombre).first()
    if existente:
        return jsonify({"error": "Ya existe un turno con ese nombre"}), 400

    turno = Turno(
        nombre=nombre,
        descripcion=data.get("descripcion", ""),
    )

    db.session.add(turno)
    db.session.flush()  # para obtener turno.id

    # Crear 7 días con valores por defecto (inactivos)
    for dia in range(7):
        td = TurnoDia(turno_id=turno.id, dia_semana=dia, activo=False)
        db.session.add(td)

    db.session.commit()

    return jsonify({
        "message": "Turno creado",
        "turno": {
            "id": turno.id,
            "nombre": turno.nombre,
        }
    }), 201


@rrhh_bp.route("/api/rrhh/turnos/<int:turno_id>", methods=["DELETE"])
def turnos_eliminar(turno_id):
    """Desactivar turno"""
    turno = Turno.query.get_or_404(turno_id)
    turno.activo = False
    db.session.commit()

    return jsonify({"message": "Turno desactivado"})


@rrhh_bp.route("/api/rrhh/turnos/<int:turno_id>/dias", methods=["GET"])
def turno_dias_listar(turno_id):
    """Listar configuración de días de un turno"""
    turno = Turno.query.get_or_404(turno_id)
    return jsonify({
        "turno_id": turno.id,
        "nombre": turno.nombre,
        "dias": [_serializar_turno_dia(d) for d in turno.dias],
    })


@rrhh_bp.route("/api/rrhh/turnos/<int:turno_id>/dias", methods=["PUT"])
def turno_dias_actualizar(turno_id):
    """Actualizar configuración de días de un turno (reemplaza todos)"""
    turno = Turno.query.get_or_404(turno_id)
    data = request.get_json() or {}
    dias_data = data.get("dias", [])

    if not isinstance(dias_data, list) or len(dias_data) != 7:
        return jsonify({"error": "Se requieren exactamente 7 días (0=lunes .. 6=domingo)"}), 400

    # Indexar días existentes
    dias_existentes = {d.dia_semana: d for d in turno.dias}

    for dia_info in dias_data:
        dia_semana = dia_info.get("dia_semana")
        if dia_semana is None or not (0 <= dia_semana <= 6):
            return jsonify({"error": f"dia_semana inválido: {dia_semana}"}), 400

        activo = bool(dia_info.get("activo", False))
        es_cortado = bool(dia_info.get("es_cortado", False))

        hora_inicio_1 = None
        hora_fin_1 = None
        hora_inicio_2 = None
        hora_fin_2 = None

        if activo:
            try:
                hora_inicio_1 = datetime.strptime(dia_info["hora_inicio_1"], "%H:%M").time()
                hora_fin_1 = datetime.strptime(dia_info["hora_fin_1"], "%H:%M").time()
                if es_cortado:
                    hora_inicio_2 = datetime.strptime(dia_info["hora_inicio_2"], "%H:%M").time()
                    hora_fin_2 = datetime.strptime(dia_info["hora_fin_2"], "%H:%M").time()
            except (KeyError, ValueError, TypeError):
                nombre_dia = DIAS_SEMANA_NOMBRES[dia_semana]
                return jsonify({"error": f"Horarios inválidos para {nombre_dia}"}), 400

        if dia_semana in dias_existentes:
            td = dias_existentes[dia_semana]
        else:
            td = TurnoDia(turno_id=turno.id, dia_semana=dia_semana)
            db.session.add(td)

        td.activo = activo
        td.es_cortado = es_cortado
        td.hora_inicio_1 = hora_inicio_1
        td.hora_fin_1 = hora_fin_1
        td.hora_inicio_2 = hora_inicio_2
        td.hora_fin_2 = hora_fin_2

    db.session.commit()

    return jsonify({
        "message": "Horarios actualizados",
        "dias": [_serializar_turno_dia(d) for d in turno.dias],
    })


# Endpoints para Asistencia

@rrhh_bp.route("/api/rrhh/asistencia", methods=["GET"])
def asistencia_listar():
    """Listar asistencia con filtros"""
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    empleado_id = request.args.get("empleado_id")
    turno_id = request.args.get("turno_id")
    estado = request.args.get("estado")
    limite = request.args.get("limite", 100, type=int)

    query = Asistencia.query

    # Aplicar filtros
    if fecha_desde:
        try:
            fecha_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(Asistencia.fecha >= fecha_desde)
        except ValueError:
            return jsonify({"error": "Formato de fecha_desde inválido"}), 400

    if fecha_hasta:
        try:
            fecha_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(Asistencia.fecha <= fecha_hasta)
        except ValueError:
            return jsonify({"error": "Formato de fecha_hasta inválido"}), 400

    if empleado_id:
        query = query.filter(Asistencia.empleado_id == empleado_id)

    if turno_id:
        query = query.filter(Asistencia.turno_id == turno_id)

    if estado:
        query = query.filter(Asistencia.estado == estado)

    # Ordenar por fecha descendente
    asistencias = query.order_by(Asistencia.fecha.desc()).limit(limite).all()

    return jsonify({
        "asistencia": [{
            "id": a.id,
            "fecha": a.fecha.isoformat(),
            "empleado": {
                "id": a.empleado.id,
                "nombre": a.empleado.name
            },
            "turno": {
                "id": a.turno.id,
                "nombre": a.turno.nombre
            },
            "hora_entrada": a.hora_entrada.isoformat() if a.hora_entrada else None,
            "hora_salida": a.hora_salida.isoformat() if a.hora_salida else None,
            "horas_trabajadas": float(a.horas_trabajadas) if a.horas_trabajadas else None,
            "estado": a.estado,
            "notas": a.notas
        } for a in asistencias]
    })


@rrhh_bp.route("/api/rrhh/asistencia", methods=["POST"])
def asistencia_registrar():
    """Registrar asistencia"""
    data = request.get_json()

    required_fields = ["empleado_id", "turno_id", "fecha"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    # Verificar que existan empleado y turno
    empleado = Employee.query.get(data["empleado_id"])
    if not empleado or not empleado.is_active:
        return jsonify({"error": "Empleado no encontrado o inactivo"}), 404

    turno = Turno.query.get(data["turno_id"])
    if not turno or not turno.activo:
        return jsonify({"error": "Turno no encontrado o inactivo"}), 404

    # Parsear fecha
    try:
        fecha = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    # Verificar que no exista asistencia para este empleado/fecha
    existente = Asistencia.query.filter_by(
        empleado_id=data["empleado_id"],
        fecha=fecha
    ).first()
    if existente:
        return jsonify({"error": "Ya existe registro de asistencia para este empleado en esta fecha"}), 400

    # Parsear horas opcionales
    hora_entrada = None
    hora_salida = None
    horas_trabajadas = None

    if data.get("hora_entrada"):
        try:
            hora_entrada = datetime.fromisoformat(data["hora_entrada"])
        except ValueError:
            return jsonify({"error": "Formato de hora_entrada inválido"}), 400

    if data.get("hora_salida"):
        try:
            hora_salida = datetime.fromisoformat(data["hora_salida"])
        except ValueError:
            return jsonify({"error": "Formato de hora_salida inválido"}), 400

    # Calcular horas trabajadas si ambas horas están presentes
    if hora_entrada and hora_salida:
        diferencia = hora_salida - hora_entrada
        horas_trabajadas = round(diferencia.total_seconds() / 3600, 2)

    # Determinar estado
    estado = data.get("estado", "presente")
    estados_validos = ["presente", "ausente", "llegada_tarde", "salida_temprana"]
    if estado not in estados_validos:
        return jsonify({"error": f"Estado inválido. Valores permitidos: {estados_validos}"}), 400

    asistencia = Asistencia(
        empleado_id=data["empleado_id"],
        turno_id=data["turno_id"],
        fecha=fecha,
        hora_entrada=hora_entrada,
        hora_salida=hora_salida,
        horas_trabajadas=horas_trabajadas,
        estado=estado,
        notas=data.get("notas")
    )

    db.session.add(asistencia)
    db.session.commit()

    return jsonify({
        "message": "Asistencia registrada",
        "asistencia": {
            "id": asistencia.id,
            "fecha": asistencia.fecha.isoformat(),
            "empleado": asistencia.empleado.name,
            "turno": asistencia.turno.nombre,
            "estado": asistencia.estado
        }
    }), 201


@rrhh_bp.route("/api/rrhh/asistencia/<int:asistencia_id>", methods=["PUT"])
def asistencia_actualizar(asistencia_id):
    """Actualizar registro de asistencia"""
    asistencia = Asistencia.query.get_or_404(asistencia_id)
    data = request.get_json()

    # Actualizar campos opcionales
    if "hora_entrada" in data:
        if data["hora_entrada"]:
            try:
                asistencia.hora_entrada = datetime.fromisoformat(data["hora_entrada"])
            except ValueError:
                return jsonify({"error": "Formato de hora_entrada inválido"}), 400
        else:
            asistencia.hora_entrada = None

    if "hora_salida" in data:
        if data["hora_salida"]:
            try:
                asistencia.hora_salida = datetime.fromisoformat(data["hora_salida"])
            except ValueError:
                return jsonify({"error": "Formato de hora_salida inválido"}), 400
        else:
            asistencia.hora_salida = None

    if "estado" in data:
        estados_validos = ["presente", "ausente", "llegada_tarde", "salida_temprana"]
        if data["estado"] not in estados_validos:
            return jsonify({"error": f"Estado inválido. Valores permitidos: {estados_validos}"}), 400
        asistencia.estado = data["estado"]

    if "notas" in data:
        asistencia.notas = data["notas"]

    # Recalcular horas trabajadas
    if asistencia.hora_entrada and asistencia.hora_salida:
        diferencia = asistencia.hora_salida - asistencia.hora_entrada
        asistencia.horas_trabajadas = round(diferencia.total_seconds() / 3600, 2)
    else:
        asistencia.horas_trabajadas = None

    db.session.commit()

    return jsonify({"message": "Asistencia actualizada"})


@rrhh_bp.route("/api/rrhh/ausentismo", methods=["GET"])
def ausentismo_listar():
    """Listar ausentismo y llegadas tarde"""
    limite = request.args.get("limite", 200, type=int)
    query = Asistencia.query.filter(Asistencia.estado.in_(["ausente", "llegada_tarde"]))
    registros = query.order_by(Asistencia.fecha.desc()).limit(limite).all()

    return jsonify({
        "registros": [{
            "id": r.id,
            "fecha": r.fecha.isoformat(),
            "empleado": {
                "id": r.empleado.id,
                "nombre": r.empleado.name
            },
            "estado": r.estado,
            "motivo": r.motivo,
            "justificado": bool(r.justificado),
            "minutos_tarde": r.minutos_tarde
        } for r in registros]
    })


@rrhh_bp.route("/api/rrhh/ausentismo", methods=["POST"])
def ausentismo_crear():
    """Registrar ausentismo o llegada tarde"""
    data = request.get_json() or {}

    required_fields = ["empleado_id", "fecha", "estado"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    estado = data.get("estado")
    if estado not in ["ausente", "llegada_tarde"]:
        return jsonify({"error": "Estado inválido"}), 400

    empleado = Employee.query.get(data["empleado_id"])
    if not empleado or not empleado.is_active:
        return jsonify({"error": "Empleado no encontrado o inactivo"}), 404

    try:
        fecha = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    minutos_tarde = data.get("minutos_tarde")
    if estado == "llegada_tarde":
        try:
            minutos_tarde = int(minutos_tarde)
        except (TypeError, ValueError):
            return jsonify({"error": "Minutos tarde inválido"}), 400
        if minutos_tarde <= 0:
            return jsonify({"error": "Minutos tarde debe ser mayor a cero"}), 400
    else:
        minutos_tarde = None

    turno_id = data.get("turno_id")
    if turno_id:
        turno = Turno.query.get(turno_id)
        if not turno or not turno.activo:
            return jsonify({"error": "Turno no encontrado o inactivo"}), 404
        turno_id = turno.id
    else:
        turno = Turno.query.filter_by(activo=True).order_by(Turno.nombre).first()
        if not turno:
            return jsonify({"error": "Debe existir al menos un turno activo"}), 400
        turno_id = turno.id

    registro = Asistencia(
        empleado_id=empleado.id,
        turno_id=turno_id,
        fecha=fecha,
        estado=estado,
        motivo=data.get("motivo"),
        justificado=bool(data.get("justificado")),
        minutos_tarde=minutos_tarde,
        notas=data.get("notas")
    )

    db.session.add(registro)
    db.session.commit()

    return jsonify({"message": "Registro creado"}), 201


# Endpoints para Adelantos

@rrhh_bp.route("/api/rrhh/empleados", methods=["GET"])
def empleados_listar():
    """Listar empleados activos"""
    empleados = Employee.query.filter_by(is_active=True).all()
    
    return jsonify({
        "employees": [{
            "id": e.id,
            "name": e.name,
            "email": e.email,
            "position": e.position,
            "department": e.department,
            "is_active": e.is_active
        } for e in empleados]
    })


@rrhh_bp.route("/api/rrhh/adelantos", methods=["GET"])
def adelantos_listar():
    """Listar adelantos con filtros"""
    empleado_id = request.args.get("empleado_id")
    tipo = request.args.get("tipo")
    aprobado = request.args.get("aprobado")
    pagado = request.args.get("pagado")
    liquidado = request.args.get("liquidado")
    mes_aplicacion = request.args.get("mes_aplicacion")
    limite = request.args.get("limite", 100, type=int)

    query = Adelanto.query

    # Aplicar filtros
    if empleado_id:
        query = query.filter(Adelanto.empleado_id == empleado_id)
    
    if tipo:
        query = query.filter(Adelanto.tipo == tipo)
    
    if mes_aplicacion:
        query = query.filter(Adelanto.mes_aplicacion == mes_aplicacion)

    if aprobado is not None:
        aprobado_bool = aprobado.lower() == "true"
        query = query.filter(Adelanto.aprobado == aprobado_bool)

    if pagado is not None:
        pagado_bool = pagado.lower() == "true"
        query = query.filter(Adelanto.pagado == pagado_bool)
    
    if liquidado is not None:
        liquidado_bool = liquidado.lower() == "true"
        query = query.filter(Adelanto.liquidado == liquidado_bool)

    # Ordenar por fecha descendente
    adelantos = query.order_by(Adelanto.fecha_solicitud.desc()).limit(limite).all()

    return jsonify({
        "adelantos": [{
            "id": a.id,
            "fecha_solicitud": a.fecha_solicitud.isoformat(),
            "empleado": {
                "id": a.empleado.id,
                "nombre": a.empleado.name
            },
            "tipo": a.tipo,
            "monto": float(a.monto),
            "concepto": a.concepto,
            "mes_aplicacion": a.mes_aplicacion,
            "cantidad_cuotas": a.cantidad_cuotas,
            "interes_porcentaje": float(a.interes_porcentaje) if a.interes_porcentaje else None,
            "cuotas_pagadas": a.cuotas_pagadas,
            "aprobado": a.aprobado,
            "fecha_aprobacion": a.fecha_aprobacion.isoformat() if a.fecha_aprobacion else None,
            "pagado": a.pagado,
            "fecha_pago": a.fecha_pago.isoformat() if a.fecha_pago else None,
            "liquidado": a.liquidado,
            "fecha_liquidacion": a.fecha_liquidacion.isoformat() if a.fecha_liquidacion else None,
            "aprobado_por": a.aprobado_por.username if a.aprobado_por else None,
            "saldo_pendiente": float(a.saldo_pendiente())
        } for a in adelantos]
    })


@rrhh_bp.route("/api/rrhh/adelantos", methods=["POST"])
def adelantos_solicitar():
    """Solicitar adelanto o préstamo"""
    data = request.get_json()

    required_fields = ["empleado_id", "tipo", "monto", "concepto"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400
    
    tipo = data["tipo"]
    if tipo not in ["adelanto_efectivo", "adelanto_mercaderia", "prestamo"]:
        return jsonify({"error": "Tipo inválido"}), 400

    # Verificar empleado
    empleado = Employee.query.get(data["empleado_id"])
    if not empleado or not empleado.is_active:
        return jsonify({"error": "Empleado no encontrado o inactivo"}), 404

    try:
        monto = Decimal(str(data["monto"]))
        if monto <= 0:
            return jsonify({"error": "Monto debe ser mayor a cero"}), 400
    except:
        return jsonify({"error": "Monto inválido"}), 400
    
    # Validar campos según tipo
    if tipo in ["adelanto_efectivo", "adelanto_mercaderia"]:
        if not data.get("mes_aplicacion"):
            return jsonify({"error": "Mes de aplicación requerido para adelantos"}), 400
    
    if tipo == "prestamo":
        if not data.get("cantidad_cuotas") or not data.get("interes_porcentaje"):
            return jsonify({"error": "Cantidad de cuotas e interés requeridos para préstamos"}), 400
        
        try:
            cantidad_cuotas = int(data["cantidad_cuotas"])
            if cantidad_cuotas <= 0:
                return jsonify({"error": "Cantidad de cuotas debe ser mayor a cero"}), 400
        except:
            return jsonify({"error": "Cantidad de cuotas inválida"}), 400

    # Sanitizar campos numéricos opcionales (el frontend puede enviar "" en vez de null)
    raw_cuotas = data.get("cantidad_cuotas")
    cantidad_cuotas = int(raw_cuotas) if raw_cuotas not in (None, "") else None
    raw_interes = data.get("interes_porcentaje")
    interes_porcentaje = Decimal(str(raw_interes)) if raw_interes not in (None, "") else None

    adelanto = Adelanto(
        empleado_id=data["empleado_id"],
        tipo=tipo,
        monto=monto,
        concepto=data["concepto"],
        mes_aplicacion=data.get("mes_aplicacion") or None,
        cantidad_cuotas=cantidad_cuotas,
        interes_porcentaje=interes_porcentaje,
    )

    db.session.add(adelanto)
    db.session.commit()

    return jsonify({
        "message": f"{tipo.replace('_', ' ').title()} solicitado",
        "adelanto": {
            "id": adelanto.id,
            "tipo": adelanto.tipo,
            "monto": float(adelanto.monto),
            "concepto": adelanto.concepto,
            "aprobado": adelanto.aprobado
        }
    }), 201


@rrhh_bp.route("/api/rrhh/adelantos/<int:adelanto_id>/aprobar", methods=["POST"])
def adelantos_aprobar(adelanto_id):
    """Aprobar adelanto"""
    from flask import session as flask_session

    adelanto = Adelanto.query.get_or_404(adelanto_id)

    if adelanto.aprobado:
        return jsonify({"error": "Adelanto ya está aprobado"}), 400

    # Obtener usuario aprobador desde sesión
    usuario_id = flask_session.get("user_id")
    if not usuario_id:
        return jsonify({"error": "Sesión inválida, re-logueá"}), 401

    usuario = User.query.get(usuario_id)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404

    adelanto.aprobado = True
    adelanto.fecha_aprobacion = datetime.utcnow()
    adelanto.aprobado_por_id = usuario_id

    db.session.commit()

    return jsonify({"message": "Adelanto aprobado"})


@rrhh_bp.route("/api/rrhh/adelantos/<int:adelanto_id>/pagar", methods=["POST"])
def adelantos_pagar(adelanto_id):
    """Marcar adelanto como pagado"""
    adelanto = Adelanto.query.get_or_404(adelanto_id)

    if not adelanto.aprobado:
        return jsonify({"error": "Adelanto debe estar aprobado antes de pagar"}), 400

    if adelanto.pagado:
        return jsonify({"error": "Adelanto ya está pagado"}), 400

    adelanto.pagado = True
    adelanto.fecha_pago = datetime.utcnow()

    db.session.commit()

    return jsonify({"message": "Adelanto marcado como pagado"})


# Endpoints para Reportes y Estadísticas

@rrhh_bp.route("/api/rrhh/reportes/asistencia", methods=["GET"])
def reportes_asistencia():
    """Reporte de asistencia por período"""
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    if not fecha_desde or not fecha_hasta:
        return jsonify({"error": "Se requieren fecha_desde y fecha_hasta"}), 400

    try:
        fecha_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
        fecha_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    # Obtener estadísticas
    total_asistencias = Asistencia.query.filter(
        Asistencia.fecha >= fecha_desde,
        Asistencia.fecha <= fecha_hasta
    ).count()

    presentes = Asistencia.query.filter(
        Asistencia.fecha >= fecha_desde,
        Asistencia.fecha <= fecha_hasta,
        Asistencia.estado == 'presente'
    ).count()

    ausentes = Asistencia.query.filter(
        Asistencia.fecha >= fecha_desde,
        Asistencia.fecha <= fecha_hasta,
        Asistencia.estado == 'ausente'
    ).count()

    llegadas_tarde = Asistencia.query.filter(
        Asistencia.fecha >= fecha_desde,
        Asistencia.fecha <= fecha_hasta,
        Asistencia.estado == 'llegada_tarde'
    ).count()

    # Horas trabajadas totales
    from sqlalchemy import func
    result = db.session.query(func.sum(Asistencia.horas_trabajadas)).filter(
        Asistencia.fecha >= fecha_desde,
        Asistencia.fecha <= fecha_hasta,
        Asistencia.horas_trabajadas.isnot(None)
    ).scalar()

    horas_totales = float(result) if result else 0

    return jsonify({
        "periodo": {
            "desde": fecha_desde.isoformat(),
            "hasta": fecha_hasta.isoformat()
        },
        "estadisticas": {
            "total_asistencias": total_asistencias,
            "presentes": presentes,
            "ausentes": ausentes,
            "llegadas_tarde": llegadas_tarde,
            "horas_trabajadas_totales": horas_totales,
            "tasa_asistencia": (presentes / total_asistencias * 100) if total_asistencias > 0 else 0
        }
    })


@rrhh_bp.route("/api/rrhh/exportar", methods=["GET"])
def rrhh_exportar():
    """Exportar datos de RRHH a Excel"""
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"error": "Pandas no instalado"}), 500

    tipo = request.args.get("tipo", "asistencia")  # asistencia, adelantos
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    if tipo == "asistencia":
        query = Asistencia.query
        if fecha_desde:
            fecha_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(Asistencia.fecha >= fecha_desde)
        if fecha_hasta:
            fecha_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(Asistencia.fecha <= fecha_hasta)

        registros = query.order_by(Asistencia.fecha.desc()).all()

        data = []
        for a in registros:
            data.append({
                "Fecha": a.fecha,
                "Empleado": a.empleado.name,
                "Turno": a.turno.nombre,
                "Hora Entrada": a.hora_entrada,
                "Hora Salida": a.hora_salida,
                "Horas Trabajadas": float(a.horas_trabajadas) if a.horas_trabajadas else "",
                "Estado": a.estado,
                "Notas": a.notas or ""
            })

        filename = "asistencia_rrhh.xlsx"

    elif tipo == "adelantos":
        query = Adelanto.query
        if fecha_desde:
            fecha_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(Adelanto.fecha_solicitud >= fecha_desde)
        if fecha_hasta:
            fecha_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(Adelanto.fecha_solicitud <= fecha_hasta)

        registros = query.order_by(Adelanto.fecha_solicitud.desc()).all()

        data = []
        for a in registros:
            data.append({
                "Fecha Solicitud": a.fecha_solicitud,
                "Empleado": a.empleado.name,
                "Tipo": a.tipo,
                "Monto": float(a.monto),
                "Concepto": a.concepto or "",
                "Mes Aplicación": a.mes_aplicacion or "",
                "Cuotas": f"{a.cuotas_pagadas}/{a.cantidad_cuotas}" if a.tipo == "prestamo" else "",
                "Aprobado": "Sí" if a.aprobado else "No",
                "Liquidado": "Sí" if a.liquidado else "No",
                "Aprobado Por": a.aprobado_por.username if a.aprobado_por else ""
            })

        filename = "adelantos_rrhh.xlsx"

    else:
        return jsonify({"error": "Tipo de exportación inválido"}), 400

    df = pd.DataFrame(data)

    # Crear archivo Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='RRHH', index=False)

    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# === ENDPOINTS DE LIQUIDACIONES ===

@rrhh_bp.route("/api/rrhh/liquidaciones/preview/<periodo>", methods=["GET"])
def liquidaciones_preview(periodo):
    """Previsualizar liquidaciones para un periodo (YYYY-MM)"""
    # Validar formato de periodo
    if not periodo or len(periodo) != 7:
        return jsonify({"error": "Formato de periodo inválido (usar YYYY-MM)"}), 400
    
    empleados = Employee.query.filter_by(is_active=True).all()
    preview = []

    for empleado in empleados:
        # Obtener adelantos no liquidados del periodo
        adelantos_efectivo = Adelanto.query.filter_by(
            empleado_id=empleado.id,
            tipo="adelanto_efectivo",
            mes_aplicacion=periodo,
            aprobado=True,
            liquidado=False
        ).all()
        
        adelantos_mercaderia = Adelanto.query.filter_by(
            empleado_id=empleado.id,
            tipo="adelanto_mercaderia",
            mes_aplicacion=periodo,
            aprobado=True,
            liquidado=False
        ).all()
        
        # Obtener préstamos activos
        prestamos = Adelanto.query.filter_by(
            empleado_id=empleado.id,
            tipo="prestamo",
            aprobado=True,
            liquidado=False
        ).all()

        # Calcular descuentos
        descuento_efectivo = sum(a.monto for a in adelantos_efectivo)
        descuento_mercaderia = sum(a.monto for a in adelantos_mercaderia)
        descuento_cuota = sum(p.calcular_monto_cuota() for p in prestamos)
        
        sueldo_base = empleado.salary or Decimal('0')
        sueldo_neto = sueldo_base - descuento_efectivo - descuento_mercaderia - descuento_cuota

        preview.append({
            "empleado_id": empleado.id,
            "empleado_nombre": empleado.name,
            "sueldo_base": float(sueldo_base),
            "descuento_adelanto_efectivo": float(descuento_efectivo),
            "descuento_adelanto_mercaderia": float(descuento_mercaderia),
            "descuento_cuota_prestamo": float(descuento_cuota),
            "sueldo_neto": float(sueldo_neto),
            "adelantos_efectivo_count": len(adelantos_efectivo),
            "adelantos_mercaderia_count": len(adelantos_mercaderia),
            "prestamos_count": len(prestamos)
        })
    
    return jsonify({"periodo": periodo, "liquidaciones": preview})


@rrhh_bp.route("/api/rrhh/liquidaciones", methods=["POST"])
def liquidaciones_generar():
    """Generar liquidaciones para un periodo"""
    data = request.get_json()
    
    if not data.get("periodo"):
        return jsonify({"error": "Periodo requerido"}), 400
    
    periodo = data["periodo"]
    
    # Validar formato
    if len(periodo) != 7:
        return jsonify({"error": "Formato de periodo inválido (usar YYYY-MM)"}), 400
    
    # Verificar si ya existe liquidación para este periodo
    liquidacion_existente = LiquidacionSueldo.query.filter_by(periodo=periodo).first()
    if liquidacion_existente:
        return jsonify({"error": f"Ya existe liquidación para el periodo {periodo}"}), 400
    
    empleados = Employee.query.filter_by(is_active=True).all()
    liquidaciones_creadas = []
    
    for empleado in empleados:
        # Obtener adelantos no liquidados
        adelantos_efectivo = Adelanto.query.filter_by(
            empleado_id=empleado.id,
            tipo="adelanto_efectivo",
            mes_aplicacion=periodo,
            aprobado=True,
            liquidado=False
        ).all()
        
        adelantos_mercaderia = Adelanto.query.filter_by(
            empleado_id=empleado.id,
            tipo="adelanto_mercaderia",
            mes_aplicacion=periodo,
            aprobado=True,
            liquidado=False
        ).all()
        
        prestamos = Adelanto.query.filter_by(
            empleado_id=empleado.id,
            tipo="prestamo",
            aprobado=True,
            liquidado=False
        ).all()
        
        # Calcular descuentos
        descuento_efectivo = sum(a.monto for a in adelantos_efectivo)
        descuento_mercaderia = sum(a.monto for a in adelantos_mercaderia)
        descuento_cuota = sum(p.calcular_monto_cuota() for p in prestamos)
        
        sueldo_base = empleado.salary or Decimal('0')
        sueldo_neto = sueldo_base - descuento_efectivo - descuento_mercaderia - descuento_cuota
        
        # Crear liquidación
        liquidacion = LiquidacionSueldo(
            empleado_id=empleado.id,
            periodo=periodo,
            sueldo_base=sueldo_base,
            descuento_adelanto_efectivo=descuento_efectivo,
            descuento_adelanto_mercaderia=descuento_mercaderia,
            descuento_cuota_prestamo=descuento_cuota,
            sueldo_neto=sueldo_neto
        )
        
        db.session.add(liquidacion)
        
        # Marcar adelantos como liquidados
        for adelanto in adelantos_efectivo + adelantos_mercaderia:
            adelanto.liquidado = True
            adelanto.fecha_liquidacion = datetime.now()
        
        # Incrementar cuotas pagadas en préstamos y marcar como liquidado si corresponde
        for prestamo in prestamos:
            prestamo.cuotas_pagadas += 1
            if prestamo.cuotas_pagadas >= prestamo.cantidad_cuotas:
                prestamo.liquidado = True
                prestamo.fecha_liquidacion = datetime.now()
        
        liquidaciones_creadas.append({
            "empleado": empleado.name,
            "sueldo_neto": float(sueldo_neto)
        })
    
    db.session.commit()
    
    return jsonify({
        "message": f"Liquidaciones generadas para {periodo}",
        "total": len(liquidaciones_creadas),
        "liquidaciones": liquidaciones_creadas
    }), 201


@rrhh_bp.route("/api/rrhh/liquidaciones/<periodo>", methods=["GET"])
def liquidaciones_obtener(periodo):
    """Obtener liquidaciones de un periodo específico"""
    liquidaciones = LiquidacionSueldo.query.filter_by(periodo=periodo).all()
    
    if not liquidaciones:
        return jsonify({"error": f"No se encontraron liquidaciones para {periodo}"}), 404
    
    return jsonify({
        "periodo": periodo,
        "liquidaciones": [{
            "id": l.id,
            "empleado": {
                "id": l.empleado.id,
                "nombre": l.empleado.name
            },
            "sueldo_base": float(l.sueldo_base),
            "descuento_adelanto_efectivo": float(l.descuento_adelanto_efectivo),
            "descuento_adelanto_mercaderia": float(l.descuento_adelanto_mercaderia),
            "descuento_cuota_prestamo": float(l.descuento_cuota_prestamo),
            "sueldo_neto": float(l.sueldo_neto),
            "fecha_liquidacion": l.fecha_liquidacion.isoformat()
        } for l in liquidaciones]
    })
