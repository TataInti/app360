from datetime import datetime, timedelta
from decimal import Decimal
import io

from flask import Blueprint, request, jsonify, send_file, render_template, session

from models import (
    CategoriaGasto,
    Gasto,
    Proveedor,
    User,
    db,
)
from security import protect_blueprint

gastos_bp = Blueprint("gastos", __name__)

protect_blueprint(gastos_bp, "gastos")  # Permisos de gastos


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
    """Listar gastos con filtros"""
    # Filtros
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    categoria_id = request.args.get("categoria_id")
    proveedor_id = request.args.get("proveedor_id")
    pagado = request.args.get("pagado")
    limite = request.args.get("limite", 100, type=int)

    query = Gasto.query

    # Aplicar filtros
    if fecha_desde:
        try:
            fecha_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(Gasto.fecha >= fecha_desde)
        except ValueError:
            return jsonify({"error": "Formato de fecha_desde inválido"}), 400

    if fecha_hasta:
        try:
            fecha_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(Gasto.fecha <= fecha_hasta)
        except ValueError:
            return jsonify({"error": "Formato de fecha_hasta inválido"}), 400

    if categoria_id:
        query = query.filter(Gasto.categoria_id == categoria_id)

    if proveedor_id:
        query = query.filter(Gasto.proveedor_id == proveedor_id)

    if pagado is not None:
        pagado_bool = pagado.lower() == "true"
        query = query.filter(Gasto.pagado == pagado_bool)

    # Ordenar por fecha descendente
    gastos = query.order_by(Gasto.fecha.desc()).limit(limite).all()

    return jsonify({
        "gastos": [{
            "id": g.id,
            "fecha": g.fecha.isoformat(),
            "descripcion": g.descripcion,
            "monto": float(g.monto),
            "categoria": {
                "id": g.categoria.id,
                "nombre": g.categoria.nombre
            },
            "proveedor": {
                "id": g.proveedor.id,
                "nombre": g.proveedor.nombre
            },
            "categoria_nombre": g.categoria.nombre,
            "proveedor_nombre": g.proveedor.nombre,
            "numero_factura": g.numero_factura,
            "fecha_vencimiento": g.fecha_vencimiento.isoformat() if g.fecha_vencimiento else None,
            "pagado": g.pagado,
            "estado": "pagado" if g.pagado else "pendiente",
            "fecha_pago": g.fecha_pago.isoformat() if g.fecha_pago else None,
            "usuario": g.usuario.username if g.usuario else None
        } for g in gastos]
    })


@gastos_bp.route("/api/gastos/registrar", methods=["POST"])
def gastos_registrar():
    """Registrar nuevo gasto"""
    data = request.get_json()

    required_fields = ["descripcion", "monto", "categoria_id", "proveedor_id"]
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    try:
        monto = Decimal(str(data["monto"]))
        if monto <= 0:
            return jsonify({"error": "Monto debe ser mayor a cero"}), 400
    except:
        return jsonify({"error": "Monto inválido"}), 400

    # Verificar que exista categoria
    categoria = CategoriaGasto.query.get(data["categoria_id"])
    if not categoria or not categoria.activo:
        return jsonify({"error": "Categoría no encontrada o inactiva"}), 404

    # Verificar que exista proveedor
    proveedor = Proveedor.query.get(data["proveedor_id"])
    if not proveedor or not proveedor.activo:
        return jsonify({"error": "Proveedor no encontrado o inactivo"}), 404

    # Parsear fechas opcionales
    fecha = data.get("fecha")
    if fecha:
        try:
            fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido"}), 400
    else:
        fecha = datetime.now().date()

    fecha_vencimiento = data.get("fecha_vencimiento")
    if fecha_vencimiento:
        try:
            fecha_vencimiento = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de fecha_vencimiento inválido"}), 400

    # Obtener usuario actual
    usuario_id = data.get("usuario_id")
    if not usuario_id:
        session_user = session.get("user")
        if session_user:
            usuario = User.query.filter_by(username=session_user).first()
            if usuario:
                usuario_id = usuario.id

    if not usuario_id:
        return jsonify({"error": "Usuario no encontrado"}), 401

    estado = data.get("estado")
    pagado = bool(data.get("pagado")) or (estado == "pagado")
    fecha_pago = datetime.utcnow() if pagado else None

    gasto = Gasto(
        fecha=fecha,
        descripcion=data["descripcion"],
        monto=monto,
        categoria_id=data["categoria_id"],
        proveedor_id=data["proveedor_id"],
        numero_factura=data.get("numero_factura"),
        fecha_vencimiento=fecha_vencimiento,
        pagado=pagado,
        fecha_pago=fecha_pago,
        usuario_id=usuario_id
    )

    db.session.add(gasto)
    db.session.commit()

    return jsonify({
        "message": "Gasto registrado",
        "gasto": {
            "id": gasto.id,
            "fecha": gasto.fecha.isoformat(),
            "descripcion": gasto.descripcion,
            "monto": float(gasto.monto),
            "categoria": gasto.categoria.nombre,
            "proveedor": gasto.proveedor.nombre
        }
    }), 201


@gastos_bp.route("/api/gastos/<int:gasto_id>", methods=["GET"])
def gastos_detalle(gasto_id):
    """Obtener detalle de un gasto"""
    gasto = Gasto.query.get_or_404(gasto_id)
    return jsonify({
        "id": gasto.id,
        "fecha": gasto.fecha.isoformat() if gasto.fecha else None,
        "descripcion": gasto.descripcion,
        "monto": float(gasto.monto),
        "categoria_id": gasto.categoria_id,
        "proveedor_id": gasto.proveedor_id,
        "numero_factura": gasto.numero_factura,
        "fecha_vencimiento": gasto.fecha_vencimiento.isoformat() if gasto.fecha_vencimiento else None,
        "pagado": gasto.pagado,
        "estado": "pagado" if gasto.pagado else "pendiente",
    })


@gastos_bp.route("/api/gastos/<int:gasto_id>", methods=["PUT"])
def gastos_actualizar(gasto_id):
    """Actualizar un gasto"""
    gasto = Gasto.query.get_or_404(gasto_id)
    data = request.get_json() or {}

    required_fields = ["descripcion", "monto", "categoria_id", "proveedor_id", "fecha"]
    for field in required_fields:
        if field not in data or data[field] in (None, ""):
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    try:
        monto = Decimal(str(data["monto"]))
        if monto <= 0:
            return jsonify({"error": "Monto debe ser mayor a cero"}), 400
    except Exception:
        return jsonify({"error": "Monto inválido"}), 400

    categoria = CategoriaGasto.query.get(data["categoria_id"])
    if not categoria or not categoria.activo:
        return jsonify({"error": "Categoría no encontrada o inactiva"}), 404

    proveedor = Proveedor.query.get(data["proveedor_id"])
    if not proveedor or not proveedor.activo:
        return jsonify({"error": "Proveedor no encontrado o inactivo"}), 404

    try:
        fecha = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    fecha_vencimiento = data.get("fecha_vencimiento")
    if fecha_vencimiento:
        try:
            fecha_vencimiento = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de fecha_vencimiento inválido"}), 400

    estado = data.get("estado")
    pagado = bool(data.get("pagado")) or (estado == "pagado")
    fecha_pago = datetime.utcnow() if pagado else None

    gasto.descripcion = data["descripcion"]
    gasto.monto = monto
    gasto.categoria_id = data["categoria_id"]
    gasto.proveedor_id = data["proveedor_id"]
    gasto.fecha = fecha
    gasto.numero_factura = data.get("numero_factura")
    gasto.fecha_vencimiento = fecha_vencimiento
    gasto.pagado = pagado
    gasto.fecha_pago = fecha_pago

    db.session.commit()
    return jsonify({"message": "Gasto actualizado"})


@gastos_bp.route("/api/gastos/<int:gasto_id>/pagar", methods=["POST"])
def gastos_pagar(gasto_id):
    """Marcar gasto como pagado"""
    gasto = Gasto.query.get_or_404(gasto_id)

    if gasto.pagado:
        return jsonify({"error": "Gasto ya está pagado"}), 400

    gasto.pagado = True
    gasto.fecha_pago = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Gasto marcado como pagado"})


@gastos_bp.route("/api/gastos/vencimientos", methods=["GET"])
def gastos_vencimientos():
    """Listar gastos próximos a vencer"""
    dias = request.args.get("dias", 7, type=int)

    fecha_limite = datetime.now().date() + timedelta(days=dias)

    gastos = Gasto.query.filter(
        Gasto.fecha_vencimiento <= fecha_limite,
        Gasto.pagado == False,
        Gasto.fecha_vencimiento >= datetime.now().date()
    ).order_by(Gasto.fecha_vencimiento).all()

    return jsonify({
        "vencimientos": [{
            "id": g.id,
            "fecha_vencimiento": g.fecha_vencimiento.isoformat(),
            "descripcion": g.descripcion,
            "monto": float(g.monto),
            "proveedor": g.proveedor.nombre,
            "dias_restantes": (g.fecha_vencimiento - datetime.now().date()).days
        } for g in gastos]
    })


@gastos_bp.route("/api/gastos/resumen", methods=["GET"])
def gastos_resumen():
    """Resumen de gastos por período"""
    periodo = request.args.get("periodo", "mes")  # mes, trimestre, año

    hoy = datetime.now().date()

    if periodo == "mes":
        fecha_inicio = hoy.replace(day=1)
        fecha_fin = hoy
    elif periodo == "trimestre":
        trimestre = (hoy.month - 1) // 3 + 1
        mes_inicio = (trimestre - 1) * 3 + 1
        fecha_inicio = hoy.replace(month=mes_inicio, day=1)
        fecha_fin = hoy
    elif periodo == "año":
        fecha_inicio = hoy.replace(month=1, day=1)
        fecha_fin = hoy
    else:
        return jsonify({"error": "Período inválido"}), 400

    # Gastos del período
    gastos = Gasto.query.filter(
        Gasto.fecha >= fecha_inicio,
        Gasto.fecha <= fecha_fin
    ).all()

    # Calcular totales
    total_gastos = sum(g.monto for g in gastos)
    gastos_pagados = sum(g.monto for g in gastos if g.pagado)
    gastos_pendientes = sum(g.monto for g in gastos if not g.pagado)

    # Por categoría
    categorias = {}
    for gasto in gastos:
        cat_nombre = gasto.categoria.nombre
        if cat_nombre not in categorias:
            categorias[cat_nombre] = {"total": 0, "pagado": 0, "pendiente": 0}
        categorias[cat_nombre]["total"] += gasto.monto
        if gasto.pagado:
            categorias[cat_nombre]["pagado"] += gasto.monto
        else:
            categorias[cat_nombre]["pendiente"] += gasto.monto

    return jsonify({
        "periodo": {
            "inicio": fecha_inicio.isoformat(),
            "fin": fecha_fin.isoformat(),
            "tipo": periodo
        },
        "totales": {
            "total": float(total_gastos),
            "pagado": float(gastos_pagados),
            "pendiente": float(gastos_pendientes)
        },
        "por_categoria": {
            cat: {
                "total": float(data["total"]),
                "pagado": float(data["pagado"]),
                "pendiente": float(data["pendiente"])
            } for cat, data in categorias.items()
        }
    })


@gastos_bp.route("/api/gastos/exportar", methods=["GET"])
def gastos_exportar():
    """Exportar gastos a Excel"""
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"error": "Pandas no instalado"}), 500

    # Obtener filtros de la query
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    categoria_id = request.args.get("categoria_id")
    proveedor_id = request.args.get("proveedor_id")
    pagado = request.args.get("pagado")

    query = Gasto.query

    # Aplicar mismos filtros que en listar
    if fecha_desde:
        fecha_desde = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
        query = query.filter(Gasto.fecha >= fecha_desde)

    if fecha_hasta:
        fecha_hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
        query = query.filter(Gasto.fecha <= fecha_hasta)

    if categoria_id:
        query = query.filter(Gasto.categoria_id == categoria_id)

    if proveedor_id:
        query = query.filter(Gasto.proveedor_id == proveedor_id)

    if pagado is not None:
        pagado_bool = pagado.lower() == "true"
        query = query.filter(Gasto.pagado == pagado_bool)

    gastos = query.order_by(Gasto.fecha.desc()).all()

    # Crear DataFrame
    data = []
    for g in gastos:
        data.append({
            "Fecha": g.fecha,
            "Descripción": g.descripcion,
            "Monto": float(g.monto),
            "Categoría": g.categoria.nombre,
            "Proveedor": g.proveedor.nombre,
            "N° Factura": g.numero_factura or "",
            "Fecha Vencimiento": g.fecha_vencimiento,
            "Pagado": "Sí" if g.pagado else "No",
            "Fecha Pago": g.fecha_pago,
            "Usuario": g.usuario.username if g.usuario else ""
        })

    df = pd.DataFrame(data)

    # Crear archivo Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Gastos', index=False)

    output.seek(0)

    # Generar nombre de archivo
    fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gastos_{fecha_actual}.xlsx"

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )