from datetime import datetime, date, timedelta
from decimal import Decimal
import io

from flask import Blueprint, request, jsonify, send_file, render_template
from sqlalchemy import func, desc, extract

from models import (
    Adelanto,
    Asistencia,
    BusinessUnit,
    Employee,
    Gasto,
    Lead,
    Location,
    Product,
    Promocion,
    StockLevel,
    Venta,
    db,
)
from security import protect_blueprint

bi_bp = Blueprint("bi", __name__)

protect_blueprint(bi_bp, "panel")  # Usar permisos de panel ejecutivo


# RUTAS WEB
@bi_bp.route("/bi", methods=["GET"])
def bi_dashboard_web():
    """Dashboard de Business Intelligence"""
    return render_template("bi_dashboard.html")


# Endpoint principal del dashboard BI
@bi_bp.route("/api/bi/dashboard", methods=["GET"])
def bi_dashboard():
    """Dashboard principal con KPIs principales"""
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    # Si no se especifican fechas, usar último mes
    if not fecha_desde:
        fecha_desde = (date.today() - timedelta(days=30)).isoformat()
    if not fecha_hasta:
        fecha_hasta = date.today().isoformat()

    try:
        fecha_desde = datetime.fromisoformat(fecha_desde).date()
        fecha_hasta = datetime.fromisoformat(fecha_hasta).date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    # KPIs principales
    kpis = {}

    # 1. Ventas totales
    ventas_total = db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad)).filter(
        Venta.fecha.between(fecha_desde, fecha_hasta)
    ).scalar() or 0
    kpis["ventas_totales"] = float(ventas_total)

    # 2. Número de ventas
    num_ventas = Venta.query.filter(
        Venta.fecha.between(fecha_desde, fecha_hasta)
    ).count()
    kpis["numero_ventas"] = num_ventas

    # 3. Ticket promedio
    kpis["ticket_promedio"] = float(ventas_total / num_ventas) if num_ventas > 0 else 0

    # 4. Gastos totales
    gastos_total = db.session.query(func.sum(Gasto.monto)).filter(
        Gasto.fecha.between(fecha_desde, fecha_hasta)
    ).scalar() or 0
    kpis["gastos_totales"] = float(gastos_total)

    # 5. Margen (ventas - gastos)
    kpis["margen_bruto"] = float(ventas_total - gastos_total)

    # 6. Número de productos
    kpis["total_productos"] = Product.query.count()

    # 7. Número de ubicaciones
    kpis["total_ubicaciones"] = Location.query.count()

    # 8. Stock total
    stock_total = db.session.query(func.sum(StockLevel.quantity)).scalar() or 0
    kpis["stock_total"] = int(stock_total)

    # 9. Empleados activos
    kpis["empleados_activos"] = Employee.query.filter_by(is_active=True).count()

    # 10. Leads totales
    kpis["total_leads"] = Lead.query.count()

    # 11. Conversión de leads
    leads_ganados = Lead.query.filter_by(status="ganado").count()
    kpis["conversion_leads"] = round((leads_ganados / kpis["total_leads"] * 100), 2) if kpis["total_leads"] > 0 else 0

    # 12. Asistencia promedio (últimos 30 días)
    asistencia_reciente = Asistencia.query.filter(
        Asistencia.fecha >= (date.today() - timedelta(days=30))
    ).all()

    if asistencia_reciente:
        presentes = sum(1 for a in asistencia_reciente if a.estado == 'presente')
        kpis["asistencia_promedio"] = round((presentes / len(asistencia_reciente) * 100), 2)
    else:
        kpis["asistencia_promedio"] = 0

    # 13. Adelantos pendientes
    adelantos_pendientes = Adelanto.query.filter_by(aprobado=True, pagado=False).count()
    kpis["adelantos_pendientes"] = adelantos_pendientes

    # 14. Promociones activas
    promociones_activas = Promocion.query.filter(
        Promocion.activo == True,
        Promocion.fecha_inicio <= date.today(),
        Promocion.fecha_fin >= date.today()
    ).count()
    kpis["promociones_activas"] = promociones_activas

    return jsonify({
        "periodo": {
            "desde": fecha_desde.isoformat(),
            "hasta": fecha_hasta.isoformat()
        },
        "kpis": kpis
    })


# Rankings y análisis
@bi_bp.route("/api/bi/ranking", methods=["GET"])
def bi_ranking():
    """Rankings por productos, clientes, etc."""
    tipo = request.args.get("tipo", "productos")  # productos, clientes, ubicaciones
    limite = request.args.get("limite", 10, type=int)
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    # Si no se especifican fechas, usar último mes
    if not fecha_desde:
        fecha_desde = (date.today() - timedelta(days=30))
    else:
        fecha_desde = datetime.fromisoformat(fecha_desde).date()

    if not fecha_hasta:
        fecha_hasta = date.today()
    else:
        fecha_hasta = datetime.fromisoformat(fecha_hasta).date()

    if tipo == "productos":
        # Productos más vendidos
        ranking = (
            db.session.query(
                Product.name,
                func.sum(Venta.cantidad).label('total_vendido'),
                func.sum(Venta.precio_efectivo * Venta.cantidad).label('total_venta')
            )
            .join(Venta, Venta.producto_id == Product.id)
            .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
            .group_by(Product.name)
            .order_by(desc('total_vendido'))
            .limit(limite)
            .all()
        )

        resultado = [{
            "producto": r[0],
            "cantidad_vendida": int(r[1]),
            "total_venta": float(r[2])
        } for r in ranking]

    elif tipo == "ubicaciones":
        # Ubicaciones con más stock
        ranking = (
            db.session.query(
                Location.name,
                func.sum(StockLevel.quantity).label('total_stock')
            )
            .join(StockLevel, StockLevel.location_id == Location.id)
            .group_by(Location.name)
            .order_by(desc('total_stock'))
            .limit(limite)
            .all()
        )

        resultado = [{
            "ubicacion": r[0],
            "stock_total": int(r[1])
        } for r in ranking]

    elif tipo == "unidades_negocio":
        # Unidades de negocio con más productos
        ranking = (
            db.session.query(
                BusinessUnit.name,
                func.count(Product.id).label('total_productos')
            )
            .join(Product, Product.business_unit_id == BusinessUnit.id)
            .group_by(BusinessUnit.name)
            .order_by(desc('total_productos'))
            .limit(limite)
            .all()
        )

        resultado = [{
            "unidad_negocio": r[0],
            "total_productos": int(r[1])
        } for r in ranking]

    else:
        return jsonify({"error": f"Tipo de ranking inválido: {tipo}"}), 400

    return jsonify({
        "tipo_ranking": tipo,
        "periodo": {
            "desde": fecha_desde.isoformat(),
            "hasta": fecha_hasta.isoformat()
        },
        "ranking": resultado
    })


# Reportes diarios
@bi_bp.route("/api/reportes/resumen-diario", methods=["GET"])
def resumen_diario():
    """Resumen diario del negocio"""
    fecha = request.args.get("fecha")
    if not fecha:
        fecha = date.today()
    else:
        try:
            fecha = datetime.fromisoformat(fecha).date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido"}), 400

    resumen = {}

    # Ventas del día
    ventas_dia = db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad)).filter(
        Venta.fecha == fecha
    ).scalar() or 0
    resumen["ventas_dia"] = float(ventas_dia)

    num_ventas_dia = Venta.query.filter(Venta.fecha == fecha).count()
    resumen["numero_ventas_dia"] = num_ventas_dia

    # Gastos del día
    gastos_dia = db.session.query(func.sum(Gasto.monto)).filter(
        Gasto.fecha == fecha
    ).scalar() or 0
    resumen["gastos_dia"] = float(gastos_dia)

    # Asistencia del día
    asistencia_dia = Asistencia.query.filter(Asistencia.fecha == fecha).all()
    resumen["total_asistencia"] = len(asistencia_dia)

    if asistencia_dia:
        presentes = sum(1 for a in asistencia_dia if a.estado == 'presente')
        resumen["asistencia_presentes"] = presentes
        resumen["tasa_asistencia"] = round((presentes / len(asistencia_dia) * 100), 2)
    else:
        resumen["asistencia_presentes"] = 0
        resumen["tasa_asistencia"] = 0

    # Leads nuevos del día
    leads_dia = Lead.query.filter(
        func.date(Lead.created_at) == fecha
    ).count()
    resumen["leads_nuevos"] = leads_dia

    # Comparación con día anterior
    fecha_anterior = fecha - timedelta(days=1)

    ventas_anterior = db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad)).filter(
        Venta.fecha == fecha_anterior
    ).scalar() or 0

    if ventas_anterior > 0:
        resumen["variacion_ventas"] = round(((ventas_dia - ventas_anterior) / ventas_anterior * 100), 2)
    else:
        resumen["variacion_ventas"] = 0

    return jsonify({
        "fecha": fecha.isoformat(),
        "resumen": resumen
    })


# Exportación de reportes
@bi_bp.route("/api/bi/exportar", methods=["GET"])
def bi_exportar():
    """Exportar datos de BI a Excel"""
    try:
        import pandas as pd
    except ImportError:
        return jsonify({"error": "Pandas no instalado"}), 500

    tipo = request.args.get("tipo", "dashboard")  # dashboard, ranking, resumen
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")

    if tipo == "ventas_resumen":
        # Resumen de ventas por período
        query = Venta.query
        if fecha_desde:
            fecha_desde = datetime.fromisoformat(fecha_desde).date()
            query = query.filter(Venta.fecha >= fecha_desde)
        if fecha_hasta:
            fecha_hasta = datetime.fromisoformat(fecha_hasta).date()
            query = query.filter(Venta.fecha <= fecha_hasta)

        ventas = query.order_by(Venta.fecha.desc()).all()

        data = []
        for v in ventas:
            data.append({
                "Fecha": v.fecha,
                "Cliente": v.cliente.name if v.cliente else "",
                "Producto": v.producto.name if v.producto else "",
                "Cantidad": v.cantidad,
                "Precio Contrato": float(v.precio_contrato),
                "Precio Efectivo": float(v.precio_efectivo),
                "Total": float(v.precio_efectivo * v.cantidad)
            })

        filename = "ventas_resumen.xlsx"

    elif tipo == "gastos_resumen":
        # Resumen de gastos por período
        query = Gasto.query
        if fecha_desde:
            fecha_desde = datetime.fromisoformat(fecha_desde).date()
            query = query.filter(Gasto.fecha >= fecha_desde)
        if fecha_hasta:
            fecha_hasta = datetime.fromisoformat(fecha_hasta).date()
            query = query.filter(Gasto.fecha <= fecha_hasta)

        gastos = query.order_by(Gasto.fecha.desc()).all()

        data = []
        for g in gastos:
            data.append({
                "Fecha": g.fecha,
                "Categoría": g.categoria.nombre if g.categoria else "",
                "Proveedor": g.proveedor.nombre if g.proveedor else "",
                "Monto": float(g.monto),
                "Descripción": g.descripcion or ""
            })

        filename = "gastos_resumen.xlsx"

    else:
        return jsonify({"error": f"Tipo de exportación inválido: {tipo}"}), 400

    df = pd.DataFrame(data)

    # Crear archivo Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='BI Report', index=False)

    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )