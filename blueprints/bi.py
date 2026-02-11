from datetime import datetime, date, timedelta
from decimal import Decimal
import io

from flask import Blueprint, request, jsonify, send_file, render_template
from sqlalchemy import func, desc, extract

from models import (
    Adelanto,
    Asistencia,
    BusinessUnit,
    CategoriaGasto,
    Client,
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


def _parse_range(range_param: str | None, default_days: int = 180):
    """Devuelve fechas desde/hasta y el periodo anterior para deltas."""
    today = date.today()
    if range_param == "12m":
        days = 365
    elif range_param == "24m":
        days = 730
    else:
        days = default_days

    fecha_hasta = today
    fecha_desde = today - timedelta(days=days)

    prev_hasta = fecha_desde
    prev_desde = fecha_desde - timedelta(days=days)

    return fecha_desde, fecha_hasta, prev_desde, prev_hasta


def _month_key(dt: date):
    return dt.strftime("%Y-%m")


def _month_label(dt: date):
    return dt.strftime("%b")


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
    kpis["ventas_total"] = float(ventas_total)

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
    kpis["gastos_total"] = float(gastos_total)

    # 5. Margen (ventas - gastos)
    margen_bruto = float(ventas_total - gastos_total)
    kpis["margen_bruto"] = margen_bruto
    kpis["margen_neto"] = (margen_bruto / float(ventas_total)) if ventas_total else 0

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

    leads_generados = Lead.query.filter(
        func.date(Lead.created_at).between(fecha_desde, fecha_hasta)
    ).count()
    kpis["leads_generados"] = leads_generados

    ventas_diarias_raw = (
        db.session.query(
            Venta.fecha,
            func.sum(Venta.precio_efectivo * Venta.cantidad)
        )
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by(Venta.fecha)
        .order_by(Venta.fecha)
        .all()
    )
    ventas_diarias = {
        row[0].isoformat(): float(row[1] or 0)
        for row in ventas_diarias_raw
    }

    ventas_por_categoria_raw = (
        db.session.query(
            Product.category,
            func.sum(Venta.precio_efectivo * Venta.cantidad)
        )
        .join(Product, Venta.producto_id == Product.id)
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by(Product.category)
        .order_by(desc(func.sum(Venta.precio_efectivo * Venta.cantidad)))
        .all()
    )
    ventas_por_categoria = {}
    for categoria, total in ventas_por_categoria_raw:
        label = categoria or "Sin categoria"
        ventas_por_categoria[label] = float(total or 0)

    gastos_diarias_raw = (
        db.session.query(Gasto.fecha, func.sum(Gasto.monto))
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .group_by(Gasto.fecha)
        .order_by(Gasto.fecha)
        .all()
    )
    gastos_diarias = {
        row[0].isoformat(): float(row[1] or 0)
        for row in gastos_diarias_raw
    }

    leads_periodo_total = Lead.query.filter(
        func.date(Lead.created_at).between(fecha_desde, fecha_hasta)
    ).count()
    leads_stage_raw = (
        db.session.query(Lead.stage, func.count(Lead.id))
        .filter(func.date(Lead.created_at).between(fecha_desde, fecha_hasta))
        .group_by(Lead.stage)
        .order_by(desc(func.count(Lead.id)))
        .all()
    )
    conversion_leads = {}
    for stage, total in leads_stage_raw:
        label = stage or "sin etapa"
        conversion_leads[label] = round((total / leads_periodo_total * 100), 2) if leads_periodo_total else 0

    ventas_top = (
        Venta.query
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .order_by((Venta.precio_efectivo * Venta.cantidad).desc())
        .limit(10)
        .all()
    )
    ventas_top_data = [
        {
            "cliente": venta.cliente.name if venta.cliente else "N/A",
            "monto": float(venta.precio_efectivo * venta.cantidad),
            "fecha": venta.fecha.isoformat()
        }
        for venta in ventas_top
    ]

    gastos_top = (
        Gasto.query
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .order_by(Gasto.monto.desc())
        .limit(10)
        .all()
    )
    gastos_top_data = [
        {
            "descripcion": gasto.descripcion,
            "monto": float(gasto.monto),
            "categoria": gasto.categoria.nombre if gasto.categoria else "",
            "fecha": gasto.fecha.isoformat() if gasto.fecha else None
        }
        for gasto in gastos_top
    ]

    leads_activos = (
        Lead.query
        .filter(Lead.status.notin_(["ganado", "perdido"]))
        .order_by(Lead.created_at.desc())
        .limit(10)
        .all()
    )
    leads_activos_data = [
        {
            "empresa": lead.name,
            "contacto": lead.owner_name or lead.phone or lead.email or "",
            "estado": lead.status,
            "valor_potencial": 0
        }
        for lead in leads_activos
    ]

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
        "kpis": kpis,
        "ventas_diarias": ventas_diarias,
        "ventas_por_categoria": ventas_por_categoria,
        "gastos_diarios": gastos_diarias,
        "conversion_leads": conversion_leads,
        "ventas_top": ventas_top_data,
        "gastos_top": gastos_top_data,
        "leads_activos": leads_activos_data
    })


# Nuevos endpoints para Inteligencia Financiera
@bi_bp.route("/api/bi/overview", methods=["GET"])
def bi_overview():
    rango = request.args.get("range", "6m")
    fecha_desde, fecha_hasta, prev_desde, prev_hasta = _parse_range(rango)

    # Ventas y gastos del periodo y previo
    ventas_total = (
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    gastos_total = (
        db.session.query(func.sum(Gasto.monto))
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    ventas_prev = (
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(prev_desde, prev_hasta))
        .scalar()
        or 0
    )
    gastos_prev = (
        db.session.query(func.sum(Gasto.monto))
        .filter(Gasto.fecha.between(prev_desde, prev_hasta))
        .scalar()
        or 0
    )

    margen_bruto = ventas_total - gastos_total
    net_margin = (margen_bruto / ventas_total) if ventas_total else 0
    gross_margin = (margen_bruto / ventas_total) if ventas_total else 0

    # Burn y runway (aprox: gastos operativos promediados por mes)
    months = max(1, (fecha_hasta - fecha_desde).days / 30)
    burn_rate = gastos_total / months
    runway_months = (ventas_total - gastos_total) / burn_rate if burn_rate else 0

    # Deltas
    def _delta(curr, prev):
        if prev == 0:
            return 0
        return (curr - prev) / prev

    kpis = {
        "cash_flow": float(ventas_total - gastos_total),
        "ebitda": float(margen_bruto),
        "gross_margin": float(gross_margin),
        "net_margin": float(net_margin),
        "burn_rate": float(burn_rate),
        "runway_months": float(runway_months),
        "deltas": {
          "cash_flow": _delta(ventas_total - gastos_total, ventas_prev - gastos_prev),
          "ebitda": _delta(margen_bruto, ventas_prev - gastos_prev),
          "gross_margin": _delta(gross_margin, (ventas_prev - gastos_prev) / ventas_prev if ventas_prev else 0),
          "net_margin": _delta(net_margin, (ventas_prev - gastos_prev) / ventas_prev if ventas_prev else 0),
          "burn_rate": _delta(burn_rate, gastos_prev / months if months else 0),
          "runway_months": _delta(runway_months, runway_months),
        }
    }

    # Mix ingresos por categoría de producto
    mix_raw = (
        db.session.query(
            Product.category,
            func.sum(Venta.precio_efectivo * Venta.cantidad)
        )
        .join(Product, Venta.producto_id == Product.id)
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by(Product.category)
        .all()
    )
    mix_labels = []
    mix_valores = []
    for cat, total in mix_raw:
        mix_labels.append(cat or "Sin categoría")
        mix_valores.append(float(total or 0))

    # Serie mensual ingresos / costos / EBITDA
    ventas_mes = (
        db.session.query(
            extract('year', Venta.fecha).label('y'),
            extract('month', Venta.fecha).label('m'),
            func.sum(Venta.precio_efectivo * Venta.cantidad)
        )
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )
    gastos_mes = (
        db.session.query(
            extract('year', Gasto.fecha).label('y'),
            extract('month', Gasto.fecha).label('m'),
            func.sum(Gasto.monto)
        )
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )

    ventas_map = {f"{int(y)}-{int(m):02d}": float(total or 0) for y, m, total in ventas_mes}
    gastos_map = {f"{int(y)}-{int(m):02d}": float(total or 0) for y, m, total in gastos_mes}

    labels = []
    ingresos_list, costos_list, ebitda_list = [], [], []
    current = date(fecha_desde.year, fecha_desde.month, 1)
    end = date(fecha_hasta.year, fecha_hasta.month, 1)
    while current <= end:
        key = _month_key(current)
        labels.append(_month_label(current))
        ingresos = ventas_map.get(key, 0)
        costos = gastos_map.get(key, 0)
        ingresos_list.append(ingresos)
        costos_list.append(costos)
        ebitda_list.append(ingresos - costos)
        # avanzar al próximo mes
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    # Cash flow neto y burn (reutiliza la misma serie)
    cash_flow_series = ebitda_list
    burn_series = [costos for costos in costos_list]

    return jsonify({
        "periodo": {"desde": fecha_desde.isoformat(), "hasta": fecha_hasta.isoformat()},
        "kpis": kpis,
        "mix_ingresos": {"labels": mix_labels, "valores": mix_valores},
        "ingresos_costos": {"labels": labels, "ingresos": ingresos_list, "costos": costos_list, "ebitda": ebitda_list},
        "top_series": {"labels": labels, "cash_flow": cash_flow_series, "burn": burn_series},
    })


@bi_bp.route("/api/bi/rentabilidad", methods=["GET"])
def bi_rentabilidad():
    rango = request.args.get("range", "6m")
    fecha_desde, fecha_hasta, prev_desde, prev_hasta = _parse_range(rango)

    # Margen global
    ventas_total = (
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    gastos_total = (
        db.session.query(func.sum(Gasto.monto))
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    margen_bruto = ventas_total - gastos_total
    gross_margin = (margen_bruto / ventas_total) if ventas_total else 0
    net_margin = gross_margin  # no tenemos impuestos/costos financieros separados
    ebitda_margin = gross_margin  # aproximación

    kpis = {
        "gross_margin": float(gross_margin),
        "net_margin": float(net_margin),
        "ebitda_margin": float(ebitda_margin),
        "ltv_cac": 0,
        "deltas": {
            "gross_margin": 0,
            "net_margin": 0,
            "ebitda_margin": 0,
            "ltv_cac": 0,
        },
    }

    # Margen por unidad de negocio (si existe business_unit_id en Product)
    margen_unidades_raw = (
        db.session.query(
            BusinessUnit.name,
            func.sum(Venta.precio_efectivo * Venta.cantidad).label("ventas")
        )
        .join(Product, Venta.producto_id == Product.id)
        .join(BusinessUnit, Product.business_unit_id == BusinessUnit.id)
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by(BusinessUnit.name)
        .all()
    )
    labels, bruto_list, neto_list = [], [], []
    for name, ventas in margen_unidades_raw:
        ventas_val = float(ventas or 0)
        labels.append(name or "N/A")
        # Sin costos por unidad, usamos margen sobre ventas solo como placeholder
        bruto = 100.0 if ventas_val else 0
        neto = bruto
        bruto_list.append(bruto)
        neto_list.append(neto)

    # Mix de costos por categoría de gasto
    costos_mix_raw = (
        db.session.query(
            func.coalesce(CategoriaGasto.nombre, "Otros"),
            func.sum(Gasto.monto)
        )
        .join(CategoriaGasto, CategoriaGasto.id == Gasto.categoria_id)
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .group_by(func.coalesce(CategoriaGasto.nombre, "Otros"))
        .all()
    )
    mix_labels = []
    mix_valores = []
    for cat, total in costos_mix_raw:
        mix_labels.append(cat or "Otros")
        mix_valores.append(float(total or 0))

    # Serie de margen mensual
    ventas_mes = (
        db.session.query(
            extract('year', Venta.fecha).label('y'),
            extract('month', Venta.fecha).label('m'),
            func.sum(Venta.precio_efectivo * Venta.cantidad)
        )
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )
    gastos_mes = (
        db.session.query(
            extract('year', Gasto.fecha).label('y'),
            extract('month', Gasto.fecha).label('m'),
            func.sum(Gasto.monto)
        )
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )
    ventas_map = {f"{int(y)}-{int(m):02d}": float(total or 0) for y, m, total in ventas_mes}
    gastos_map = {f"{int(y)}-{int(m):02d}": float(total or 0) for y, m, total in gastos_mes}

    labels_serie, bruto_serie, neto_serie = [], [], []
    current = date(fecha_desde.year, fecha_desde.month, 1)
    end = date(fecha_hasta.year, fecha_hasta.month, 1)
    while current <= end:
        key = _month_key(current)
        labels_serie.append(_month_label(current))
        ventas_val = ventas_map.get(key, 0)
        gastos_val = gastos_map.get(key, 0)
        bruto_pct = (ventas_val - gastos_val) / ventas_val if ventas_val else 0
        neto_pct = bruto_pct
        bruto_serie.append(bruto_pct)
        neto_serie.append(neto_pct)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    # Top clientes por margen (suma por cliente)
    top_clientes_raw = (
        db.session.query(
            Client.name,
            func.sum(Venta.precio_efectivo * Venta.cantidad).label("venta")
        )
        .join(Client, Client.id == Venta.cliente_id)
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by(Client.name)
        .order_by(desc("venta"))
        .limit(3)
        .all()
    )
    top_clientes = [
        {
            "cliente": c,
            "margen": 0.0 if v == 0 else 0.25,
            "ingreso": float(v or 0)
        }
        for c, v in top_clientes_raw
    ]

    alertas = []
    for idx, name in enumerate(labels):
        if neto_list[idx] < 20:  # alerta si margen neto < 20%
            alertas.append({"unidad": name, "margen": neto_list[idx] / 100, "objetivo": 0.25})

    return jsonify({
        "periodo": {"desde": fecha_desde.isoformat(), "hasta": fecha_hasta.isoformat()},
        "kpis": kpis,
        "margen_unidades": {"labels": labels, "bruto": bruto_list, "neto": neto_list},
        "mix_costos": {"labels": mix_labels, "valores": mix_valores},
        "margen_serie": {"labels": labels_serie, "bruto": bruto_serie, "neto": neto_serie},
        "top_clientes": top_clientes,
        "alertas": alertas,
    })


@bi_bp.route("/api/bi/eficiencia", methods=["GET"])
def bi_eficiencia():
    rango = request.args.get("range", "6m")
    fecha_desde, fecha_hasta, prev_desde, prev_hasta = _parse_range(rango)

    # Cash in/out
    cash_in = (
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    cash_out = (
        db.session.query(func.sum(Gasto.monto))
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    cash_balance = cash_in - cash_out

    months = max(1, (fecha_hasta - fecha_desde).days / 30)
    burn_rate = cash_out / months
    runway_months = cash_balance / burn_rate if burn_rate else 0

    kpis = {
        "cash_balance": float(cash_balance),
        "cash_in": float(cash_in),
        "cash_out": float(cash_out),
        "dso": 0,
        "dpo": 0,
        "inventory_days": 0,
        "burn_rate": float(burn_rate),
        "runway_months": float(runway_months),
        "arpu": 0,
        "payback_months": 0,
        "deltas": {
            "cash_balance": 0,
            "cash_in": 0,
            "cash_out": 0,
            "dso": 0,
            "dpo": 0,
            "inventory_days": 0,
            "burn_rate": 0,
            "runway_months": 0,
            "arpu": 0,
            "payback_months": 0,
        },
    }

    # Serie cash flow mensual
    ventas_mes = (
        db.session.query(
            extract('year', Venta.fecha).label('y'),
            extract('month', Venta.fecha).label('m'),
            func.sum(Venta.precio_efectivo * Venta.cantidad)
        )
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )
    gastos_mes = (
        db.session.query(
            extract('year', Gasto.fecha).label('y'),
            extract('month', Gasto.fecha).label('m'),
            func.sum(Gasto.monto)
        )
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )
    ventas_map = {f"{int(y)}-{int(m):02d}": float(total or 0) for y, m, total in ventas_mes}
    gastos_map = {f"{int(y)}-{int(m):02d}": float(total or 0) for y, m, total in gastos_mes}

    labels, cash_in_series, cash_out_series, balance_series = [], [], [], []
    current = date(fecha_desde.year, fecha_desde.month, 1)
    end = date(fecha_hasta.year, fecha_hasta.month, 1)
    balance_acum = 0
    while current <= end:
        key = _month_key(current)
        labels.append(_month_label(current))
        ci = ventas_map.get(key, 0)
        co = gastos_map.get(key, 0)
        balance_acum += ci - co
        cash_in_series.append(ci)
        cash_out_series.append(co)
        balance_series.append(balance_acum)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    # Eficiencia operativa (placeholder en ausencia de AR/AP)
    eficiencia_labels = labels
    eficiencia = {
        "labels": eficiencia_labels,
        "dso": [0 for _ in eficiencia_labels],
        "dpo": [0 for _ in eficiencia_labels],
        "inventory": [0 for _ in eficiencia_labels],
    }

    # Mix de gastos por categoría
    gastos_mix_raw = (
        db.session.query(
            func.coalesce(CategoriaGasto.nombre, "Otros"),
            func.sum(Gasto.monto)
        )
        .join(CategoriaGasto, CategoriaGasto.id == Gasto.categoria_id)
        .filter(Gasto.fecha.between(fecha_desde, fecha_hasta))
        .group_by(func.coalesce(CategoriaGasto.nombre, "Otros"))
        .all()
    )
    gm_labels, gm_valores = [], []
    for cat, total in gastos_mix_raw:
        gm_labels.append(cat or "Otros")
        gm_valores.append(float(total or 0))

    # Cobranzas próximas (placeholder: leads recientes)
    cobranzas = [
        {
            "cliente": lead.name,
            "monto": 0,
            "vencimiento": lead.created_at.date().isoformat() if lead.created_at else None,
        }
        for lead in Lead.query.order_by(Lead.created_at.desc()).limit(3).all()
    ]

    return jsonify({
        "periodo": {"desde": fecha_desde.isoformat(), "hasta": fecha_hasta.isoformat()},
        "kpis": kpis,
        "cash_flow": {"labels": labels, "cash_in": cash_in_series, "cash_out": cash_out_series, "balance": balance_series},
        "eficiencia": eficiencia,
        "gastos_mix": {"labels": gm_labels, "valores": gm_valores},
        "cobranzas": cobranzas,
    })


@bi_bp.route("/api/bi/liquidez", methods=["GET"])
def bi_liquidez():
    """Liquidez: caja, FCF 30/90d, burn y aging placeholders."""
    rango = request.args.get("range", "6m")
    fecha_desde, fecha_hasta, _, _ = _parse_range(rango)

    # Caja disponible = ventas acumuladas - gastos acumulados
    cash_on_hand = (
        (db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad)).filter(Venta.fecha <= fecha_hasta).scalar() or 0)
        - (db.session.query(func.sum(Gasto.monto)).filter(Gasto.fecha <= fecha_hasta).scalar() or 0)
    )

    def _fcf_days(days: int):
        start = fecha_hasta - timedelta(days=days)
        ventas = db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad)).filter(Venta.fecha.between(start, fecha_hasta)).scalar() or 0
        gastos = db.session.query(func.sum(Gasto.monto)).filter(Gasto.fecha.between(start, fecha_hasta)).scalar() or 0
        return float(ventas - gastos)

    fcf_30d = _fcf_days(30)
    fcf_90d = _fcf_days(90)

    # Burn y runway aproximados
    months = max(1, (fecha_hasta - fecha_desde).days / 30)
    gastos_periodo = db.session.query(func.sum(Gasto.monto)).filter(Gasto.fecha.between(fecha_desde, fecha_hasta)).scalar() or 0
    burn = gastos_periodo / months
    runway_months = (cash_on_hand / burn) if burn else 0

    kpis = {
        "cash_on_hand": float(cash_on_hand),
        "fcf_30d": float(fcf_30d),
        "fcf_90d": float(fcf_90d),
        "burn": float(burn),
        "runway_months": float(runway_months),
        "ccc": 0,
        "nwc_ratio": 0,
        "deltas": {
            "cash_on_hand": 0,
            "fcf_30d": 0,
            "fcf_90d": 0,
            "burn": 0,
            "runway_months": 0,
            "ccc": 0,
            "nwc_ratio": 0,
        },
    }

    # Serie semanal cash in/out
    labels, cash_in_series, cash_out_series, balance_series = [], [], [], []
    balance_acum = 0
    current = fecha_desde
    week_idx = 1
    while current <= fecha_hasta:
        week_end = min(current + timedelta(days=6), fecha_hasta)
        ci = db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad)).filter(Venta.fecha.between(current, week_end)).scalar() or 0
        co = db.session.query(func.sum(Gasto.monto)).filter(Gasto.fecha.between(current, week_end)).scalar() or 0
        balance_acum += ci - co
        labels.append(f"S{week_idx}")
        cash_in_series.append(float(ci))
        cash_out_series.append(float(co))
        balance_series.append(float(balance_acum))
        week_idx += 1
        current = week_end + timedelta(days=1)

    cash_weekly = {
        "labels": labels,
        "cash_in": cash_in_series,
        "cash_out": cash_out_series,
        "balance": balance_series,
    }

    # Sin AR/AP modelados: devolvemos buckets vacíos
    aging_ar = {"labels": ["0-30", "31-60", "61-90", "90+"], "values": [0, 0, 0, 0]}
    aging_ap = {"labels": ["0-30", "31-60", "61-90", "90+"], "values": [0, 0, 0, 0]}

    return jsonify({
        "periodo": {"desde": fecha_desde.isoformat(), "hasta": fecha_hasta.isoformat()},
        "kpis": kpis,
        "cash_weekly": cash_weekly,
        "aging_ar": aging_ar,
        "aging_ap": aging_ap,
    })


@bi_bp.route("/api/bi/proyecciones", methods=["GET"])
def bi_proyecciones():
    """Proyecciones a 24M con escenarios base/optimista/estresado (mock calculado)."""
    scenario = request.args.get("scenario", "base")

    base_labels = [f"T{i}" for i in range(1, 9)]  # 8 trimestres = 24M

    def _serie(base_val: float, growth: float):
        vals = []
        current = base_val
        for _ in base_labels:
            vals.append(round(current, 2))
            current *= (1 + growth)
        return vals

    growth_map = {
        "base": 0.04,
        "optimista": 0.06,
        "estres": 0.02,
    }
    g = growth_map.get(scenario, 0.04)

    escenarios = {
        key: {
            "labels": base_labels,
            "ingresos": _serie(480, growth_map[key]),
            "ebitda": [round(v * 0.26, 2) for v in _serie(480, growth_map[key])],
            "fcf": [round(v * 0.18, 2) for v in _serie(480, growth_map[key])],
        }
        for key in growth_map
    }

    capex_vs_inversion = {
        "labels": base_labels,
        "capex": _serie(30, 0.0),
        "otros": _serie(12, 0.0),
    }

    estructura_capital = {"labels": ["Equity", "Deuda"], "values": [65, 35]}

    kpis = {
        "fcf_proj": escenarios.get(scenario, escenarios["base"]).get("fcf", [])[-1] if escenarios else 0,
        "debt_ebitda": 2.4,
        "interest_coverage": 4.8,
        "deltas": {
            "fcf_proj": 0,
            "debt_ebitda": 0,
            "interest_coverage": 0,
        },
    }

    supuestos = [
        "Crecimiento trimestral estable según escenario",
        "Capex plano en 24M",
        "Costo de deuda constante",
    ]

    return jsonify({
        "kpis": kpis,
        "escenarios": escenarios,
        "capex_vs_inversion": capex_vs_inversion,
        "estructura_capital": estructura_capital,
        "supuestos": supuestos,
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