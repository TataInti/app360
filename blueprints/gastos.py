"""
Blueprint de Gastos — vista filtrada de MovimientoCaja con categoria_gasto_id.
Todos los gastos son MovimientoCaja tipo 'egreso' con categoria_gasto obligatoria.
"""
from datetime import datetime, timedelta
from decimal import Decimal
import io

from flask import Blueprint, request, jsonify, send_file, render_template, session
from sqlalchemy import func

from models import (
    CategoriaGasto,
    InstrumentoPago,
    MovimientoCaja,
    Proveedor,
    User,
    db,
)
from models.tesoreria import PortadorInstrumento
from security import protect_blueprint

gastos_bp = Blueprint("gastos", __name__)

protect_blueprint(gastos_bp, "gastos")


def _gastos_query():
    """MovimientoCaja con categoria_gasto_id definida y no anulados."""
    return MovimientoCaja.query.filter(
        MovimientoCaja.categoria_gasto_id.isnot(None),
        MovimientoCaja.estado != "anulado",
    )


# RUTAS WEB
@gastos_bp.route("/gastos", methods=["GET"])
def gastos_panel():
    """Panel principal de gastos"""
    return render_template("gastos_panel.html")


# Endpoints para Categorías de Gastos

@gastos_bp.route("/api/gastos/categorias", methods=["GET"])
def categorias_listar():
    """Listar categorías de gastos activas"""
    categorias = CategoriaGasto.query.filter_by(activo=True).order_by(CategoriaGasto.nombre).all()

    return jsonify({
        "categorias": [{
            "id": c.id,
            "nombre": c.nombre,
            "descripcion": c.descripcion
        } for c in categorias]
    })


@gastos_bp.route("/api/gastos/categorias", methods=["POST"])
def categorias_crear():
    """Crear nueva categoría de gasto"""
    data = request.get_json()

    required_fields = ["nombre"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    nombre = data["nombre"].strip()
    if not nombre:
        return jsonify({"error": "Nombre no puede estar vacío"}), 400

    # Verificar que no exista
    existente = CategoriaGasto.query.filter_by(nombre=nombre).first()
    if existente:
        return jsonify({"error": "Ya existe una categoría con ese nombre"}), 400

    categoria = CategoriaGasto(
        nombre=nombre,
        descripcion=data.get("descripcion", "")
    )

    db.session.add(categoria)
    db.session.commit()

    return jsonify({
        "message": "Categoría creada",
        "categoria": {
            "id": categoria.id,
            "nombre": categoria.nombre,
            "descripcion": categoria.descripcion
        }
    }), 201


# Endpoints para Proveedores

@gastos_bp.route("/api/gastos/proveedores", methods=["GET"])
def proveedores_listar():
    """Listar proveedores activos"""
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    return jsonify({
        "proveedores": [{
            "id": p.id,
            "nombre": p.nombre,
            "cuit": p.cuit,
            "email": p.email,
            "telefono": p.telefono,
            "direccion": p.direccion
        } for p in proveedores]
    })


@gastos_bp.route("/api/gastos/proveedores", methods=["POST"])
def proveedores_crear():
    """Crear nuevo proveedor"""
    data = request.get_json()

    required_fields = ["nombre"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    nombre = data["nombre"].strip()
    if not nombre:
        return jsonify({"error": "Nombre no puede estar vacío"}), 400

    # Verificar CUIT único si se proporciona
    cuit = data.get("cuit")
    if cuit:
        existente = Proveedor.query.filter_by(cuit=cuit).first()
        if existente:
            return jsonify({"error": "Ya existe un proveedor con ese CUIT"}), 400

    proveedor = Proveedor(
        nombre=nombre,
        cuit=cuit,
        email=data.get("email"),
        telefono=data.get("telefono"),
        direccion=data.get("direccion")
    )

    db.session.add(proveedor)
    db.session.commit()

    return jsonify({
        "message": "Proveedor creado",
        "proveedor": {
            "id": proveedor.id,
            "nombre": proveedor.nombre,
            "cuit": proveedor.cuit
        }
    }), 201


# Endpoints para Gastos

@gastos_bp.route("/api/gastos/listar", methods=["GET"])
def gastos_listar():
    """Listar gastos (movimientos con categoría de gasto) con filtros"""
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    categoria_id = request.args.get("categoria_id")
    proveedor_id = request.args.get("proveedor_id")
    instrumento_id = request.args.get("instrumento_id")
    limite = request.args.get("limite", 200, type=int)

    query = _gastos_query()

    if fecha_desde:
        query = query.filter(MovimientoCaja.fecha_hora >= datetime.strptime(fecha_desde, "%Y-%m-%d"))
    if fecha_hasta:
        query = query.filter(
            MovimientoCaja.fecha_hora <= datetime.strptime(fecha_hasta + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        )
    if categoria_id:
        query = query.filter(MovimientoCaja.categoria_gasto_id == categoria_id)
    if proveedor_id:
        query = query.filter(MovimientoCaja.proveedor_id == proveedor_id)
    if instrumento_id:
        query = query.filter(MovimientoCaja.instrumento_id == instrumento_id)

    movimientos = query.order_by(MovimientoCaja.fecha_hora.desc()).limit(limite).all()

    return jsonify({
        "gastos": [{
            "id": m.id,
            "fecha": m.fecha_hora.strftime("%Y-%m-%d"),
            "fecha_hora": m.fecha_hora.isoformat(),
            "descripcion": m.descripcion,
            "monto": float(m.monto),
            "tipo": m.tipo,
            "categoria_nombre": m.categoria_gasto.nombre if m.categoria_gasto else "-",
            "proveedor_nombre": m.proveedor.nombre if m.proveedor else "-",
            "instrumento": m.instrumento.nombre if m.instrumento else "-",
            "portador": m.portador.nombre if m.portador else None,
            "referencia": m.referencia,
            "estado": m.estado,
            "usuario": m.usuario.username if m.usuario else None
        } for m in movimientos]
    })


@gastos_bp.route("/api/gastos/registrar", methods=["POST"])
def gastos_registrar():
    """Registrar nuevo gasto = MovimientoCaja tipo egreso con categoria_gasto obligatoria"""
    data = request.get_json()

    required = ["descripcion", "monto", "categoria_gasto_id", "proveedor_id", "instrumento_id"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    try:
        monto = Decimal(str(data["monto"]))
        if monto <= 0:
            return jsonify({"error": "Monto debe ser mayor a cero"}), 400
    except Exception:
        return jsonify({"error": "Monto inválido"}), 400

    categoria = CategoriaGasto.query.get(data["categoria_gasto_id"])
    if not categoria or not categoria.activo:
        return jsonify({"error": "Categoría no encontrada o inactiva"}), 404

    proveedor = Proveedor.query.get(data["proveedor_id"])
    if not proveedor or not proveedor.activo:
        return jsonify({"error": "Proveedor no encontrado o inactivo"}), 404

    instrumento = InstrumentoPago.query.get(data["instrumento_id"])
    if not instrumento or not instrumento.activo:
        return jsonify({"error": "Instrumento no encontrado o inactivo"}), 404

    portador_id = data.get("portador_id")
    if instrumento.requiere_portador and not portador_id:
        return jsonify({"error": "Este instrumento requiere indicar un portador"}), 400
    if portador_id:
        portador = PortadorInstrumento.query.get(portador_id)
        if not portador or not portador.activo:
            return jsonify({"error": "Portador no encontrado o inactivo"}), 404
        # Si el instrumento tiene lista M2M configurada, validar pertenencia
        allowed = instrumento.portadores_permitidos
        if allowed and portador not in allowed:
            return jsonify({"error": "El portador seleccionado no está habilitado para este instrumento"}), 400

    usuario_id = data.get("usuario_id")
    if not usuario_id:
        session_user = session.get("user")
        if session_user:
            usuario = User.query.filter_by(username=session_user).first()
            if usuario:
                usuario_id = usuario.id
    if not usuario_id:
        return jsonify({"error": "Usuario no encontrado"}), 401

    movimiento = MovimientoCaja(
        tipo="egreso",
        monto=monto,
        descripcion=data["descripcion"].strip(),
        instrumento_id=data["instrumento_id"],
        categoria_gasto_id=data["categoria_gasto_id"],
        proveedor_id=data["proveedor_id"],
        portador_id=portador_id if portador_id else None,
        usuario_id=usuario_id,
        referencia=data.get("referencia"),
        cliente_proveedor=proveedor.nombre,
    )
    db.session.add(movimiento)
    db.session.commit()

    return jsonify({
        "message": "Gasto registrado",
        "movimiento": {
            "id": movimiento.id,
            "monto": float(movimiento.monto),
            "descripcion": movimiento.descripcion,
            "instrumento": movimiento.instrumento.nombre
        }
    }), 201


@gastos_bp.route("/api/gastos/resumen", methods=["GET"])
def gastos_resumen():
    """Resumen y KPIs de gastos del período"""
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    if not fecha_desde or not fecha_hasta:
        hoy = datetime.now().date()
        fecha_desde = fecha_desde or hoy.replace(day=1).isoformat()
        fecha_hasta = fecha_hasta or hoy.isoformat()

    dt_desde = datetime.strptime(fecha_desde, "%Y-%m-%d")
    dt_hasta = datetime.strptime(fecha_hasta + " 23:59:59", "%Y-%m-%d %H:%M:%S")

    gastos = _gastos_query().filter(
        MovimientoCaja.fecha_hora >= dt_desde,
        MovimientoCaja.fecha_hora <= dt_hasta,
    ).all()

    total = sum(float(g.monto) for g in gastos)
    cant = len(gastos)

    por_categoria = {}
    for g in gastos:
        cat = g.categoria_gasto.nombre if g.categoria_gasto else "Sin categoría"
        por_categoria[cat] = por_categoria.get(cat, 0) + float(g.monto)

    por_proveedor = {}
    for g in gastos:
        prov = g.proveedor.nombre if g.proveedor else "Sin proveedor"
        por_proveedor[prov] = por_proveedor.get(prov, 0) + float(g.monto)

    por_instrumento = {}
    for g in gastos:
        inst = g.instrumento.nombre if g.instrumento else "?"
        por_instrumento[inst] = por_instrumento.get(inst, 0) + float(g.monto)

    evo = {}
    for g in gastos:
        dia = g.fecha_hora.strftime("%Y-%m-%d")
        evo[dia] = evo.get(dia, 0) + float(g.monto)

    return jsonify({
        "total": total,
        "cantidad": cant,
        "promedio": round(total / cant, 2) if cant else 0,
        "por_categoria": por_categoria,
        "por_proveedor": por_proveedor,
        "por_instrumento": por_instrumento,
        "evolucion_diaria": evo,
    })


@gastos_bp.route("/api/gastos/exportar", methods=["GET"])
def gastos_exportar():
    """Exportar gastos a Excel"""
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"error": "Pandas no instalado"}), 500

    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    categoria_id = request.args.get("categoria_id")
    proveedor_id = request.args.get("proveedor_id")

    query = _gastos_query()
    if fecha_desde:
        query = query.filter(MovimientoCaja.fecha_hora >= datetime.strptime(fecha_desde, "%Y-%m-%d"))
    if fecha_hasta:
        query = query.filter(
            MovimientoCaja.fecha_hora <= datetime.strptime(fecha_hasta + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        )
    if categoria_id:
        query = query.filter(MovimientoCaja.categoria_gasto_id == categoria_id)
    if proveedor_id:
        query = query.filter(MovimientoCaja.proveedor_id == proveedor_id)

    movimientos = query.order_by(MovimientoCaja.fecha_hora.desc()).all()

    rows = []
    for m in movimientos:
        rows.append({
            "Fecha/Hora": m.fecha_hora,
            "Monto": float(m.monto),
            "Categoría": m.categoria_gasto.nombre if m.categoria_gasto else "",
            "Proveedor": m.proveedor.nombre if m.proveedor else "",
            "Instrumento": m.instrumento.nombre if m.instrumento else "",
            "Portador": m.portador.nombre if m.portador else "",
            "Descripción": m.descripcion,
            "Referencia": m.referencia or "",
            "Usuario": m.usuario.username if m.usuario else "",
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Gastos", index=False)
    output.seek(0)

    filename = f"gastos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )