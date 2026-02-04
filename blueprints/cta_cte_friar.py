from datetime import datetime, date
from decimal import Decimal

from flask import Blueprint, request, jsonify, render_template, session

from models import db, User
from models.tesoreria import CuentaCorrienteFriar, PagoFriar, LogCuentaCorrienteFriar, InstrumentoPago
from models.gastos import Proveedor
from security import protect_blueprint

cta_cte_friar_bp = Blueprint("cta_cte_friar", __name__)

protect_blueprint(cta_cte_friar_bp, "tesoreria")


# =============================================================================
# RUTAS WEB
# =============================================================================

@cta_cte_friar_bp.route("/tesoreria/cta-cte-friar", methods=["GET"])
def cta_cte_friar_dashboard():
    """Dashboard de Cuenta Corriente Friar"""
    return render_template("cta_cte_friar.html")


# =============================================================================
# ENDPOINTS API - CUENTA CORRIENTE
# =============================================================================

@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar", methods=["GET"])
def cuenta_corriente_obtener():
    """Obtener cuenta corriente Friar (debería ser única)"""
    cuenta = CuentaCorrienteFriar.query.first()
    
    if not cuenta:
        return jsonify({"cuenta": None})
    
    # Calcular total de pagos
    total_pagos = db.session.query(db.func.sum(PagoFriar.monto)).filter(
        PagoFriar.cuenta_corriente_id == cuenta.id
    ).scalar() or 0
    
    saldo_actual = float(cuenta.saldo_inicial) - float(total_pagos)
    
    return jsonify({
        "cuenta": {
            "id": cuenta.id,
            "proveedor_id": cuenta.proveedor_id,
            "proveedor": cuenta.proveedor.nombre if cuenta.proveedor else None,
            "saldo_inicial": float(cuenta.saldo_inicial),
            "total_pagos": float(total_pagos),
            "saldo_actual": saldo_actual,
            "observaciones": cuenta.observaciones,
            "editado_por": cuenta.editado_por.username if cuenta.editado_por else None,
            "fecha_edicion": cuenta.fecha_edicion.isoformat() if cuenta.fecha_edicion else None,
            "created_at": cuenta.created_at.isoformat(),
            "updated_at": cuenta.updated_at.isoformat()
        }
    })


@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar", methods=["POST"])
def cuenta_corriente_crear():
    """Crear cuenta corriente Friar (solo si no existe)"""
    # Verificar que no exista ya
    if CuentaCorrienteFriar.query.first():
        return jsonify({"error": "Ya existe una cuenta corriente Friar"}), 400
    
    data = request.get_json()
    proveedor_id = data.get("proveedor_id")
    saldo_inicial = data.get("saldo_inicial", 0)
    
    if not proveedor_id:
        return jsonify({"error": "proveedor_id requerido"}), 400
    
    # Verificar que el proveedor existe
    proveedor = Proveedor.query.get(proveedor_id)
    if not proveedor:
        return jsonify({"error": "Proveedor no encontrado"}), 404
    
    try:
        cuenta = CuentaCorrienteFriar(
            proveedor_id=proveedor_id,
            saldo_inicial=Decimal(str(saldo_inicial)),
            observaciones=data.get("observaciones")
        )
        
        db.session.add(cuenta)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Cuenta corriente creada",
            "cuenta": {
                "id": cuenta.id,
                "saldo_inicial": float(cuenta.saldo_inicial)
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear cuenta: {str(e)}"}), 500


def require_admin():
    """Helper para verificar que el usuario sea admin"""
    if "user" not in session:
        return jsonify({"error": "No autenticado"}), 401
    if session.get("role") not in ["admin", "manager", "gerente"]:
        return jsonify({"error": "Acceso denegado. Se requiere rol de administrador."}), 403
    return None


@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar/<int:id>", methods=["PUT"])
def cuenta_corriente_editar(id):
    """Editar saldo inicial de cuenta corriente (solo admin, con justificación)"""
    # Verificar permisos admin
    auth_error = require_admin()
    if auth_error:
        return auth_error
    
    cuenta = CuentaCorrienteFriar.query.get_or_404(id)
    data = request.get_json()
    
    # Validar justificación requerida
    justificacion = data.get("justificacion")
    if not justificacion or not justificacion.strip():
        return jsonify({"error": "Campo requerido: justificacion"}), 400
    
    try:
        # Guardar estado anterior
        campos_anteriores = {
            "saldo_inicial": float(cuenta.saldo_inicial),
            "observaciones": cuenta.observaciones
        }
        
        # Actualizar campos permitidos
        if "saldo_inicial" in data:
            cuenta.saldo_inicial = Decimal(str(data["saldo_inicial"]))
        if "observaciones" in data:
            cuenta.observaciones = data["observaciones"]
        
        # Actualizar campos de auditoría
        usuario_id = session.get("user_id")
        cuenta.editado_por_id = usuario_id
        cuenta.fecha_edicion = datetime.utcnow()
        
        # Crear log de edición
        campos_nuevos = {
            "saldo_inicial": float(cuenta.saldo_inicial),
            "observaciones": cuenta.observaciones
        }
        
        log = LogCuentaCorrienteFriar(
            cuenta_corriente_id=id,
            usuario_id=usuario_id,
            campos_anteriores=campos_anteriores,
            campos_nuevos=campos_nuevos,
            justificacion=justificacion.strip()
        )
        
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Cuenta corriente actualizada correctamente",
            "cuenta": {
                "id": cuenta.id,
                "saldo_inicial": float(cuenta.saldo_inicial),
                "observaciones": cuenta.observaciones
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar cuenta: {str(e)}"}), 500


@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar/<int:id>/logs", methods=["GET"])
def cuenta_corriente_logs(id):
    """Obtener historial de ediciones de la cuenta corriente"""
    cuenta = CuentaCorrienteFriar.query.get_or_404(id)
    logs = LogCuentaCorrienteFriar.query.filter_by(cuenta_corriente_id=id).order_by(
        LogCuentaCorrienteFriar.fecha_edicion.desc()
    ).all()
    
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


# =============================================================================
# ENDPOINTS API - PAGOS A FRIAR
# =============================================================================

@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar/pagos", methods=["GET"])
def pagos_listar():
    """Listar pagos a Friar"""
    cuenta = CuentaCorrienteFriar.query.first()
    
    if not cuenta:
        return jsonify({"pagos": [], "total": 0})
    
    # Filtros
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    
    query = PagoFriar.query.filter_by(cuenta_corriente_id=cuenta.id)
    
    if fecha_desde:
        query = query.filter(PagoFriar.fecha >= datetime.strptime(fecha_desde, "%Y-%m-%d"))
    if fecha_hasta:
        query = query.filter(PagoFriar.fecha <= datetime.strptime(fecha_hasta + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
    
    pagos = query.order_by(PagoFriar.fecha.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        "pagos": [{
            "id": p.id,
            "fecha": p.fecha.isoformat(),
            "monto": float(p.monto),
            "instrumento": p.instrumento.nombre if p.instrumento else None,
            "descripcion": p.descripcion,
            "referencia": p.referencia,
            "usuario": p.usuario.username if p.usuario else None
        } for p in pagos.items],
        "total": pagos.total,
        "pages": pagos.pages,
        "current_page": pagos.page
    })


@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar/pagos", methods=["POST"])
def pagos_crear():
    """Registrar nuevo pago a Friar"""
    cuenta = CuentaCorrienteFriar.query.first()
    
    if not cuenta:
        return jsonify({"error": "No existe cuenta corriente Friar configurada"}), 400
    
    data = request.get_json()
    
    monto = data.get("monto")
    instrumento_id = data.get("instrumento_id")
    descripcion = data.get("descripcion")
    
    if not monto or not instrumento_id or not descripcion:
        return jsonify({"error": "Monto, instrumento y descripción requeridos"}), 400
    
    # Validar instrumento
    instrumento = InstrumentoPago.query.get(instrumento_id)
    if not instrumento:
        return jsonify({"error": "Instrumento no encontrado"}), 404
    
    try:
        monto_decimal = Decimal(str(monto))
        if monto_decimal <= 0:
            return jsonify({"error": "El monto debe ser mayor a cero"}), 400
        
        usuario_id = session.get("user_id", 1)
        
        pago = PagoFriar(
            cuenta_corriente_id=cuenta.id,
            monto=monto_decimal,
            instrumento_id=instrumento_id,
            descripcion=descripcion,
            referencia=data.get("referencia"),
            usuario_id=usuario_id,
            fecha=datetime.strptime(data.get("fecha"), "%Y-%m-%d") if data.get("fecha") else datetime.utcnow()
        )
        
        db.session.add(pago)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Pago registrado correctamente",
            "pago": {
                "id": pago.id,
                "monto": float(pago.monto),
                "fecha": pago.fecha.isoformat()
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al registrar pago: {str(e)}"}), 500


@cta_cte_friar_bp.route("/api/tesoreria/cta-cte-friar/pagos/<int:id>", methods=["DELETE"])
def pagos_eliminar(id):
    """Eliminar pago (solo admin)"""
    auth_error = require_admin()
    if auth_error:
        return auth_error
    
    pago = PagoFriar.query.get_or_404(id)
    
    try:
        db.session.delete(pago)
        db.session.commit()
        return jsonify({"success": True, "message": "Pago eliminado"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar pago: {str(e)}"}), 500
