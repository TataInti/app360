# api.py
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func

import models as m
from models import db

api = Blueprint("api", __name__, url_prefix="/api")


def get_model(name):
    """Devuelve la clase de modelo si existe, si no None."""
    return getattr(m, name, None)


def _parse_periodo(periodo_raw: str | None) -> tuple[str, date, date]:
    """Parsea periodo soportado: '7', '15', '30', '6m', 'ytd'. Devuelve (key, desde, hasta)."""
    today = date.today()
    if not periodo_raw:
        periodo_raw = "30"

    periodo_key = str(periodo_raw).strip().lower()
    if periodo_key in {"7", "7d"}:
        return ("7", today - timedelta(days=6), today)
    if periodo_key in {"15", "15d"}:
        return ("15", today - timedelta(days=14), today)
    if periodo_key in {"30", "30d"}:
        return ("30", today - timedelta(days=29), today)
    if periodo_key in {"6m", "180", "180d"}:
        return ("6m", today - timedelta(days=179), today)
    if periodo_key in {"ytd", "anio", "año"}:
        return ("ytd", date(today.year, 1, 1), today)

    # fallback seguro
    return ("30", today - timedelta(days=29), today)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _parse_periodo_o_fechas(periodo_raw: str | None, fecha_desde_raw: str | None, fecha_hasta_raw: str | None) -> tuple[str, date, date]:
    """Prioriza fecha_desde/fecha_hasta, luego periodo; default final últimos 30 días."""
    desde = _parse_iso_date(fecha_desde_raw)
    hasta = _parse_iso_date(fecha_hasta_raw)

    if desde and hasta:
        if desde > hasta:
            desde, hasta = hasta, desde
        return ("custom", desde, hasta)

    today = date.today()
    if desde and not hasta:
        return ("custom", desde, today)
    if hasta and not desde:
        return ("custom", hasta - timedelta(days=29), hasta)

    return _parse_periodo(periodo_raw)


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_str(value) -> str:
    return str(value) if value is not None else ""


# -----------------------------------------------------------------------------
#  /api/dashboard
#  Dashboard operativo (equivalente a dashboard.html)
# -----------------------------------------------------------------------------
@api.get("/dashboard")
def api_dashboard():
    Product = get_model("Product")
    Location = get_model("Location")
    Stock = get_model("Stock")

    # Totales
    if Product:
        total_products = db.session.query(func.count(Product.id)).scalar() or 0
    else:
        total_products = 0

    if Location:
        total_locations = db.session.query(func.count(Location.id)).scalar() or 0
    else:
        total_locations = 0

    if Stock:
        total_stock_records = db.session.query(func.count(Stock.id)).scalar() or 0
    else:
        total_stock_records = 0

    # Stock por unidad de negocio
    stock_per_unit = []
    if Product and Stock and hasattr(Product, "business_unit_id"):
        rows_unit = (
            db.session.query(Product.business_unit_id, func.sum(Stock.quantity))
            .join(Stock, Stock.product_id == Product.id)
            .group_by(Product.business_unit_id)
            .all()
        )

        for bu_id, qty in rows_unit:
            label = f"Unidad {bu_id}" if bu_id is not None else "Sin unidad"
            stock_per_unit.append([label, int(qty or 0)])

    # Stock por ubicación
    stock_per_location = []
    if Location and Stock:
        rows_loc = (
            db.session.query(Location.name, func.sum(Stock.quantity))
            .join(Stock, Stock.location_id == Location.id)
            .group_by(Location.name)
            .all()
        )

        stock_per_location = [[name, int(qty or 0)] for name, qty in rows_loc]

    return jsonify(
        {
            "total_products": int(total_products),
            "total_locations": int(total_locations),
            "total_stock_records": int(total_stock_records),
            "stock_per_unit": stock_per_unit,
            "stock_per_location": stock_per_location,
        }
    )


# -----------------------------------------------------------------------------
#  /api/dashboard-comercial
#  Dashboard Comercial (equivalente a dashboard_comercial.html)
# -----------------------------------------------------------------------------
@api.get("/dashboard-comercial")
def api_dashboard_comercial():
    Lead = get_model("Lead")

    if Lead:
        total_leads = db.session.query(func.count(Lead.id)).scalar() or 0

        # Leads por estado
        estados_rows = (
            db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
        )
        leads_por_estado = {status or "sin_estado": int(qty or 0) for status, qty in estados_rows}

        # Leads por unidad de negocio
        leads_por_unidad = []
        if hasattr(Lead, "business_unit_id"):
            unidad_rows = (
                db.session.query(Lead.business_unit_id, func.count(Lead.id))
                .group_by(Lead.business_unit_id)
                .all()
            )
            for bu_id, qty in unidad_rows:
                label = f"Unidad {bu_id}" if bu_id is not None else "Sin unidad"
                leads_por_unidad.append([label, int(qty or 0)])

        # Leads por origen
        origen_rows = db.session.query(Lead.source, func.count(Lead.id)).group_by(Lead.source).all()
        leads_por_origen = [[source or "Sin origen", int(qty or 0)] for source, qty in origen_rows]

    else:
        # Si ni siquiera existe Lead, devolvemos todo en cero
        total_leads = 0
        leads_por_estado = {}
        leads_por_unidad = []
        leads_por_origen = []

    # Conversión (ganado / total)
    ganados = leads_por_estado.get("ganado", 0)
    conversion = round((ganados / total_leads) * 100, 2) if total_leads else 0.0

    return jsonify(
        {
            "total_leads": int(total_leads),
            "leads_por_estado": leads_por_estado,
            "conversion": float(conversion),
            "leads_por_unidad": leads_por_unidad,
            "leads_por_origen": leads_por_origen,
        }
    )


# -----------------------------------------------------------------------------
#  /api/panel-ejecutivo
#  Panel Ejecutivo Global (equivalente a panel_ejecutivo.html)
# -----------------------------------------------------------------------------
@api.get("/panel-ejecutivo")
def api_panel_ejecutivo():
    Product = get_model("Product")
    Location = get_model("Location")
    Lead = get_model("Lead")
    Stock = get_model("Stock")

    # Totales
    if Lead:
        total_leads = db.session.query(func.count(Lead.id)).scalar() or 0
    else:
        total_leads = 0

    if Product:
        total_products = db.session.query(func.count(Product.id)).scalar() or 0
    else:
        total_products = 0

    if Location:
        total_locations = db.session.query(func.count(Location.id)).scalar() or 0
    else:
        total_locations = 0

    # Leads por estado
    leads_por_estado = {}
    if Lead:
        estados_rows = (
            db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
        )
        leads_por_estado = {status or "sin_estado": int(qty or 0) for status, qty in estados_rows}

    ganados = leads_por_estado.get("ganado", 0)
    conversion = round((ganados / total_leads) * 100, 2) if total_leads else 0.0

    # Stock por unidad de negocio
    stock_por_unidad = []
    if Product and Stock and hasattr(Product, "business_unit_id"):
        stock_unidad_rows = (
            db.session.query(Product.business_unit_id, func.sum(Stock.quantity))
            .join(Stock, Stock.product_id == Product.id)
            .group_by(Product.business_unit_id)
            .all()
        )
        for bu_id, qty in stock_unidad_rows:
            label = f"Unidad {bu_id}" if bu_id is not None else "Sin unidad"
            stock_por_unidad.append([label, int(qty or 0)])

    # Productos con stock bajo (ej: menos de 10 unidades)
    stock_bajo = []
    if Product and Stock:
        stock_bajo_rows = (
            db.session.query(Product.name, func.sum(Stock.quantity))
            .join(Stock, Stock.product_id == Product.id)
            .group_by(Product.id)
            .having(func.sum(Stock.quantity) < 10)
            .all()
        )
        stock_bajo = [[name, int(qty or 0)] for name, qty in stock_bajo_rows]

    return jsonify(
        {
            "total_leads": int(total_leads),
            "total_products": int(total_products),
            "total_locations": int(total_locations),
            "conversion": float(conversion),
            "leads_por_estado": leads_por_estado,
            "stock_por_unidad": stock_por_unidad,
            "stock_bajo": stock_bajo,
        }
    )


# -----------------------------------------------------------------------------
#  /api/dashboard-financiero
#  Dashboard Financiero (Tesorería + RRHH) con período 7/15/30/YTD
# -----------------------------------------------------------------------------
@api.get("/dashboard-financiero")
def api_dashboard_financiero():
    periodo_key, desde, hasta = _parse_periodo_o_fechas(
        request.args.get("period"),
        request.args.get("fecha_desde"),
        request.args.get("fecha_hasta"),
    )

    MovimientoCaja = get_model("MovimientoCaja")
    InstrumentoPago = get_model("InstrumentoPago")
    Adelanto = get_model("Adelanto")
    Employee = get_model("Employee")
    StgSabiogoVentas = get_model("StgSabiogoVentas")

    # Defaults (si faltan modelos, devolvemos todo en 0/[])
    kpis: dict = {
        "period": periodo_key,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "ingresos_total": 0.0,
        "egresos_total": 0.0,
        "neto": 0.0,
        "movimientos_total": 0,
        "movimientos_ingresos": 0,
        "movimientos_egresos": 0,
        "ticket_promedio": 0.0,
        "egresos_sobre_ingresos_pct": 0.0,
        "dias_neto_negativo": 0,
        "max_ingreso": None,
        "max_egreso": None,
        "rrhh_empleados_con_adelantos_prestamos": 0,
        "rrhh_monto_adelantos_prestamos": 0.0,
        "rrhh_monto_pendiente_prestamos": 0.0,
        "rrhh_breakdown_tipo": {},
        "pre_acumulado": 0.0,
        "fac_acumulado": 0.0,
        "pre_fac_saldo": 0.0,
    }

    series: dict = {
        "flujo": {"labels": [], "ingresos": [], "egresos": [], "neto": [], "granularidad": "dia"},
        "instrumentos": {"labels": [], "values": []},
    }

    if MovimientoCaja and InstrumentoPago:
        dt_desde = datetime.combine(desde, datetime.min.time())
        dt_hasta = datetime.combine(hasta, datetime.max.time())

        # Agregados principales (excluir anulados)
        base_filters = [
            MovimientoCaja.fecha_hora >= dt_desde,
            MovimientoCaja.fecha_hora <= dt_hasta,
            MovimientoCaja.estado != "anulado",
        ]

        ingresos_total = (
            db.session.query(func.sum(MovimientoCaja.monto))
            .filter(MovimientoCaja.tipo == "ingreso")
            .filter(*base_filters)
            .scalar()
            or 0
        )
        egresos_total = (
            db.session.query(func.sum(MovimientoCaja.monto))
            .filter(MovimientoCaja.tipo == "egreso")
            .filter(*base_filters)
            .scalar()
            or 0
        )

        movimientos_total = (
            db.session.query(func.count(MovimientoCaja.id))
            .filter(*base_filters)
            .scalar()
            or 0
        )
        movimientos_ingresos = (
            db.session.query(func.count(MovimientoCaja.id))
            .filter(MovimientoCaja.tipo == "ingreso")
            .filter(*base_filters)
            .scalar()
            or 0
        )
        movimientos_egresos = (
            db.session.query(func.count(MovimientoCaja.id))
            .filter(MovimientoCaja.tipo == "egreso")
            .filter(*base_filters)
            .scalar()
            or 0
        )

        ingresos_total_f = _to_float(ingresos_total)
        egresos_total_f = _to_float(egresos_total)
        neto = ingresos_total_f - egresos_total_f

        ticket_promedio = 0.0
        if movimientos_total:
            ticket_promedio = (ingresos_total_f + egresos_total_f) / float(movimientos_total)

        egresos_sobre_ingresos_pct = 0.0
        if ingresos_total_f > 0:
            egresos_sobre_ingresos_pct = (egresos_total_f / ingresos_total_f) * 100.0

        # Máximos (opcionales)
        max_ingreso_row = (
            db.session.query(MovimientoCaja)
            .filter(MovimientoCaja.tipo == "ingreso")
            .filter(*base_filters)
            .order_by(MovimientoCaja.monto.desc())
            .first()
        )
        max_egreso_row = (
            db.session.query(MovimientoCaja)
            .filter(MovimientoCaja.tipo == "egreso")
            .filter(*base_filters)
            .order_by(MovimientoCaja.monto.desc())
            .first()
        )

        def mov_to_dict(mov):
            if not mov:
                return None
            return {
                "id": int(mov.id),
                "fecha_hora": mov.fecha_hora.isoformat() if getattr(mov, "fecha_hora", None) else None,
                "monto": _to_float(getattr(mov, "monto", 0)),
                "descripcion": _safe_str(getattr(mov, "descripcion", "")),
                "instrumento": _safe_str(getattr(getattr(mov, "instrumento", None), "nombre", ""))
                or _safe_str(getattr(mov, "instrumento", "")),
            }

        # Series flujo (diaria; para YTD agregamos por mes)
        rows_by_day = (
            db.session.query(
                func.date(MovimientoCaja.fecha_hora).label("dia"),
                MovimientoCaja.tipo.label("tipo"),
                func.sum(MovimientoCaja.monto).label("total"),
            )
            .filter(*base_filters)
            .group_by(func.date(MovimientoCaja.fecha_hora), MovimientoCaja.tipo)
            .all()
        )

        ingresos_by_day: dict[str, float] = {}
        egresos_by_day: dict[str, float] = {}
        for dia, tipo, total in rows_by_day:
            key = str(dia)
            if tipo == "ingreso":
                ingresos_by_day[key] = ingresos_by_day.get(key, 0.0) + _to_float(total)
            elif tipo == "egreso":
                egresos_by_day[key] = egresos_by_day.get(key, 0.0) + _to_float(total)

        # Contar días con neto negativo (usando la base diaria)
        dias_neto_negativo = 0
        for key in set(list(ingresos_by_day.keys()) + list(egresos_by_day.keys())):
            if (ingresos_by_day.get(key, 0.0) - egresos_by_day.get(key, 0.0)) < 0:
                dias_neto_negativo += 1

        if periodo_key == "ytd":
            # Agregación mensual en Python (DB-agnóstica)
            mensual: dict[str, dict[str, float]] = {}
            d = desde
            while d <= hasta:
                mensual[d.strftime("%Y-%m")] = {"ingresos": 0.0, "egresos": 0.0}
                d = d + timedelta(days=1)

            for day_key, val in ingresos_by_day.items():
                month_key = str(day_key)[:7]
                if month_key in mensual:
                    mensual[month_key]["ingresos"] += _to_float(val)
            for day_key, val in egresos_by_day.items():
                month_key = str(day_key)[:7]
                if month_key in mensual:
                    mensual[month_key]["egresos"] += _to_float(val)

            labels = sorted(mensual.keys())
            ingresos_series = [mensual[k]["ingresos"] for k in labels]
            egresos_series = [mensual[k]["egresos"] for k in labels]
            neto_series = [ingresos_series[i] - egresos_series[i] for i in range(len(labels))]
            series["flujo"] = {
                "labels": labels,
                "ingresos": ingresos_series,
                "egresos": egresos_series,
                "neto": neto_series,
                "granularidad": "mes",
            }
        else:
            labels = []
            ingresos_series = []
            egresos_series = []
            neto_series = []
            d = desde
            while d <= hasta:
                key = d.isoformat()
                labels.append(key)
                ing = ingresos_by_day.get(key, 0.0)
                egr = egresos_by_day.get(key, 0.0)
                ingresos_series.append(ing)
                egresos_series.append(egr)
                neto_series.append(ing - egr)
                d = d + timedelta(days=1)

            series["flujo"] = {
                "labels": labels,
                "ingresos": ingresos_series,
                "egresos": egresos_series,
                "neto": neto_series,
                "granularidad": "dia",
            }

        # Distribución por instrumento (monto absoluto)
        instrumentos_rows = (
            db.session.query(InstrumentoPago.nombre, func.sum(MovimientoCaja.monto))
            .join(InstrumentoPago, InstrumentoPago.id == MovimientoCaja.instrumento_id)
            .filter(*base_filters)
            .group_by(InstrumentoPago.nombre)
            .order_by(func.sum(MovimientoCaja.monto).desc())
            .all()
        )
        inst_labels = [name or "Sin instrumento" for name, _ in instrumentos_rows]
        inst_values = [abs(_to_float(total)) for _, total in instrumentos_rows]
        series["instrumentos"] = {"labels": inst_labels, "values": inst_values}

        kpis.update(
            {
                "ingresos_total": ingresos_total_f,
                "egresos_total": egresos_total_f,
                "neto": neto,
                "movimientos_total": int(movimientos_total),
                "movimientos_ingresos": int(movimientos_ingresos),
                "movimientos_egresos": int(movimientos_egresos),
                "ticket_promedio": float(ticket_promedio),
                "egresos_sobre_ingresos_pct": float(egresos_sobre_ingresos_pct),
                "dias_neto_negativo": int(dias_neto_negativo),
                "max_ingreso": mov_to_dict(max_ingreso_row),
                "max_egreso": mov_to_dict(max_egreso_row),
            }
        )

    # RRHH: adelantos/préstamos
    if Adelanto and Employee:
        # Período: por fecha_solicitud (si existe) o fallback a conteo global
        dt_desde = datetime.combine(desde, datetime.min.time())
        dt_hasta = datetime.combine(hasta, datetime.max.time())

        q = db.session.query(Adelanto)
        if hasattr(Adelanto, "fecha_solicitud"):
            q = q.filter(Adelanto.fecha_solicitud >= dt_desde).filter(Adelanto.fecha_solicitud <= dt_hasta)

        adelantos = q.all()
        empleados_ids = set()
        monto_total = 0.0
        breakdown: dict[str, float] = {}
        for a in adelantos:
            empleados_ids.add(getattr(a, "empleado_id", None))
            monto = _to_float(getattr(a, "monto", 0))
            monto_total += monto
            tipo = _safe_str(getattr(a, "tipo", "desconocido")) or "desconocido"
            breakdown[tipo] = breakdown.get(tipo, 0.0) + monto

        # Pendiente préstamos (aprox. usando método del modelo en Python)
        monto_pendiente = 0.0
        try:
            prestamos_no_liquidados = (
                db.session.query(Adelanto)
                .filter(Adelanto.tipo == "prestamo")
                .filter(getattr(Adelanto, "aprobado", True) == True)
                .filter(getattr(Adelanto, "liquidado", False) == False)
                .all()
            )
            for p in prestamos_no_liquidados:
                if hasattr(p, "saldo_pendiente"):
                    monto_pendiente += _to_float(p.saldo_pendiente())
                else:
                    monto_pendiente += _to_float(getattr(p, "monto", 0))
        except Exception:
            monto_pendiente = 0.0

        kpis.update(
            {
                "rrhh_empleados_con_adelantos_prestamos": int(len([x for x in empleados_ids if x is not None])),
                "rrhh_monto_adelantos_prestamos": float(monto_total),
                "rrhh_monto_pendiente_prestamos": float(monto_pendiente),
                "rrhh_breakdown_tipo": {k: float(v) for k, v in breakdown.items()},
            }
        )

    # Control comercial-financiero: PRE vs FAC acumulado al corte del período.
    if StgSabiogoVentas:
        total_pre = (
            db.session.query(func.sum(StgSabiogoVentas.subtot))
            .filter(StgSabiogoVentas.estado == "procesado")
            .filter(func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE")
            .filter(StgSabiogoVentas.fecha <= hasta)
            .scalar()
            or 0
        )
        total_fac = (
            db.session.query(func.sum(StgSabiogoVentas.subtot))
            .filter(StgSabiogoVentas.estado == "procesado")
            .filter(func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") != "PRE")
            .filter(StgSabiogoVentas.fecha <= hasta)
            .scalar()
            or 0
        )

        total_pre_f = _to_float(total_pre)
        total_fac_f = _to_float(total_fac)
        kpis.update(
            {
                "pre_acumulado": float(total_pre_f),
                "fac_acumulado": float(total_fac_f),
                "pre_fac_saldo": float(total_pre_f - total_fac_f),
            }
        )

    return jsonify({"kpis": kpis, "series": series})


# -----------------------------------------------------------------------------
#  /api/dashboard-comercial-v2
#  Dashboard Comercial v2 (Marketing + Comercial)
# -----------------------------------------------------------------------------
@api.get("/dashboard-comercial-v2")
def api_dashboard_comercial_v2():
    periodo_key, desde, hasta = _parse_periodo_o_fechas(
        request.args.get("period"),
        request.args.get("fecha_desde"),
        request.args.get("fecha_hasta"),
    )
    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    dt_desde = datetime.combine(desde, datetime.min.time())
    dt_hasta = datetime.combine(hasta, datetime.max.time())

    Lead = get_model("Lead")
    Campaign = get_model("Campaign")
    Venta = get_model("Venta")
    Promocion = get_model("Promocion")
    Comision = get_model("Comision")
    Goal = get_model("Goal")
    StgSabiogoVentas = get_model("StgSabiogoVentas")

    payload = {
        "period": periodo_key,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "empresa": empresa,
        "kpis": {
            "leads_total": 0,
            "leads_periodo": 0,
            "leads_ganados_total": 0,
            "conversion_total_pct": 0.0,
            "campanias_total": 0,
            "campanias_activas": 0,
            "ventas_periodo_total": 0.0,
            "ventas_periodo_count": 0,
            "ventas_ticket_promedio": 0.0,
            "promociones_activas": 0,
            "comisiones_mes_total": 0.0,
            "objetivos_en_progreso": 0,
            "ventas_pre_periodo_total": 0.0,
            "ventas_pre_periodo_count": 0,
            "ventas_pre_ticket_promedio": 0.0,
            "ventas_pre_top_vendedor": "",
        },
        "series": {
            "leads_por_estado": {},
            "leads_por_origen": [],
            "leads_por_canal": [],
            "top_campanias_por_leads": [],
            "pre_detalle": [],
            "pre_por_vendedor": [],
            "pre_por_cliente": [],
            "pre_por_producto": [],
            "pre_evolucion_diaria": [],
        },
    }

    # MARKETING: campañas + leads
    if Campaign:
        payload["kpis"]["campanias_total"] = int(db.session.query(func.count(Campaign.id)).scalar() or 0)
        if hasattr(Campaign, "active"):
            payload["kpis"]["campanias_activas"] = int(
                db.session.query(func.count(Campaign.id)).filter(Campaign.active == True).scalar() or 0
            )

    if Lead:
        leads_total = int(db.session.query(func.count(Lead.id)).scalar() or 0)
        payload["kpis"]["leads_total"] = leads_total

        leads_periodo_q = db.session.query(func.count(Lead.id))
        if hasattr(Lead, "created_at"):
            leads_periodo_q = leads_periodo_q.filter(Lead.created_at >= dt_desde).filter(Lead.created_at <= dt_hasta)
        leads_periodo = int(leads_periodo_q.scalar() or 0)
        payload["kpis"]["leads_periodo"] = leads_periodo

        estados_rows = db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
        leads_por_estado = {status or "sin_estado": int(qty or 0) for status, qty in estados_rows}
        payload["series"]["leads_por_estado"] = leads_por_estado

        ganados = int(leads_por_estado.get("ganado", 0))
        payload["kpis"]["leads_ganados_total"] = ganados
        payload["kpis"]["conversion_total_pct"] = float(round((ganados / leads_total) * 100, 2)) if leads_total else 0.0

        origen_rows = db.session.query(Lead.source, func.count(Lead.id)).group_by(Lead.source).all()
        payload["series"]["leads_por_origen"] = [[source or "Sin origen", int(qty or 0)] for source, qty in origen_rows]

        # Leads por canal (vía Campaign.channel)
        if Campaign and hasattr(Lead, "campaign_id"):
            canal_rows = (
                db.session.query(Campaign.channel, func.count(Lead.id))
                .select_from(Lead)
                .outerjoin(Campaign, Campaign.id == Lead.campaign_id)
                .group_by(Campaign.channel)
                .all()
            )
            payload["series"]["leads_por_canal"] = [[channel or "Sin canal", int(qty or 0)] for channel, qty in canal_rows]

            top_campaign_rows = (
                db.session.query(Campaign.name, func.count(Lead.id))
                .join(Lead, Lead.campaign_id == Campaign.id)
                .group_by(Campaign.name)
                .order_by(func.count(Lead.id).desc())
                .limit(5)
                .all()
            )
            payload["series"]["top_campanias_por_leads"] = [[name or "(sin nombre)", int(qty or 0)] for name, qty in top_campaign_rows]

    # COMERCIAL: ventas internas, promos, comisiones, objetivos
    if Venta:
        ventas_q = db.session.query(Venta)
        if hasattr(Venta, "fecha"):
            ventas_q = ventas_q.filter(Venta.fecha >= desde).filter(Venta.fecha <= hasta)
        ventas = ventas_q.all()
        payload["kpis"]["ventas_periodo_count"] = int(len(ventas))

        total_ventas = 0.0
        for v in ventas:
            try:
                total_ventas += _to_float(getattr(v, "precio_contrato", 0)) * float(getattr(v, "cantidad", 0) or 0)
            except Exception:
                continue
        payload["kpis"]["ventas_periodo_total"] = float(total_ventas)
        if len(ventas):
            payload["kpis"]["ventas_ticket_promedio"] = float(total_ventas / float(len(ventas)))

    if Promocion:
        # Promos activas en fecha actual (si el modelo tiene los campos)
        today = date.today()
        q = db.session.query(func.count(Promocion.id))
        if hasattr(Promocion, "activo"):
            q = q.filter(Promocion.activo == True)
        if hasattr(Promocion, "fecha_inicio"):
            q = q.filter(Promocion.fecha_inicio <= today)
        if hasattr(Promocion, "fecha_fin"):
            q = q.filter(Promocion.fecha_fin >= today)
        payload["kpis"]["promociones_activas"] = int(q.scalar() or 0)

    if Comision:
        # Comisiones del mes actual (YYYY-MM)
        periodo_mes = date.today().strftime("%Y-%m")
        q = db.session.query(func.sum(Comision.comision_total))
        if hasattr(Comision, "periodo"):
            q = q.filter(Comision.periodo == periodo_mes)
        payload["kpis"]["comisiones_mes_total"] = float(_to_float(q.scalar() or 0))

    if Goal:
        q = db.session.query(func.count(Goal.id))
        if hasattr(Goal, "status"):
            q = q.filter(Goal.status == "en progreso")
        payload["kpis"]["objetivos_en_progreso"] = int(q.scalar() or 0)

    # Detalle operativo basado en PRE (ventas SabioGo en el período).
    if StgSabiogoVentas:
        _pre_filters = [
            StgSabiogoVentas.estado == "procesado",
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
            StgSabiogoVentas.fecha >= desde,
            StgSabiogoVentas.fecha <= hasta,
        ]
        if empresa in ("CARNES", "LACTEOS"):
            _pre_filters.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa)

        pre_base_q = db.session.query(StgSabiogoVentas).filter(*_pre_filters)

        pre_count = int(pre_base_q.count() or 0)
        pre_total = float(_to_float(pre_base_q.with_entities(func.sum(StgSabiogoVentas.subtot)).scalar() or 0))
        payload["kpis"]["ventas_pre_periodo_count"] = pre_count
        payload["kpis"]["ventas_pre_periodo_total"] = pre_total
        payload["kpis"]["ventas_pre_ticket_promedio"] = float(pre_total / pre_count) if pre_count else 0.0

        pre_detalle_rows = pre_base_q.order_by(
            StgSabiogoVentas.fecha.desc(),
            StgSabiogoVentas.id.desc(),
        ).limit(20).all()
        payload["series"]["pre_detalle"] = [
            {
                "id": int(row.id),
                "fecha": row.fecha.isoformat() if getattr(row, "fecha", None) else None,
                "comprobante": _safe_str(getattr(row, "comprobante", "")),
                "nro_comprob": _safe_str(getattr(row, "nro_comprob", "")),
                "vendedor": _safe_str(getattr(row, "vendedor", "")) or "Sin vendedor",
                "cliente": _safe_str(getattr(row, "cliente", "")) or "Sin cliente",
                "producto": _safe_str(getattr(row, "producto", "")) or "Sin producto",
                "codigo": _safe_str(getattr(row, "codigo", "")),
                "subtot": float(_to_float(getattr(row, "subtot", 0))),
                "kilos": float(_to_float(getattr(row, "kilos", 0))),
                "cajas": float(_to_float(getattr(row, "cajas", 0))),
            }
            for row in pre_detalle_rows
        ]

        pre_vendedor_rows = (
            db.session.query(
                StgSabiogoVentas.vendedor,
                func.count(StgSabiogoVentas.id),
                func.sum(StgSabiogoVentas.subtot),
            )
            .filter(*_pre_filters)
            .group_by(StgSabiogoVentas.vendedor)
            .order_by(func.sum(StgSabiogoVentas.subtot).desc())
            .limit(10)
            .all()
        )
        payload["series"]["pre_por_vendedor"] = [
            [
                vendedor or "Sin vendedor",
                int(cantidad or 0),
                float(_to_float(monto or 0)),
            ]
            for vendedor, cantidad, monto in pre_vendedor_rows
        ]
        if pre_vendedor_rows:
            payload["kpis"]["ventas_pre_top_vendedor"] = pre_vendedor_rows[0][0] or "Sin vendedor"

        pre_cliente_rows = (
            db.session.query(
                StgSabiogoVentas.cliente,
                func.count(StgSabiogoVentas.id),
                func.sum(StgSabiogoVentas.subtot),
            )
            .filter(*_pre_filters)
            .group_by(StgSabiogoVentas.cliente)
            .order_by(func.sum(StgSabiogoVentas.subtot).desc())
            .limit(10)
            .all()
        )
        payload["series"]["pre_por_cliente"] = [
            [
                cliente or "Sin cliente",
                int(cantidad or 0),
                float(_to_float(monto or 0)),
            ]
            for cliente, cantidad, monto in pre_cliente_rows
        ]

        pre_producto_rows = (
            db.session.query(
                StgSabiogoVentas.producto,
                func.count(StgSabiogoVentas.id),
                func.sum(StgSabiogoVentas.subtot),
            )
            .filter(*_pre_filters)
            .group_by(StgSabiogoVentas.producto)
            .order_by(func.sum(StgSabiogoVentas.subtot).desc())
            .limit(10)
            .all()
        )
        payload["series"]["pre_por_producto"] = [
            [
                producto or "Sin producto",
                int(cantidad or 0),
                float(_to_float(monto or 0)),
            ]
            for producto, cantidad, monto in pre_producto_rows
        ]

        # Evolución diaria PRE
        pre_diaria_rows = (
            db.session.query(
                StgSabiogoVentas.fecha,
                func.count(StgSabiogoVentas.id),
                func.sum(StgSabiogoVentas.subtot),
            )
            .filter(*_pre_filters)
            .group_by(StgSabiogoVentas.fecha)
            .order_by(StgSabiogoVentas.fecha)
            .all()
        )
        payload["series"]["pre_evolucion_diaria"] = [
            {
                "fecha": row[0].isoformat() if row[0] else None,
                "cantidad": int(row[1] or 0),
                "monto": float(_to_float(row[2] or 0)),
            }
            for row in pre_diaria_rows
        ]

    return jsonify(payload)


# -----------------------------------------------------------------------------
#  /api/panel-ejecutivo-v2
#  Panel Ejecutivo v2 (rentabilidad + tesorería)
# -----------------------------------------------------------------------------
@api.get("/panel-ejecutivo-v2")
def api_panel_ejecutivo_v2():
    # Por defecto: últimos 30 días
    periodo_key, desde, hasta = _parse_periodo_o_fechas(
        request.args.get("period") or "30",
        request.args.get("fecha_desde"),
        request.args.get("fecha_hasta"),
    )
    dt_desde = datetime.combine(desde, datetime.min.time())
    dt_hasta = datetime.combine(hasta, datetime.max.time())

    MovimientoCaja = get_model("MovimientoCaja")
    InstrumentoPago = get_model("InstrumentoPago")
    CuentaCorrienteFriar = get_model("CuentaCorrienteFriar")
    PagoFriar = get_model("PagoFriar")
    StgSabiogoVentas = get_model("StgSabiogoVentas")

    result = {
        "period": periodo_key,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "kpis": {
            "sabiogo_ingresos": 0.0,
            "sabiogo_costos": 0.0,
            "sabiogo_margen": 0.0,
            "sabiogo_margen_pct": 0.0,
            "cta_cte_friar_saldo_actual": 0.0,
            "cta_cte_friar_total": 0.0,
        },
        "top_clientes": [],
        "instrumentos": {"labels": [], "values": []},
        "friar": {
            "cuenta": None,
            "ultimos_pagos": [],
        },
    }

    # SabioGo: top 5 clientes por monto (YTD)
    if StgSabiogoVentas and hasattr(StgSabiogoVentas, "fecha"):
        monto_col = getattr(StgSabiogoVentas, "subtot", None) or getattr(StgSabiogoVentas, "neto", None)
        if monto_col is not None:
            rows = (
                db.session.query(StgSabiogoVentas.cliente, func.sum(monto_col))
                .filter(StgSabiogoVentas.fecha >= desde)
                .filter(StgSabiogoVentas.fecha <= hasta)
                .filter(getattr(StgSabiogoVentas, "estado", "procesado") == "procesado")
                .group_by(StgSabiogoVentas.cliente)
                .order_by(func.sum(monto_col).desc())
                .limit(5)
                .all()
            )
            result["top_clientes"] = [
                {"cliente": (cliente or "(sin cliente)"), "monto": float(_to_float(total))}
                for cliente, total in rows
            ]

    # Tesorería: distribución de instrumentos (YTD)
    if MovimientoCaja and InstrumentoPago:
        instrumentos_rows = (
            db.session.query(InstrumentoPago.nombre, func.sum(MovimientoCaja.monto))
            .join(InstrumentoPago, InstrumentoPago.id == MovimientoCaja.instrumento_id)
            .filter(MovimientoCaja.fecha_hora >= dt_desde)
            .filter(MovimientoCaja.fecha_hora <= dt_hasta)
            .group_by(InstrumentoPago.nombre)
            .order_by(func.sum(MovimientoCaja.monto).desc())
            .all()
        )
        result["instrumentos"]["labels"] = [name or "Sin instrumento" for name, _ in instrumentos_rows]
        result["instrumentos"]["values"] = [abs(float(_to_float(total))) for _, total in instrumentos_rows]

    # Friar: cuenta corriente y últimos 5 pagos
    if CuentaCorrienteFriar and PagoFriar:
        cuenta = db.session.query(CuentaCorrienteFriar).first()
        if cuenta:
            total_pagos = (
                db.session.query(func.sum(PagoFriar.monto))
                .filter(PagoFriar.cuenta_corriente_id == cuenta.id)
                .scalar()
                or 0
            )
            saldo_actual = _to_float(getattr(cuenta, "saldo_inicial", 0)) - _to_float(total_pagos)
            result["friar"]["cuenta"] = {
                "id": int(cuenta.id),
                "proveedor": _safe_str(getattr(getattr(cuenta, "proveedor", None), "nombre", None)),
                "saldo_inicial": float(_to_float(getattr(cuenta, "saldo_inicial", 0))),
                "total_pagos": float(_to_float(total_pagos)),
                "saldo_actual": float(saldo_actual),
            }
            result["kpis"]["cta_cte_friar_saldo_actual"] = float(saldo_actual)
            result["kpis"]["cta_cte_friar_total"] = float(_to_float(getattr(cuenta, "saldo_inicial", 0)))

            ultimos = (
                db.session.query(PagoFriar)
                .filter(PagoFriar.cuenta_corriente_id == cuenta.id)
                .order_by(PagoFriar.fecha.desc())
                .limit(5)
                .all()
            )
            result["friar"]["ultimos_pagos"] = [
                {
                    "fecha": p.fecha.isoformat() if getattr(p, "fecha", None) else None,
                    "monto": float(_to_float(getattr(p, "monto", 0))),
                    "instrumento": _safe_str(getattr(getattr(p, "instrumento", None), "nombre", None)),
                    "descripcion": _safe_str(getattr(p, "descripcion", None)),
                }
                for p in ultimos
            ]

    # Opcional: rentabilidad SabioGo (mismos KPIs que BI)
    try:
        from services.sabiogo_service import SabiogoService

        sabiogo_service = SabiogoService()
        resumen = sabiogo_service.get_rentabilidad_resumen(desde, hasta) or {}
        ingresos = _to_float(resumen.get("total_ingresos", 0))
        costos = _to_float(resumen.get("total_costos", 0))
        margen = _to_float(resumen.get("margen_bruto", 0))
        margen_pct = _to_float(resumen.get("margen_porcentual", 0))
        result["kpis"].update(
            {
                "sabiogo_ingresos": float(ingresos),
                "sabiogo_costos": float(costos),
                "sabiogo_margen": float(margen),
                "sabiogo_margen_pct": float(margen_pct),
            }
        )
    except Exception:
        # Si no hay tablas SabioGo o el service falla, dejamos en 0
        pass

    return jsonify(result)
