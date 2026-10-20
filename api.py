# api.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from sqlalchemy import func

import models as m
from models import db
from models.time_utils import today_local_date

api = Blueprint("api", __name__, url_prefix="/api")


def get_model(name):
    """Devuelve la clase de modelo si existe, si no None."""
    return getattr(m, name, None)


def _parse_periodo(periodo_raw: str | None) -> tuple[str, date, date]:
    """Parsea periodo soportado: '7', '15', '30', '6m', 'ytd'. Devuelve (key, desde, hasta)."""
    today = today_local_date()
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

    today = today_local_date()
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

        total_dias = (hasta - desde).days + 1
        granularidad = (
            "mes"
            if periodo_key == "ytd" or total_dias > 210
            else "semana"
            if periodo_key == "6m" or total_dias > 45
            else "dia"
        )

        if granularidad in ("mes", "semana"):
            # Agregación adaptable en Python (DB-agnóstica).
            agregados: dict[str, dict[str, float]] = {}
            d = desde
            while d <= hasta:
                key = (
                    d.strftime("%Y-%m")
                    if granularidad == "mes"
                    else (d - timedelta(days=d.weekday())).isoformat()
                )
                agregados.setdefault(key, {"ingresos": 0.0, "egresos": 0.0})
                d = d + timedelta(days=1)

            for day_key, val in ingresos_by_day.items():
                day_value = date.fromisoformat(str(day_key)[:10])
                key = (
                    day_value.strftime("%Y-%m")
                    if granularidad == "mes"
                    else (day_value - timedelta(days=day_value.weekday())).isoformat()
                )
                if key in agregados:
                    agregados[key]["ingresos"] += _to_float(val)
            for day_key, val in egresos_by_day.items():
                day_value = date.fromisoformat(str(day_key)[:10])
                key = (
                    day_value.strftime("%Y-%m")
                    if granularidad == "mes"
                    else (day_value - timedelta(days=day_value.weekday())).isoformat()
                )
                if key in agregados:
                    agregados[key]["egresos"] += _to_float(val)

            labels = sorted(agregados.keys())
            ingresos_series = [agregados[k]["ingresos"] for k in labels]
            egresos_series = [agregados[k]["egresos"] for k in labels]
            neto_series = [ingresos_series[i] - egresos_series[i] for i in range(len(labels))]
            series["flujo"] = {
                "labels": labels,
                "ingresos": ingresos_series,
                "egresos": egresos_series,
                "neto": neto_series,
                "granularidad": granularidad,
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
    vendedor_filter = (request.args.get("vendedor") or "").strip()
    cliente_filter = (request.args.get("cliente") or "").strip()
    producto_filter = (request.args.get("producto") or "").strip()
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
        "cliente_analisis": None,
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
        if vendedor_filter:
            _pre_filters.append(StgSabiogoVentas.vendedor == vendedor_filter)
        if cliente_filter:
            _pre_filters.append(StgSabiogoVentas.cliente == cliente_filter)
        if producto_filter:
            _pre_filters.append(StgSabiogoVentas.producto == producto_filter)

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

        def frecuencia_dias(fecha_min, fecha_max, fechas_distintas):
            fechas_distintas = int(fechas_distintas or 0)
            if fechas_distintas < 2 or not fecha_min or not fecha_max:
                return None
            return float((fecha_max - fecha_min).days / (fechas_distintas - 1))

        def agregar_pre_por_dimension(columna, nombre_sin_dato, incluir_productos=False):
            rows = (
                db.session.query(
                    columna.label("nombre"),
                    func.sum(StgSabiogoVentas.subtot).label("plata"),
                    func.sum(StgSabiogoVentas.cajas).label("cajas"),
                    func.sum(StgSabiogoVentas.kilos).label("kilos"),
                    func.count(func.distinct(StgSabiogoVentas.nro_comprob)).label("compras"),
                    func.count(func.distinct(StgSabiogoVentas.producto)).label("productos"),
                    func.max(StgSabiogoVentas.fecha).label("ultima_compra"),
                    func.min(StgSabiogoVentas.fecha).label("primera_compra"),
                    func.count(func.distinct(StgSabiogoVentas.fecha)).label("fechas_distintas"),
                )
                .filter(*_pre_filters)
                .group_by(columna)
                .order_by(func.sum(StgSabiogoVentas.subtot).desc())
                .limit(10)
                .all()
            )
            resultado = []
            for row in rows:
                plata = float(_to_float(row.plata))
                ultima = row.ultima_compra
                resultado.append(
                    {
                        "nombre": row.nombre or nombre_sin_dato,
                        "plata": plata,
                        "cajas": float(_to_float(row.cajas)),
                        "kilos": float(_to_float(row.kilos)),
                        "compras": int(row.compras or 0),
                        "pct": round(plata / pre_total * 100, 1) if pre_total else 0.0,
                        "productos": int(row.productos or 0) if incluir_productos else 0,
                        "ultima_compra": ultima.isoformat() if ultima else None,
                        "frecuencia_dias": (
                            frecuencia_dias(row.primera_compra, ultima, row.fechas_distintas)
                            if incluir_productos
                            else None
                        ),
                    }
                )
            return resultado

        payload["series"]["pre_por_vendedor"] = agregar_pre_por_dimension(
            StgSabiogoVentas.vendedor, "Sin vendedor"
        )
        if payload["series"]["pre_por_vendedor"]:
            payload["kpis"]["ventas_pre_top_vendedor"] = payload["series"]["pre_por_vendedor"][0]["nombre"]

        payload["series"]["pre_por_cliente"] = agregar_pre_por_dimension(
            StgSabiogoVentas.cliente, "Sin cliente", incluir_productos=True
        )
        payload["series"]["pre_por_producto"] = agregar_pre_por_dimension(
            StgSabiogoVentas.producto, "Sin producto"
        )

        if cliente_filter:
            analisis = (
                pre_base_q.with_entities(
                    func.count(func.distinct(StgSabiogoVentas.nro_comprob)).label("compras"),
                    func.count(func.distinct(StgSabiogoVentas.producto)).label("productos"),
                    func.max(StgSabiogoVentas.fecha).label("ultima_compra"),
                    func.min(StgSabiogoVentas.fecha).label("primera_compra"),
                    func.count(func.distinct(StgSabiogoVentas.fecha)).label("fechas_distintas"),
                    func.sum(StgSabiogoVentas.subtot).label("plata"),
                    func.sum(StgSabiogoVentas.cajas).label("cajas"),
                    func.sum(StgSabiogoVentas.kilos).label("kilos"),
                )
                .first()
            )
            payload["cliente_analisis"] = {
                "cliente": cliente_filter,
                "compras": int(analisis.compras or 0),
                "productos": int(analisis.productos or 0),
                "frecuencia_dias": frecuencia_dias(
                    analisis.primera_compra, analisis.ultima_compra, analisis.fechas_distintas
                ),
                "ultima_compra": analisis.ultima_compra.isoformat() if analisis.ultima_compra else None,
                "plata": float(_to_float(analisis.plata)),
                "cajas": float(_to_float(analisis.cajas)),
                "kilos": float(_to_float(analisis.kilos)),
            }

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
    fecha_desde_raw = request.args.get("fecha_desde")
    fecha_hasta_raw = request.args.get("fecha_hasta")
    fecha_desde = _parse_iso_date(fecha_desde_raw)
    fecha_hasta = _parse_iso_date(fecha_hasta_raw)
    if fecha_desde_raw and not fecha_desde:
        return jsonify({"error": "fecha_desde tiene un formato inválido"}), 400
    if fecha_hasta_raw and not fecha_hasta:
        return jsonify({"error": "fecha_hasta tiene un formato inválido"}), 400
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        return jsonify({"error": "fecha_desde no puede ser mayor a fecha_hasta"}), 400
    today = today_local_date()
    if fecha_desde and fecha_desde > today:
        return jsonify({"error": "fecha_desde no puede ser una fecha futura"}), 400
    if fecha_hasta and fecha_hasta > today:
        return jsonify({"error": "fecha_hasta no puede ser una fecha futura"}), 400

    periodo_key, desde, hasta = _parse_periodo_o_fechas(
        request.args.get("period") or "30",
        fecha_desde_raw,
        fecha_hasta_raw,
    )
    from services.resultado_comercial_service import ResultadoComercialService

    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    resumen = ResultadoComercialService().calcular(desde, hasta, empresa)
    k = resumen["kpis"]

    CuentaCorrienteFriar = get_model("CuentaCorrienteFriar")
    PagoFriar = get_model("PagoFriar")
    LiquidacionFriar = get_model("LiquidacionFriar")

    result = {
        "period": periodo_key,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "empresa": empresa,
        "kpis": {
            "facturacion": k["facturacion"],
            "compras": k["compras"],
            "diferencia_facturacion_compras": k["diferencia_facturacion_compras"],
            "ingresos_incluidos": k["ingresos_incluidos"],
            "egresos_incluidos": k["egresos_incluidos"],
            "resultado_gestion": k["resultado_gestion"],
            "resultado_sobre_facturacion_pct": k["resultado_sobre_facturacion_pct"],
            "caja_neta": k["caja_neta"],
            # Compatibilidad con consumidores anteriores.
            "sabiogo_ingresos": k["facturacion"],
            "sabiogo_costos": k["compras"],
            "sabiogo_margen": k["diferencia_facturacion_compras"],
            "sabiogo_margen_pct": (
                k["diferencia_facturacion_compras"] / k["facturacion"] * 100
                if k["facturacion"]
                else 0.0
            ),
            "cta_cte_friar_saldo_actual": 0.0,
            "cta_cte_friar_total": 0.0,
        },
        "top_clientes": resumen["clientes"]["top"],
        "concentracion_clientes": resumen["clientes"],
        "instrumentos": {"labels": [], "values": []},
        "conceptos": resumen["conceptos"],
        "analisis_financiero": resumen["analisis_financiero"],
        "sueldos_pagados": resumen["sueldos_pagados"],
        "series": resumen["series"],
        "meta": resumen["meta"],
        "alertas": resumen["meta"]["warnings"],
        "friar": {
            "cuenta": None,
            "ultimos_pagos": [],
        },
    }

    # Friar: cuenta corriente y últimos 5 pagos
    if CuentaCorrienteFriar and PagoFriar and LiquidacionFriar:
        cuenta = db.session.query(CuentaCorrienteFriar).first()
        if cuenta:
            total_pagos = (
                db.session.query(func.sum(PagoFriar.monto))
                .filter(PagoFriar.cuenta_corriente_id == cuenta.id)
                .scalar()
                or 0
            )
            total_liquidaciones = (
                db.session.query(func.sum(LiquidacionFriar.monto))
                .filter(LiquidacionFriar.cuenta_corriente_id == cuenta.id)
                .scalar()
                or 0
            )
            saldo_actual = (
                _to_float(getattr(cuenta, "saldo_inicial", 0))
                + _to_float(total_liquidaciones)
                - _to_float(total_pagos)
            )
            result["friar"]["cuenta"] = {
                "id": int(cuenta.id),
                "proveedor": _safe_str(getattr(getattr(cuenta, "proveedor", None), "nombre", None)),
                "saldo_inicial": float(_to_float(getattr(cuenta, "saldo_inicial", 0))),
                "total_liquidaciones": float(_to_float(total_liquidaciones)),
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

    return jsonify(result)


# -----------------------------------------------------------------------------
#  Análisis de cantidades – Panel Ventas
# -----------------------------------------------------------------------------
@api.get("/dashboard-comercial/filtros")
def api_dashboard_comercial_filtros():
    """Devuelve listas completas de vendedores, clientes y productos para poblar filtros."""
    from models.sabiogo.staging import StgSabiogoVentas

    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    f = [StgSabiogoVentas.estado == "procesado"]
    if empresa not in ("", "TODAS"):
        f.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa)

    vend = (
        db.session.query(StgSabiogoVentas.vendedor)
        .filter(*f)
        .filter(StgSabiogoVentas.vendedor.isnot(None), StgSabiogoVentas.vendedor != "")
        .distinct()
        .order_by(StgSabiogoVentas.vendedor)
        .all()
    )
    prod = (
        db.session.query(StgSabiogoVentas.producto)
        .filter(*f)
        .filter(StgSabiogoVentas.producto.isnot(None), StgSabiogoVentas.producto != "")
        .distinct()
        .order_by(StgSabiogoVentas.producto)
        .all()
    )
    clientes = (
        db.session.query(StgSabiogoVentas.cliente)
        .filter(*f)
        .filter(StgSabiogoVentas.cliente.isnot(None), StgSabiogoVentas.cliente != "")
        .distinct()
        .order_by(StgSabiogoVentas.cliente)
        .all()
    )
    return jsonify({
        "vendedores": [r.vendedor for r in vend],
        "clientes": [r.cliente for r in clientes],
        "productos": [r.producto for r in prod],
    })


@api.get("/dashboard-comercial/analisis")
def api_dashboard_comercial_analisis():
    """Top 15 + evolución 6M para producto / cliente / vendedor."""
    from models.sabiogo.staging import StgSabiogoVentas

    tipo_raw = (request.args.get("tipo") or "producto").lower().strip()
    tipo = tipo_raw if tipo_raw in ("producto", "cliente", "vendedor") else "producto"

    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    vendedor_filter = (request.args.get("vendedor") or "").strip()
    producto_filter = (request.args.get("producto") or "").strip()

    hoy = date.today()
    try:
        fecha_desde = datetime.fromisoformat(request.args.get("fecha_desde") or "").date()
        fecha_hasta = datetime.fromisoformat(request.args.get("fecha_hasta") or "").date()
    except (ValueError, TypeError):
        fecha_desde = hoy - timedelta(days=30)
        fecha_hasta = hoy

    # Últimos 6 meses para el gráfico de líneas (independiente del filtro de fechas)
    m = hoy.month - 1 or 12
    y = hoy.year if hoy.month > 1 else hoy.year - 1
    for _ in range(4):
        m = m - 1 or 12
        y = y if m > 0 else y - 1
    evo_desde = date(y if m != 12 or hoy.month > 6 else y, m, 1)
    # Más robusto: restar 6 meses desde el primero del mes actual
    primer_mes_actual = date(hoy.year, hoy.month, 1)
    evo_mes = primer_mes_actual.month - 6
    evo_anio = primer_mes_actual.year
    if evo_mes <= 0:
        evo_mes += 12
        evo_anio -= 1
    evo_desde = date(evo_anio, evo_mes, 1)
    evo_hasta = hoy

    col_expr = getattr(StgSabiogoVentas, tipo)

    def base_filters(fd, fh):
        f = [
            StgSabiogoVentas.estado == "procesado",
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
            StgSabiogoVentas.fecha.between(fd, fh),
        ]
        if empresa not in ("", "TODAS"):
            f.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa)
        if vendedor_filter and tipo != "vendedor":
            f.append(StgSabiogoVentas.vendedor == vendedor_filter)
        if producto_filter and tipo != "producto":
            f.append(StgSabiogoVentas.producto == producto_filter)
        return f

    # Top 15 por cajas en el período filtrado
    top15_rows = (
        db.session.query(
            col_expr.label("nombre"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
            func.sum(StgSabiogoVentas.subtot).label("monto"),
            func.count(func.distinct(StgSabiogoVentas.nro_comprob)).label("facturas"),
        )
        .filter(*base_filters(fecha_desde, fecha_hasta))
        .filter(col_expr.isnot(None))
        .group_by(col_expr)
        .order_by(func.sum(StgSabiogoVentas.cajas).desc())
        .limit(15)
        .all()
    )

    # Evolución mensual últimos 6M
    evo_rows = (
        db.session.query(
            func.date_trunc("month", StgSabiogoVentas.fecha).label("periodo"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
            func.sum(StgSabiogoVentas.subtot).label("monto"),
        )
        .filter(*base_filters(evo_desde, evo_hasta))
        .group_by(func.date_trunc("month", StgSabiogoVentas.fecha))
        .order_by(func.date_trunc("month", StgSabiogoVentas.fecha))
        .all()
    )

    titulos = {"producto": "Top 15 Productos", "cliente": "Top 15 Clientes", "vendedor": "Top 15 Vendedores"}

    return jsonify(
        {
            "tipo": tipo,
            "titulo": titulos.get(tipo, "Top 15"),
            "top15": [
                {
                    "nombre": r.nombre or "–",
                    "cajas": float(r.cajas or 0),
                    "monto": float(r.monto or 0),
                    "facturas": int(r.facturas or 0),
                }
                for r in top15_rows
            ],
            "evo_6m": [
                {
                    "periodo": r.periodo.strftime("%Y-%m") if r.periodo else None,
                    "cajas": float(r.cajas or 0),
                    "monto": float(r.monto or 0),
                }
                for r in evo_rows
            ],
        }
    )


@api.get("/dashboard-comercial/mix")
def api_dashboard_comercial_mix():
    """Mix de ventas: distribución, diversidad por cliente, participación cliente×producto,
    evolución mensual del mix (últimos 6 meses)."""
    from models.sabiogo.staging import StgSabiogoVentas

    empresa  = (request.args.get("empresa") or "TODAS").upper().strip()
    vendedor_f = (request.args.get("vendedor") or "").strip()
    cliente_f  = (request.args.get("cliente")  or "").strip()
    producto_f = (request.args.get("producto") or "").strip()

    hoy = date.today()
    try:
        fecha_desde = datetime.fromisoformat(request.args.get("fecha_desde") or "").date()
        fecha_hasta = datetime.fromisoformat(request.args.get("fecha_hasta") or "").date()
    except (ValueError, TypeError):
        fecha_desde = date(hoy.year, hoy.month, 1)
        fecha_hasta = hoy

    # Últimos 6 meses para evolución
    primer_mes = date(hoy.year, hoy.month, 1)
    evo_mes  = primer_mes.month - 6
    evo_anio = primer_mes.year
    if evo_mes <= 0:
        evo_mes += 12
        evo_anio -= 1
    evo_desde = date(evo_anio, evo_mes, 1)

    def base_f(fd, fh):
        f = [
            StgSabiogoVentas.estado == "procesado",
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
            StgSabiogoVentas.fecha.between(fd, fh),
        ]
        if empresa not in ("", "TODAS"):
            f.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa)
        if vendedor_f:
            f.append(StgSabiogoVentas.vendedor == vendedor_f)
        if cliente_f:
            f.append(StgSabiogoVentas.cliente == cliente_f)
        if producto_f:
            f.append(StgSabiogoVentas.producto == producto_f)
        return f

    # ── 1. Mix global: top 10 productos + "Otros" ──
    mg_rows = (
        db.session.query(
            StgSabiogoVentas.producto.label("producto"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
        )
        .filter(*base_f(fecha_desde, fecha_hasta))
        .filter(StgSabiogoVentas.producto.isnot(None))
        .group_by(StgSabiogoVentas.producto)
        .order_by(func.sum(StgSabiogoVentas.cajas).desc())
        .limit(11)
        .all()
    )
    total_cajas = sum(float(r.cajas or 0) for r in mg_rows)
    mix_global = []
    otros = 0.0
    for i, r in enumerate(mg_rows):
        c = float(r.cajas or 0)
        if i < 10:
            mix_global.append({
                "producto": r.producto or "–",
                "cajas": c,
                "pct": round(c / total_cajas * 100, 1) if total_cajas else 0,
            })
        else:
            otros += c
    if otros > 0:
        mix_global.append({"producto": "Otros", "cajas": otros,
                            "pct": round(otros / total_cajas * 100, 1) if total_cajas else 0})

    # ── 2. Diversidad de clientes: top 15 por N° productos distintos ──
    div_rows = (
        db.session.query(
            StgSabiogoVentas.cliente.label("cliente"),
            func.count(func.distinct(StgSabiogoVentas.producto)).label("n_productos"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
        )
        .filter(*base_f(fecha_desde, fecha_hasta))
        .filter(StgSabiogoVentas.cliente.isnot(None))
        .group_by(StgSabiogoVentas.cliente)
        .order_by(func.count(func.distinct(StgSabiogoVentas.producto)).desc())
        .limit(15)
        .all()
    )
    diversidad_clientes = [
        {"cliente": r.cliente or "–", "n_productos": int(r.n_productos or 0),
         "cajas": float(r.cajas or 0)}
        for r in div_rows
    ]

    # ── 3. Mix por cliente: top 8 clientes × top 5 productos (stacked bar) ──
    # determinar top 8 clientes por cajas
    top8_clientes_rows = (
        db.session.query(
            StgSabiogoVentas.cliente.label("cliente"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
        )
        .filter(*base_f(fecha_desde, fecha_hasta))
        .filter(StgSabiogoVentas.cliente.isnot(None))
        .group_by(StgSabiogoVentas.cliente)
        .order_by(func.sum(StgSabiogoVentas.cajas).desc())
        .limit(8)
        .all()
    )
    top8_clientes = [r.cliente for r in top8_clientes_rows]

    # determinar top 5 productos globales del período
    top5_prods_rows = (
        db.session.query(
            StgSabiogoVentas.producto.label("producto"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
        )
        .filter(*base_f(fecha_desde, fecha_hasta))
        .filter(StgSabiogoVentas.producto.isnot(None))
        .group_by(StgSabiogoVentas.producto)
        .order_by(func.sum(StgSabiogoVentas.cajas).desc())
        .limit(5)
        .all()
    )
    top5_prods = [r.producto for r in top5_prods_rows]

    # consulta cruzada cliente×producto
    if top8_clientes and top5_prods:
        cross_rows = (
            db.session.query(
                StgSabiogoVentas.cliente.label("cliente"),
                StgSabiogoVentas.producto.label("producto"),
                func.sum(StgSabiogoVentas.cajas).label("cajas"),
            )
            .filter(*base_f(fecha_desde, fecha_hasta))
            .filter(StgSabiogoVentas.cliente.in_(top8_clientes))
            .filter(StgSabiogoVentas.producto.in_(top5_prods))
            .group_by(StgSabiogoVentas.cliente, StgSabiogoVentas.producto)
            .all()
        )
        cross_map: dict[str, dict[str, float]] = {c: {} for c in top8_clientes}
        for r in cross_rows:
            if r.cliente in cross_map:
                cross_map[r.cliente][r.producto] = float(r.cajas or 0)
    else:
        cross_map = {}

    mix_por_cliente = [
        {"cliente": c, "productos": cross_map.get(c, {})}
        for c in top8_clientes
    ]

    # ── 4. Evolución del mix: top 3 productos × últimos 6 meses ──
    top3_prods_rows = (
        db.session.query(
            StgSabiogoVentas.producto.label("producto"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
        )
        .filter(*base_f(evo_desde, hoy))
        .filter(StgSabiogoVentas.producto.isnot(None))
        .group_by(StgSabiogoVentas.producto)
        .order_by(func.sum(StgSabiogoVentas.cajas).desc())
        .limit(3)
        .all()
    )
    top3_prods = [r.producto for r in top3_prods_rows]

    evo_rows = []
    if top3_prods:
        evo_raw = (
            db.session.query(
                func.date_trunc("month", StgSabiogoVentas.fecha).label("periodo"),
                StgSabiogoVentas.producto.label("producto"),
                func.sum(StgSabiogoVentas.cajas).label("cajas"),
            )
            .filter(*base_f(evo_desde, hoy))
            .filter(StgSabiogoVentas.producto.in_(top3_prods))
            .group_by(func.date_trunc("month", StgSabiogoVentas.fecha), StgSabiogoVentas.producto)
            .order_by(func.date_trunc("month", StgSabiogoVentas.fecha))
            .all()
        )
        # agrupar por mes
        evo_map: dict[str, dict[str, float]] = {}
        for r in evo_raw:
            mes = r.periodo.strftime("%Y-%m") if r.periodo else "?"
            if mes not in evo_map:
                evo_map[mes] = {}
            evo_map[mes][r.producto] = float(r.cajas or 0)
        evo_rows = [{"periodo": mes, "productos": prods} for mes, prods in sorted(evo_map.items())]

    # ── 5. Clientes disponibles para el select ──
    clientes_rows = (
        db.session.query(StgSabiogoVentas.cliente)
        .filter(*base_f(fecha_desde, fecha_hasta))
        .filter(StgSabiogoVentas.cliente.isnot(None), StgSabiogoVentas.cliente != "")
        .distinct()
        .order_by(StgSabiogoVentas.cliente)
        .all()
    )

    return jsonify({
        "mix_global":          mix_global,
        "diversidad_clientes": diversidad_clientes,
        "mix_por_cliente":     mix_por_cliente,
        "top_productos_stacked": top5_prods,
        "evo_mix":             evo_rows,
        "top_productos_evo":   top3_prods,
        "clientes_disponibles": [r.cliente for r in clientes_rows],
    })


@api.get("/dashboard-comercial/seguimiento")
def api_dashboard_comercial_seguimiento():
    """Seguimiento por vendedor de los clientes con pedidos PRE procesados."""
    from models.sabiogo.staging import StgSabiogoVentas

    hoy = datetime.now(ZoneInfo("America/Argentina/Tucuman")).date()
    desde = hoy - timedelta(days=29)
    vendedor_expr = func.trim(StgSabiogoVentas.vendedor)
    cliente_expr = func.trim(StgSabiogoVentas.cliente)
    comprobante_expr = func.trim(StgSabiogoVentas.nro_comprob)
    filtros_documento = [
        StgSabiogoVentas.estado == "procesado",
        func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
        vendedor_expr.isnot(None),
        vendedor_expr != "",
        cliente_expr.isnot(None),
        cliente_expr != "",
        comprobante_expr.isnot(None),
        comprobante_expr != "",
    ]

    # Una fila lógica por comprobante, aunque tenga varias líneas de productos.
    documentos = (
        db.session.query(
            vendedor_expr.label("vendedor"),
            cliente_expr.label("cliente"),
            comprobante_expr.label("nro_comprob"),
            func.min(StgSabiogoVentas.fecha).label("fecha"),
        )
        .filter(*filtros_documento)
        .group_by(vendedor_expr, cliente_expr, comprobante_expr)
        .subquery("pre_documentos_seguimiento")
    )

    clientes_rows = (
        db.session.query(
            documentos.c.vendedor,
            documentos.c.cliente,
            func.min(documentos.c.fecha).label("primera_compra"),
            func.max(documentos.c.fecha).label("ultima_compra"),
        )
        .group_by(documentos.c.vendedor, documentos.c.cliente)
        .all()
    )
    clientes_por_vendedor: dict[str, dict[str, dict]] = {}
    for row in clientes_rows:
        clientes_por_vendedor.setdefault(row.vendedor, {})[row.cliente] = {
            "primera_compra": row.primera_compra,
            "ultima_compra": row.ultima_compra,
        }

    activos_rows = (
        db.session.query(documentos.c.vendedor, documentos.c.cliente)
        .filter(documentos.c.fecha.between(desde, hoy))
        .distinct()
        .all()
    )
    activos_por_vendedor: dict[str, set[str]] = {}
    for vendedor, cliente in activos_rows:
        activos_por_vendedor.setdefault(vendedor, set()).add(cliente)

    producto_expr = func.coalesce(
        func.nullif(func.trim(StgSabiogoVentas.producto), ""), "Sin producto"
    )
    filtros_productos = [
        StgSabiogoVentas.estado == "procesado",
        func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
        vendedor_expr.isnot(None),
        vendedor_expr != "",
        StgSabiogoVentas.fecha.between(desde, hoy),
    ]
    productos_rows = (
        db.session.query(
            vendedor_expr.label("vendedor"),
            producto_expr.label("producto"),
            func.sum(StgSabiogoVentas.subtot).label("plata"),
        )
        .filter(*filtros_productos)
        .group_by(vendedor_expr, producto_expr)
        .all()
    )
    plata_por_producto: dict[str, dict[str, float]] = {}
    for row in productos_rows:
        plata_por_producto.setdefault(row.vendedor, {})[row.producto] = float(
            _to_float(row.plata)
        )

    vendedores = []
    for vendedor in sorted(clientes_por_vendedor, key=str.casefold):
        clientes = clientes_por_vendedor[vendedor]
        nombres = sorted(clientes, key=str.casefold)
        nuevos_nombres = [
            nombre
            for nombre in nombres
            if desde <= clientes[nombre]["primera_compra"] <= hoy
        ]

        importes = plata_por_producto.get(vendedor, {})
        total_plata = sum(importes.values())
        top_productos = sorted(
            importes.items(), key=lambda item: (-item[1], item[0].casefold())
        )
        productos = [
            {
                "nombre": nombre,
                "pct": round(plata / total_plata * 100, 1) if total_plata else 0.0,
                "plata": plata,
            }
            for nombre, plata in top_productos[:8]
        ]
        resto = top_productos[8:]
        if resto:
            plata_otros = sum(plata for _, plata in resto)
            productos.append(
                {
                    "nombre": "Otros",
                    "pct": round(plata_otros / total_plata * 100, 1) if total_plata else 0.0,
                    "plata": float(plata_otros),
                }
            )
            productos.sort(key=lambda item: (-item["plata"], item["nombre"].casefold()))

        ultimas = [
            {
                "nombre": nombre,
                "fecha": clientes[nombre]["ultima_compra"],
                "dias": (hoy - clientes[nombre]["ultima_compra"]).days,
            }
            for nombre in nombres
        ]
        ultimas.sort(key=lambda item: (-item["dias"], item["nombre"].casefold()))

        vendedores.append(
            {
                "nombre": vendedor,
                "total": len(nombres),
                "activos": len(activos_por_vendedor.get(vendedor, set())),
                "nuevos": [{"nombre": nombre} for nombre in nuevos_nombres],
                "lista": [{"nombre": nombre} for nombre in nombres],
                "productos": productos,
                "ultimas": [
                    {**item, "fecha": item["fecha"].isoformat()}
                    for item in ultimas[:12]
                ],
            }
        )

    return jsonify(
        {
            "desde": desde.isoformat(),
            "hasta": hoy.isoformat(),
            "vendedores": vendedores,
        }
    )
