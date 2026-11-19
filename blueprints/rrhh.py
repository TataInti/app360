from datetime import datetime, date, timedelta, time as dt_time
from decimal import Decimal
import io
import os
import uuid

from flask import Blueprint, request, jsonify, send_file, render_template, flash, redirect, url_for, current_app
from werkzeug.utils import secure_filename
import pandas as pd

from models import (
    Adelanto,
    Asistencia,
    Employee,
    Turno,
    User,
    db,
)
from models.rrhh import (
    LiquidacionSueldo,
    TurnoDia,
    FichadaReloj,
    ResumenAsistenciaDiaria,
    TOLERANCIA_TARDANZA_MIN,
)
from security import protect_blueprint
from services.importes import MAXIMO_NUMERIC_12_2, parse_importe

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
            current_app.logger.exception("Error al crear empleado desde RRHH")
            flash("No se pudo crear el empleado. Revisá los datos e intentá de nuevo.", "danger")
        return redirect(url_for("rrhh.rrhh_empleados"))
    
    # GET: cargar empleados y ubicaciones
    employees = Employee.query.all()
    locations = Location.query.all()
    return render_template("rrhh_empleados.html", employees=employees, locations=locations)


@rrhh_bp.route("/rrhh/dotacion", methods=["GET"])
def rrhh_dotacion():
    """La dotación todavía no tiene vista propia: se consulta desde el panel de RRHH."""
    flash("La dotación todavía no tiene datos cargados. Podés seguir desde el panel de RRHH.", "info")
    return redirect(url_for("rrhh.rrhh_panel"))


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
        monto = parse_importe(data["monto"], maximo=MAXIMO_NUMERIC_12_2)
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

    # Periodo ya liquidado: se muestran los valores guardados. La fórmula de abajo volvería a
    # descontar las cuotas de préstamo ya aplicadas en la liquidación (A-011).
    guardadas = LiquidacionSueldo.query.filter_by(periodo=periodo).all()
    if guardadas:
        ids_liquidados = {liq.empleado_id for liq in guardadas}
        empleados_activos = Employee.query.filter_by(is_active=True).all()
        return jsonify({
            "periodo": periodo,
            "periodo_liquidado": True,
            "empleados_sin_liquidacion": sum(1 for e in empleados_activos if e.id not in ids_liquidados),
            "liquidaciones": [{
                "empleado_id": liq.empleado_id,
                "empleado_nombre": liq.empleado.name,
                "sueldo_base": float(liq.sueldo_base or 0),
                "descuento_adelanto_efectivo": float(liq.descuento_adelanto_efectivo or 0),
                "descuento_adelanto_mercaderia": float(liq.descuento_adelanto_mercaderia or 0),
                "descuento_cuota_prestamo": float(liq.descuento_cuota_prestamo or 0),
                "sueldo_neto": float(liq.sueldo_neto or 0),
                "adelantos_efectivo_count": None,
                "adelantos_mercaderia_count": None,
                "prestamos_count": None,
                "ya_liquidado": True,
            } for liq in guardadas],
        })

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
            "prestamos_count": len(prestamos),
            "ya_liquidado": False,
        })

    return jsonify({
        "periodo": periodo,
        "periodo_liquidado": False,
        "empleados_sin_liquidacion": 0,
        "liquidaciones": preview,
    })


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
        # 200 con lista vacía: un 404 se registra como error en la consola del navegador.
        # Se conserva el campo error, que leen las pantallas de liquidaciones.
        return jsonify({
            "periodo": periodo,
            "liquidaciones": [],
            "error": f"No se encontraron liquidaciones para {periodo}",
        })
    
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


# ─── Endpoints Fichadas Reloj (Control de Asistencia Biométrico) ──────────


def _parse_hora(v):
    """Parsea hora del reloj en múltiples formatos: HH:MM, HH:MM:SS, Timedelta, time, datetime."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "hour") and hasattr(v, "minute"):
        # ya es un time o datetime
        return v if not hasattr(v, "date") else v.time()
    if isinstance(v, pd.Timedelta):
        total_sec = int(v.total_seconds())
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        return dt_time(h % 24, m, s)
    s = str(v).strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _normalize_clock_id_value(v):
    """Normaliza un clock_id a string entero limpio: '09' → '9', ' 9 ' → '9'."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return str(int(float(s)))
    except (ValueError, OverflowError):
        return s


def _empty_processing_stats():
    return {
        "procesados": 0,
        "faltas": 0,
        "tardanzas": 0,
        "fichadas_faltantes": 0,
        "sin_turno": 0,
        "dias_sin_turno": 0,
    }


def _diagnosticar_asociacion_fichadas():
    """Audita fichadas pendientes para explicar por qué asocian o no."""
    from collections import defaultdict
    from sqlalchemy import func

    pendientes_rows = (
        db.session.query(
            FichadaReloj.clock_id_original,
            FichadaReloj.nombre_reloj,
            func.count(FichadaReloj.id),
        )
        .filter(FichadaReloj.empleado_id.is_(None))
        .group_by(FichadaReloj.clock_id_original, FichadaReloj.nombre_reloj)
        .order_by(func.count(FichadaReloj.id).desc(), FichadaReloj.clock_id_original.asc())
        .all()
    )

    empleados_por_clock = defaultdict(list)
    empleados_con_clock_id = 0
    empleados_activos_con_clock_id = 0

    for emp in Employee.query.filter(Employee.clock_id.isnot(None)).all():
        normalized = _normalize_clock_id_value(emp.clock_id)
        if not normalized:
            continue

        empleados_con_clock_id += 1
        if emp.is_active:
            empleados_activos_con_clock_id += 1

        empleados_por_clock[normalized].append(
            {
                "empleado_id": emp.id,
                "empleado": emp.name,
                "clock_id": str(emp.clock_id).strip(),
                "turno_id": emp.turno_id,
                "activo": bool(emp.is_active),
            }
        )

    matchables = []
    sin_match = []
    ambiguos = []
    sin_turno = []
    matchables_total = 0
    sin_match_total = 0
    ambiguos_total = 0

    for clock_id_original, nombre_reloj, cantidad in pendientes_rows:
        cantidad = int(cantidad or 0)
        item = {
            "clock_id": clock_id_original,
            "clock_id_normalizado": _normalize_clock_id_value(clock_id_original),
            "nombre_reloj": nombre_reloj or "—",
            "cantidad": cantidad,
        }
        candidatos = empleados_por_clock.get(item["clock_id_normalizado"], [])
        if not candidatos:
            sin_match.append(item)
            sin_match_total += cantidad
            continue

        if len(candidatos) > 1:
            ambiguos.append({**item, "empleados": candidatos})
            ambiguos_total += cantidad
            continue

        candidato = candidatos[0]
        match_item = {**item, **candidato}
        matchables.append(match_item)
        matchables_total += cantidad
        if not candidato.get("turno_id"):
            sin_turno.append(match_item)

    duplicados_normalizados = [
        {
            "clock_id_normalizado": clock_id_normalizado,
            "empleados": empleados,
        }
        for clock_id_normalizado, empleados in sorted(empleados_por_clock.items())
        if len(empleados) > 1
    ]

    return {
        "pendientes_total": sum(int(row[2] or 0) for row in pendientes_rows),
        "clock_ids_pendientes": len(pendientes_rows),
        "empleados_con_clock_id": empleados_con_clock_id,
        "empleados_activos_con_clock_id": empleados_activos_con_clock_id,
        "matchables_total": matchables_total,
        "sin_match_total": sin_match_total,
        "ambiguos_total": ambiguos_total,
        "sin_turno_total": sum(item["cantidad"] for item in sin_turno),
        "sin_turno_empleados": len({item["empleado_id"] for item in sin_turno}),
        "duplicados_normalizados": duplicados_normalizados,
        "matchables": matchables,
        "sin_match": sin_match,
        "ambiguos": ambiguos,
        "sin_turno": sin_turno,
    }


def _asociar_fichadas():
    """Asocia fichadas pendientes y devuelve detalle de impacto y diagnóstico."""
    diagnostico_previo = _diagnosticar_asociacion_fichadas()
    if not diagnostico_previo["pendientes_total"]:
        return {
            "asociados": 0,
            "pendientes": 0,
            "empleado_ids": [],
            "impactados": [],
            "diagnostico": diagnostico_previo,
        }

    asociados = 0
    impactados = {}

    for match in diagnostico_previo["matchables"]:
        emp_id = match["empleado_id"]
        count = FichadaReloj.query.filter(
            FichadaReloj.clock_id_original == match["clock_id"],
            FichadaReloj.empleado_id.is_(None),
        ).update({"empleado_id": emp_id})
        count = int(count or 0)
        if not count:
            continue

        asociados += count
        if emp_id not in impactados:
            impactados[emp_id] = {
                "empleado_id": emp_id,
                "empleado": match["empleado"],
                "turno_id": match["turno_id"],
                "clock_ids": [],
                "cantidad": 0,
            }
        impactados[emp_id]["clock_ids"].append(match["clock_id"])
        impactados[emp_id]["cantidad"] += count

    if asociados:
        db.session.commit()

    diagnostico_actual = _diagnosticar_asociacion_fichadas()
    impactados_list = sorted(
        impactados.values(),
        key=lambda item: (-item["cantidad"], item["empleado"]),
    )
    for impactado in impactados_list:
        impactado["clock_ids"] = sorted(impactado["clock_ids"])

    return {
        "asociados": asociados,
        "pendientes": diagnostico_actual["pendientes_total"],
        "empleado_ids": sorted(impactados.keys()),
        "impactados": impactados_list,
        "diagnostico": diagnostico_actual,
    }


@rrhh_bp.route("/api/rrhh/fichadas/cargar", methods=["POST"])
def fichadas_cargar():
    """Importar fichadas desde Excel del reloj biométrico."""
    if "archivo" not in request.files:
        return jsonify({"error": "Se requiere un archivo Excel"}), 400

    archivo = request.files["archivo"]
    if not archivo.filename:
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    ext = os.path.splitext(archivo.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        return jsonify({"error": "Solo se aceptan archivos .xlsx o .xls"}), 400

    upload_dir = current_app.config.get("UPLOAD_FOLDER", "/tmp")
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(archivo.filename)
    path = os.path.join(upload_dir, filename)
    archivo.save(path)

    try:
        df = pd.read_excel(path, skiprows=7)
    except Exception as e:
        return jsonify({"error": f"No se pudo leer el Excel: {e}"}), 400
    finally:
        if os.path.exists(path):
            os.remove(path)

    # Normalizar nombres de columnas (soporta formato crudo del reloj y preprocesado)
    col_map = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl == "id":
            col_map[c] = "clock_id"
        elif "id" in cl and "empleado" in cl:
            col_map[c] = "clock_id"
        elif cl == "fecha":
            col_map[c] = "fecha"
        elif cl in ("hora de registro de entrada", "hora"):
            col_map[c] = "hora"
        elif cl == "nombre":
            col_map[c] = "nombre_ref"
        elif cl == "apellido":
            col_map[c] = "apellido_ref"
        elif cl == "empleado":
            col_map[c] = "nombre_ref"
    df = df.rename(columns=col_map)

    required_cols = {"clock_id", "fecha", "hora"}
    if not required_cols.issubset(set(df.columns)):
        return jsonify({"error": f"Columnas requeridas no encontradas. Encontradas: {list(df.columns)}"}), 400

    # Concatenar nombre+apellido si vienen separados
    if "apellido_ref" in df.columns:
        df["nombre_ref"] = df.get("nombre_ref", "").astype(str) + " " + df["apellido_ref"].astype(str)

    df = df.dropna(subset=["clock_id", "fecha", "hora"])
    df["clock_id"] = df["clock_id"].apply(_normalize_clock_id_value)

    total_filas = len(df)
    fechas_rango = None
    if total_filas > 0:
        try:
            fechas = pd.to_datetime(df["fecha"], errors="coerce").dropna()
            if len(fechas):
                fechas_rango = {"desde": fechas.min().strftime("%Y-%m-%d"), "hasta": fechas.max().strftime("%Y-%m-%d")}
        except Exception:
            pass

    # Batch dedup: cargar existentes en un set (1 query en vez de N)
    clock_ids_unicos = df["clock_id"].unique().tolist()
    existentes = set()
    for row in db.session.query(FichadaReloj.clock_id_original, FichadaReloj.fecha_hora).filter(
        FichadaReloj.clock_id_original.in_(clock_ids_unicos)
    ).all():
        existentes.add((row[0], row[1]))

    lote = str(uuid.uuid4())[:8]
    importados = 0
    duplicados = 0
    errores_parse = 0

    for _, row in df.iterrows():
        cid = str(row["clock_id"]).strip()
        nombre_reloj = str(row.get("nombre_ref", "")).strip() if "nombre_ref" in row.index else ""

        try:
            fecha_val = pd.Timestamp(row["fecha"]).date()
        except Exception:
            errores_parse += 1
            continue

        hora_val = _parse_hora(row["hora"])
        if hora_val is None:
            errores_parse += 1
            continue

        fecha_hora = datetime.combine(fecha_val, hora_val)

        if (cid, fecha_hora) in existentes:
            duplicados += 1
            continue

        fichada = FichadaReloj(
            empleado_id=None,
            clock_id_original=cid,
            nombre_reloj=nombre_reloj or None,
            fecha=fecha_val,
            hora=hora_val,
            fecha_hora=fecha_hora,
            archivo_origen=filename,
            lote_importacion=lote,
        )
        db.session.add(fichada)
        existentes.add((cid, fecha_hora))
        importados += 1

    db.session.commit()

    # Auto-asociar: vincular fichadas con empleados por clock_id
    resultado_asociacion = _asociar_fichadas()

    # Auto-procesar: generar resumen diario contra turnos
    proc_stats = _procesar_fichadas_logic(lote=lote) or _empty_processing_stats()

    return jsonify({
        "lote": lote,
        "importados": importados,
        "duplicados": duplicados,
        "errores_parse": errores_parse,
        "total_filas": total_filas,
        "fechas_rango": fechas_rango,
        "asociados": resultado_asociacion["asociados"],
        "pendientes": resultado_asociacion["pendientes"],
        "diagnostico": resultado_asociacion["diagnostico"],
        "procesamiento": proc_stats,
    })


@rrhh_bp.route("/api/rrhh/fichadas/asociar", methods=["POST"])
def fichadas_asociar():
    """Re-asocia fichadas sin empleado y reprocesa lo recién impactado."""
    resultado_asociacion = _asociar_fichadas()
    procesamiento = _empty_processing_stats()

    if resultado_asociacion["empleado_ids"]:
        procesamiento = (
            _procesar_fichadas_logic(empleado_ids=resultado_asociacion["empleado_ids"])
            or _empty_processing_stats()
        )

    return jsonify(
        {
            "asociados": resultado_asociacion["asociados"],
            "pendientes": resultado_asociacion["pendientes"],
            "impactados": resultado_asociacion["impactados"],
            "diagnostico": resultado_asociacion["diagnostico"],
            "procesamiento": procesamiento,
        }
    )


def _procesar_fichadas_logic(lote=None, fecha_desde=None, fecha_hasta=None, empleado_ids=None):
    """Lógica interna de procesamiento de fichadas contra turnos.

    Retorna dict con stats o None si no hay fichadas.
    """
    query = FichadaReloj.query.filter(FichadaReloj.empleado_id.isnot(None))
    if empleado_ids:
        query = query.filter(FichadaReloj.empleado_id.in_(empleado_ids))
    if lote:
        query = query.filter_by(lote_importacion=lote)
    elif fecha_desde and fecha_hasta:
        query = query.filter(FichadaReloj.fecha.between(fecha_desde, fecha_hasta))

    fichadas = query.order_by(FichadaReloj.empleado_id, FichadaReloj.fecha, FichadaReloj.hora).all()
    if not fichadas:
        return None

    # Agrupar por (empleado_id, fecha)
    grupos = {}
    for f in fichadas:
        key = (f.empleado_id, f.fecha)
        grupos.setdefault(key, []).append(f)

    # Precargar turnos y días
    empleado_ids = list({k[0] for k in grupos})
    empleados = {e.id: e for e in Employee.query.filter(Employee.id.in_(empleado_ids)).all()}
    turno_dias_cache = {}

    stats = _empty_processing_stats()
    empleados_sin_turno = set()

    for (emp_id, fecha), fichs in grupos.items():
        emp = empleados.get(emp_id)
        if not emp or not emp.turno_id:
            stats["dias_sin_turno"] += 1
            if emp_id:
                empleados_sin_turno.add(emp_id)
            continue

        dia_semana = fecha.weekday()  # 0=lunes
        cache_key = (emp.turno_id, dia_semana)
        if cache_key not in turno_dias_cache:
            td = TurnoDia.query.filter_by(turno_id=emp.turno_id, dia_semana=dia_semana).first()
            turno_dias_cache[cache_key] = td
        turno_dia = turno_dias_cache[cache_key]

        if not turno_dia or not turno_dia.activo:
            continue

        esperadas = 4 if turno_dia.es_cortado else 2
        horas = sorted([f.hora for f in fichs])

        hora_e1 = horas[0] if len(horas) >= 1 else None
        hora_s1 = horas[1] if len(horas) >= 2 else None
        hora_e2 = horas[2] if len(horas) >= 3 else None
        hora_s2 = horas[3] if len(horas) >= 4 else None

        # Calcular tardanza
        minutos_tarde = 0
        if hora_e1 and turno_dia.hora_inicio_1:
            diff = _time_diff_minutes(turno_dia.hora_inicio_1, hora_e1)
            if diff > TOLERANCIA_TARDANZA_MIN:
                minutos_tarde += diff
        if turno_dia.es_cortado and hora_e2 and turno_dia.hora_inicio_2:
            diff = _time_diff_minutes(turno_dia.hora_inicio_2, hora_e2)
            if diff > TOLERANCIA_TARDANZA_MIN:
                minutos_tarde += diff

        es_tarde = minutos_tarde > 0
        fichada_faltante = len(horas) < esperadas and len(horas) > 0
        es_falta = len(horas) == 0

        # Upsert
        resumen = ResumenAsistenciaDiaria.query.filter_by(empleado_id=emp_id, fecha=fecha).first()
        if not resumen:
            resumen = ResumenAsistenciaDiaria(empleado_id=emp_id, fecha=fecha)
            db.session.add(resumen)

        resumen.turno_id = emp.turno_id
        resumen.fichadas_count = len(horas)
        resumen.fichadas_esperadas = esperadas
        resumen.hora_entrada_1 = hora_e1
        resumen.hora_salida_1 = hora_s1
        resumen.hora_entrada_2 = hora_e2
        resumen.hora_salida_2 = hora_s2
        resumen.minutos_tarde_total = minutos_tarde
        resumen.es_falta = es_falta
        resumen.es_tarde = es_tarde
        resumen.fichada_faltante = fichada_faltante
        resumen.lote_importacion = lote or "manual"

        stats["procesados"] += 1
        if es_falta:
            stats["faltas"] += 1
        if es_tarde:
            stats["tardanzas"] += 1
        if fichada_faltante:
            stats["fichadas_faltantes"] += 1

    # Detectar faltas: días laborales sin fichadas
    if lote:
        fechas_lote = sorted({f.fecha for f in fichadas})
        if fechas_lote:
            fecha_min, fecha_max = fechas_lote[0], fechas_lote[-1]
            for emp_id in empleado_ids:
                emp = empleados.get(emp_id)
                if not emp or not emp.turno_id:
                    continue
                current = fecha_min
                while current <= fecha_max:
                    if (emp_id, current) not in grupos:
                        dia_semana = current.weekday()
                        cache_key = (emp.turno_id, dia_semana)
                        if cache_key not in turno_dias_cache:
                            td = TurnoDia.query.filter_by(turno_id=emp.turno_id, dia_semana=dia_semana).first()
                            turno_dias_cache[cache_key] = td
                        turno_dia = turno_dias_cache[cache_key]
                        if turno_dia and turno_dia.activo:
                            resumen = ResumenAsistenciaDiaria.query.filter_by(
                                empleado_id=emp_id, fecha=current
                            ).first()
                            if not resumen:
                                resumen = ResumenAsistenciaDiaria(
                                    empleado_id=emp_id,
                                    fecha=current,
                                    turno_id=emp.turno_id,
                                    fichadas_count=0,
                                    fichadas_esperadas=4 if turno_dia.es_cortado else 2,
                                    es_falta=True,
                                    lote_importacion=lote or "manual",
                                )
                                db.session.add(resumen)
                                stats["procesados"] += 1
                                stats["faltas"] += 1
                    current += timedelta(days=1)

    stats["sin_turno"] = len(empleados_sin_turno)
    db.session.commit()
    return stats


@rrhh_bp.route("/api/rrhh/fichadas/procesar", methods=["POST"])
def fichadas_procesar():
    """Procesa fichadas crudas contra turnos y genera resumen diario."""
    data = request.get_json() or {}
    lote = data.get("lote")
    fecha_desde_str = data.get("fecha_desde")
    fecha_hasta_str = data.get("fecha_hasta")

    fecha_desde = fecha_hasta = None
    if fecha_desde_str and fecha_hasta_str:
        try:
            fecha_desde = datetime.strptime(fecha_desde_str, "%Y-%m-%d").date()
            fecha_hasta = datetime.strptime(fecha_hasta_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido"}), 400

    sin_asociar_q = FichadaReloj.query.filter(FichadaReloj.empleado_id.is_(None))
    if lote:
        sin_asociar_q = sin_asociar_q.filter_by(lote_importacion=lote)
    sin_asociar = sin_asociar_q.count()

    stats = _procesar_fichadas_logic(lote=lote, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    if not stats:
        return jsonify({"error": "No se encontraron fichadas asociadas para procesar", "sin_asociar": sin_asociar}), 404

    stats["sin_asociar"] = sin_asociar
    return jsonify(stats)


def _time_diff_minutes(t_ref, t_actual):
    """Diferencia en minutos: positivo si t_actual es posterior a t_ref."""
    ref_min = t_ref.hour * 60 + t_ref.minute
    act_min = t_actual.hour * 60 + t_actual.minute
    return act_min - ref_min


@rrhh_bp.route("/api/rrhh/fichadas/resumen", methods=["GET"])
def fichadas_resumen():
    """Resumen de asistencia con KPIs agregados."""
    periodo = request.args.get("periodo")  # YYYY-MM
    empleado_id = request.args.get("empleado_id", type=int)
    estado = request.args.get("estado")  # falta|tarde|ok|fichada_faltante
    periodo_fd = None
    periodo_fh = None

    query = ResumenAsistenciaDiaria.query

    if periodo:
        try:
            anio, mes = int(periodo[:4]), int(periodo[5:7])
            periodo_fd = date(anio, mes, 1)
            if mes == 12:
                periodo_fh = date(anio + 1, 1, 1) - timedelta(days=1)
            else:
                periodo_fh = date(anio, mes + 1, 1) - timedelta(days=1)
            query = query.filter(ResumenAsistenciaDiaria.fecha.between(periodo_fd, periodo_fh))
        except (ValueError, IndexError):
            return jsonify({"error": "Formato de período inválido (YYYY-MM)"}), 400

    if empleado_id:
        query = query.filter_by(empleado_id=empleado_id)

    if estado == "falta":
        query = query.filter_by(es_falta=True, justificado=False)
    elif estado == "tarde":
        query = query.filter_by(es_tarde=True)
    elif estado == "fichada_faltante":
        query = query.filter_by(fichada_faltante=True)
    elif estado == "ok":
        query = query.filter_by(es_falta=False, es_tarde=False, fichada_faltante=False)

    registros = query.order_by(ResumenAsistenciaDiaria.fecha.desc()).limit(2000).all()

    # KPIs
    empleados_unicos = set()
    total_faltas = 0
    total_tardanzas = 0
    total_min_tarde = 0
    total_dias = 0

    for r in registros:
        empleados_unicos.add(r.empleado_id)
        total_dias += 1
        if r.es_falta and not r.justificado:
            total_faltas += 1
        if r.es_tarde:
            total_tardanzas += 1
            total_min_tarde += r.minutos_tarde_total or 0

    puntualidad = round((1 - (total_faltas + total_tardanzas) / total_dias) * 100, 1) if total_dias else 100

    # Ranking peor comportamiento (top 10)
    ranking = {}
    for r in registros:
        emp_id = r.empleado_id
        if emp_id not in ranking:
            ranking[emp_id] = {"faltas": 0, "tardanzas": 0, "min_tarde": 0}
        if r.es_falta and not r.justificado:
            ranking[emp_id]["faltas"] += 1
        if r.es_tarde:
            ranking[emp_id]["tardanzas"] += 1
            ranking[emp_id]["min_tarde"] += r.minutos_tarde_total or 0

    # Precargar nombres
    emp_ids_ranking = list(ranking.keys())
    emp_names = {}
    if emp_ids_ranking:
        for e in Employee.query.filter(Employee.id.in_(emp_ids_ranking)).all():
            emp_names[e.id] = e.name

    top_peor = sorted(
        ranking.items(),
        key=lambda x: x[1]["faltas"] * 100 + x[1]["tardanzas"],
        reverse=True,
    )[:10]

    # Tendencia mensual (últimos 6 meses)
    hoy = date.today()
    tendencia = []
    for i in range(5, -1, -1):
        m = hoy.month - i
        a = hoy.year
        while m <= 0:
            m += 12
            a -= 1
        label = f"{a}-{m:02d}"
        td_fd = date(a, m, 1)
        if m == 12:
            td_fh = date(a + 1, 1, 1) - timedelta(days=1)
        else:
            td_fh = date(a, m + 1, 1) - timedelta(days=1)
        mes_q = ResumenAsistenciaDiaria.query.filter(
            ResumenAsistenciaDiaria.fecha.between(td_fd, td_fh)
        )
        total_m = mes_q.count()
        faltas_m = mes_q.filter_by(es_falta=True, justificado=False).count()
        tardes_m = mes_q.filter_by(es_tarde=True).count()
        punt_m = round((1 - (faltas_m + tardes_m) / total_m) * 100, 1) if total_m else 100
        tendencia.append({"mes": label, "puntualidad": punt_m, "faltas": faltas_m, "tardanzas": tardes_m})

    # Fichadas sin asociar (pendientes de vinculación con empleado)
    fichadas_sin_asociar = FichadaReloj.query.filter(FichadaReloj.empleado_id.is_(None)).count()
    fichadas_pendientes = []
    if fichadas_sin_asociar > 0:
        from sqlalchemy import func
        rows = (
            db.session.query(
                FichadaReloj.clock_id_original,
                FichadaReloj.nombre_reloj,
                func.count(FichadaReloj.id),
            )
            .filter(FichadaReloj.empleado_id.is_(None))
            .group_by(FichadaReloj.clock_id_original, FichadaReloj.nombre_reloj)
            .order_by(func.count(FichadaReloj.id).desc(), FichadaReloj.clock_id_original.asc())
            .all()
        )
        fichadas_pendientes = [
            {"clock_id": r[0], "nombre_reloj": r[1] or "—", "cantidad": r[2]}
            for r in rows
        ]

    # Fichadas asociadas pero sin procesar del período/empleado seleccionado.
    fichadas_asociadas_q = (
        db.session.query(FichadaReloj.empleado_id, FichadaReloj.fecha)
        .filter(FichadaReloj.empleado_id.isnot(None))
    )
    resumen_procesado_q = db.session.query(
        ResumenAsistenciaDiaria.empleado_id,
        ResumenAsistenciaDiaria.fecha,
    )

    if periodo_fd and periodo_fh:
        fichadas_asociadas_q = fichadas_asociadas_q.filter(
            FichadaReloj.fecha.between(periodo_fd, periodo_fh)
        )
        resumen_procesado_q = resumen_procesado_q.filter(
            ResumenAsistenciaDiaria.fecha.between(periodo_fd, periodo_fh)
        )

    if empleado_id:
        fichadas_asociadas_q = fichadas_asociadas_q.filter(FichadaReloj.empleado_id == empleado_id)
        resumen_procesado_q = resumen_procesado_q.filter(
            ResumenAsistenciaDiaria.empleado_id == empleado_id
        )

    dias_fichadas = {(emp_id, fecha) for emp_id, fecha in fichadas_asociadas_q.distinct().all()}
    dias_procesados = {(emp_id, fecha) for emp_id, fecha in resumen_procesado_q.distinct().all()}
    fichadas_sin_procesar = len(dias_fichadas - dias_procesados)

    return jsonify({
        "kpis": {
            "empleados_analizados": len(empleados_unicos),
            "faltas": total_faltas,
            "tardanzas": total_tardanzas,
            "min_tarde_acumulados": total_min_tarde,
            "puntualidad": puntualidad,
            "fichadas_sin_asociar": fichadas_sin_asociar,
            "fichadas_sin_procesar": fichadas_sin_procesar,
        },
        "fichadas_sin_procesar_scope": "periodo" if periodo else "global",
        "ranking_peor": [
            {
                "empleado_id": eid,
                "nombre": emp_names.get(eid, "—"),
                "faltas": data["faltas"],
                "tardanzas": data["tardanzas"],
                "min_tarde": data["min_tarde"],
            }
            for eid, data in top_peor
        ],
        "tendencia": tendencia,
        "fichadas_pendientes": fichadas_pendientes,
        "registros": [
            {
                "id": r.id,
                "empleado_id": r.empleado_id,
                "empleado": r.empleado.name if r.empleado else "—",
                "fecha": r.fecha.isoformat(),
                "fichadas": r.fichadas_count,
                "esperadas": r.fichadas_esperadas,
                "entrada_1": r.hora_entrada_1.strftime("%H:%M") if r.hora_entrada_1 else None,
                "salida_1": r.hora_salida_1.strftime("%H:%M") if r.hora_salida_1 else None,
                "entrada_2": r.hora_entrada_2.strftime("%H:%M") if r.hora_entrada_2 else None,
                "salida_2": r.hora_salida_2.strftime("%H:%M") if r.hora_salida_2 else None,
                "min_tarde": r.minutos_tarde_total,
                "es_falta": r.es_falta,
                "es_tarde": r.es_tarde,
                "fichada_faltante": r.fichada_faltante,
                "justificado": r.justificado,
                "notas": r.notas,
            }
            for r in registros
        ],
    })


@rrhh_bp.route("/api/rrhh/fichadas/resumen-empleado", methods=["GET"])
def fichadas_resumen_empleado():
    """Detalle diario de un empleado en un mes."""
    empleado_id = request.args.get("empleado_id", type=int)
    periodo = request.args.get("periodo")
    if not empleado_id or not periodo:
        return jsonify({"error": "Se requiere empleado_id y periodo (YYYY-MM)"}), 400

    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
        fd = date(anio, mes, 1)
        fh = date(anio, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(anio + 1, 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        return jsonify({"error": "Período inválido"}), 400

    registros = ResumenAsistenciaDiaria.query.filter(
        ResumenAsistenciaDiaria.empleado_id == empleado_id,
        ResumenAsistenciaDiaria.fecha.between(fd, fh),
    ).order_by(ResumenAsistenciaDiaria.fecha).all()

    emp = Employee.query.get(empleado_id)

    return jsonify({
        "empleado": emp.name if emp else "—",
        "periodo": periodo,
        "dias": [
            {
                "id": r.id,
                "fecha": r.fecha.isoformat(),
                "dia_semana": r.fecha.weekday(),
                "fichadas": r.fichadas_count,
                "esperadas": r.fichadas_esperadas,
                "entrada_1": r.hora_entrada_1.strftime("%H:%M") if r.hora_entrada_1 else None,
                "salida_1": r.hora_salida_1.strftime("%H:%M") if r.hora_salida_1 else None,
                "entrada_2": r.hora_entrada_2.strftime("%H:%M") if r.hora_entrada_2 else None,
                "salida_2": r.hora_salida_2.strftime("%H:%M") if r.hora_salida_2 else None,
                "min_tarde": r.minutos_tarde_total,
                "es_falta": r.es_falta,
                "es_tarde": r.es_tarde,
                "fichada_faltante": r.fichada_faltante,
                "justificado": r.justificado,
                "notas": r.notas,
            }
            for r in registros
        ],
    })


@rrhh_bp.route("/api/rrhh/fichadas/resumen/<int:resumen_id>/justificar", methods=["PUT"])
def fichadas_justificar(resumen_id):
    """Marcar un resumen diario como justificado."""
    resumen = ResumenAsistenciaDiaria.query.get_or_404(resumen_id)
    data = request.get_json() or {}

    resumen.justificado = True
    resumen.notas = data.get("notas", resumen.notas)
    db.session.commit()

    return jsonify({"message": "Justificado correctamente"})


@rrhh_bp.route("/api/rrhh/fichadas/resumen-liquidacion", methods=["GET"])
def fichadas_resumen_liquidacion():
    """Retorna string resumen para liquidación de sueldos."""
    empleado_id = request.args.get("empleado_id", type=int)
    periodo = request.args.get("periodo")
    if not empleado_id or not periodo:
        return jsonify({"error": "Se requiere empleado_id y periodo"}), 400

    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
        fd = date(anio, mes, 1)
        fh = date(anio, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(anio + 1, 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        return jsonify({"error": "Período inválido"}), 400

    registros = ResumenAsistenciaDiaria.query.filter(
        ResumenAsistenciaDiaria.empleado_id == empleado_id,
        ResumenAsistenciaDiaria.fecha.between(fd, fh),
        ResumenAsistenciaDiaria.justificado == False,  # noqa: E712
    ).all()

    tardanzas = [r for r in registros if r.es_tarde]
    faltas = [r for r in registros if r.es_falta]
    min_acum = sum(r.minutos_tarde_total or 0 for r in tardanzas)

    texto = f"Llegadas tarde: {len(tardanzas)} turnos, min acumulados: {min_acum} / Faltas: {len(faltas)} días"

    return jsonify({"resumen": texto, "tardanzas": len(tardanzas), "min_acumulados": min_acum, "faltas": len(faltas)})
