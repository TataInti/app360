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
            
            nuevo_empleado = Employee(
                first_name=first_name,
                last_name=last_name,
                position=data.get("role"),
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


@rrhh_bp.route("/rrhh/ausentismo", methods=["GET"])
def rrhh_ausentismo():
    """Vista de ausentismo"""
    return render_template("rrhh_ausentismo.html")


# Endpoints para Turnos

@rrhh_bp.route("/api/rrhh/turnos", methods=["GET"])
def turnos_listar():
    """Listar turnos activos"""
    turnos = Turno.query.filter_by(activo=True).order_by(Turno.hora_inicio).all()

    return jsonify({
        "turnos": [{
            "id": t.id,
            "nombre": t.nombre,
            "descripcion": t.descripcion,
            "hora_inicio": t.hora_inicio.strftime("%H:%M"),
            "hora_fin": t.hora_fin.strftime("%H:%M"),
            "dias_semana": t.dias_semana
        } for t in turnos]
    })


@rrhh_bp.route("/api/rrhh/turnos", methods=["POST"])
def turnos_crear():
    """Crear nuevo turno"""
    data = request.get_json()

    required_fields = ["nombre", "hora_inicio", "hora_fin"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    nombre = data["nombre"].strip()
    if not nombre:
        return jsonify({"error": "Nombre no puede estar vacío"}), 400

    # Verificar que no exista
    existente = Turno.query.filter_by(nombre=nombre).first()
    if existente:
        return jsonify({"error": "Ya existe un turno con ese nombre"}), 400

    try:
        hora_inicio = datetime.strptime(data["hora_inicio"], "%H:%M").time()
        hora_fin = datetime.strptime(data["hora_fin"], "%H:%M").time()
    except ValueError:
        return jsonify({"error": "Formato de hora inválido (HH:MM)"}), 400

    turno = Turno(
        nombre=nombre,
        descripcion=data.get("descripcion", ""),
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        dias_semana=data.get("dias_semana", "1,2,3,4,5")  # Lunes a viernes por defecto
    )

    db.session.add(turno)
    db.session.commit()

    return jsonify({
        "message": "Turno creado",
        "turno": {
            "id": turno.id,
            "nombre": turno.nombre,
            "hora_inicio": turno.hora_inicio.strftime("%H:%M"),
            "hora_fin": turno.hora_fin.strftime("%H:%M")
        }
    }), 201


@rrhh_bp.route("/api/rrhh/turnos/<int:turno_id>", methods=["DELETE"])
def turnos_eliminar(turno_id):
    """Desactivar turno"""
    turno = Turno.query.get_or_404(turno_id)
    turno.activo = False
    db.session.commit()

    return jsonify({"message": "Turno desactivado"})


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


# Endpoints para Adelantos

@rrhh_bp.route("/api/rrhh/adelantos", methods=["GET"])
def adelantos_listar():
    """Listar adelantos con filtros"""
    empleado_id = request.args.get("empleado_id")
    aprobado = request.args.get("aprobado")
    pagado = request.args.get("pagado")
    limite = request.args.get("limite", 50, type=int)

    query = Adelanto.query

    # Aplicar filtros
    if empleado_id:
        query = query.filter(Adelanto.empleado_id == empleado_id)

    if aprobado is not None:
        aprobado_bool = aprobado.lower() == "true"
        query = query.filter(Adelanto.aprobado == aprobado_bool)

    if pagado is not None:
        pagado_bool = pagado.lower() == "true"
        query = query.filter(Adelanto.pagado == pagado_bool)

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
            "monto": float(a.monto),
            "motivo": a.motivo,
            "aprobado": a.aprobado,
            "fecha_aprobacion": a.fecha_aprobacion.isoformat() if a.fecha_aprobacion else None,
            "pagado": a.pagado,
            "fecha_pago": a.fecha_pago.isoformat() if a.fecha_pago else None,
            "aprobado_por": a.aprobado_por.username if a.aprobado_por else None
        } for a in adelantos]
    })


@rrhh_bp.route("/api/rrhh/adelantos", methods=["POST"])
def adelantos_solicitar():
    """Solicitar adelanto de sueldo"""
    data = request.get_json()

    required_fields = ["empleado_id", "monto", "motivo"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

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

    adelanto = Adelanto(
        empleado_id=data["empleado_id"],
        monto=monto,
        motivo=data["motivo"]
    )

    db.session.add(adelanto)
    db.session.commit()

    return jsonify({
        "message": "Adelanto solicitado",
        "adelanto": {
            "id": adelanto.id,
            "monto": float(adelanto.monto),
            "motivo": adelanto.motivo,
            "aprobado": adelanto.aprobado
        }
    }), 201


@rrhh_bp.route("/api/rrhh/adelantos/<int:adelanto_id>/aprobar", methods=["POST"])
def adelantos_aprobar(adelanto_id):
    """Aprobar adelanto"""
    adelanto = Adelanto.query.get_or_404(adelanto_id)

    if adelanto.aprobado:
        return jsonify({"error": "Adelanto ya está aprobado"}), 400

    data = request.get_json()
    usuario_id = data.get("usuario_id", 1)  # Default admin

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
                "Monto": float(a.monto),
                "Motivo": a.motivo or "",
                "Aprobado": "Sí" if a.aprobado else "No",
                "Fecha Aprobación": a.fecha_aprobacion,
                "Pagado": "Sí" if a.pagado else "No",
                "Fecha Pago": a.fecha_pago,
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
