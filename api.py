# api.py
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import String, case, cast, func

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


def _formatear_mes(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    return str(value)[:7]


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
            "ventas_pre_ticket_promedio": None,
            "ventas_pre_clientes_compradores": 0,
            "ventas_pre_cajas": 0.0,
            "ventas_pre_kilos": 0.0,
            "ventas_pre_lineas_sin_numero": 0,
            "fecha_maxima_pre": None,
            "ultima_importacion_pre": None,
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
        from services.comercial_pre import calcular_resumen_pre
        from services.vendedores_comerciales import resolver_nombre_vendedor

        if vendedor_filter:
            from services.comercial_pre import expresion_vendedor_resuelta

            _pre_filters.append(
                expresion_vendedor_resuelta()
                == resolver_nombre_vendedor(vendedor_filter)
            )
        if cliente_filter:
            _pre_filters.append(StgSabiogoVentas.cliente == cliente_filter)
        if producto_filter:
            _pre_filters.append(StgSabiogoVentas.producto == producto_filter)

        pre_resumen = calcular_resumen_pre(
            desde,
            hasta,
            empresa=empresa if empresa in ("CARNES", "LACTEOS") else None,
            vendedor=vendedor_filter or None,
            cliente=cliente_filter or None,
            producto=producto_filter or None,
        )
        pre_base_q = db.session.query(StgSabiogoVentas).filter(*_pre_filters)

        pre_count = int(pre_resumen["pedidos_identificados"])
        pre_total = float(pre_resumen["importe_pre"])
        payload["kpis"]["ventas_pre_periodo_count"] = pre_count
        payload["kpis"]["ventas_pre_periodo_total"] = pre_total
        payload["kpis"]["ventas_pre_ticket_promedio"] = pre_resumen["ticket_promedio"]
        payload["kpis"]["ventas_pre_clientes_compradores"] = pre_resumen[
            "clientes_compradores"
        ]
        payload["kpis"]["ventas_pre_cajas"] = pre_resumen["cajas"]
        payload["kpis"]["ventas_pre_kilos"] = pre_resumen["kilos"]
        payload["kpis"]["ventas_pre_lineas_sin_numero"] = pre_resumen[
            "lineas_sin_numero"
        ]
        payload["kpis"]["fecha_maxima_pre"] = pre_resumen["fecha_maxima_pre"]
        payload["kpis"]["ultima_importacion_pre"] = pre_resumen[
            "ultima_importacion"
        ]

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

        payload["series"]["pre_por_vendedor"] = pre_resumen["por_vendedor"]
        if payload["series"]["pre_por_vendedor"]:
            payload["kpis"]["ventas_pre_top_vendedor"] = payload["series"][
                "pre_por_vendedor"
            ][0]["nombre"]

        payload["series"]["pre_por_cliente"] = pre_resumen["por_cliente"]
        payload["series"]["pre_por_producto"] = pre_resumen["por_producto"]

        if cliente_filter:
            analisis = pre_resumen["cliente_seleccionado"] or {
                "compras": 0,
                "productos": 0,
                "frecuencia_dias": None,
                "ultima_compra": None,
                "plata": 0.0,
                "cajas": 0.0,
                "kilos": 0.0,
            }
            payload["cliente_analisis"] = {
                "cliente": cliente_filter,
                "compras": analisis["compras"],
                "productos": analisis["productos"],
                "frecuencia_dias": analisis["frecuencia_dias"],
                "ultima_compra": analisis["ultima_compra"],
                "plata": analisis["plata"],
                "cajas": analisis["cajas"],
                "kilos": analisis["kilos"],
            }

        payload["series"]["pre_evolucion_diaria"] = pre_resumen["por_fecha"]

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
    from models.comercial import ComercialVendedor
    from services.comercial_criterios import filtro_comprobante_panel_ventas
    from services.vendedores_comerciales import resolver_nombre_vendedor

    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    f = [
        StgSabiogoVentas.estado == "procesado",
        filtro_comprobante_panel_ventas(),
    ]
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
    vendedores_nombres = {
        resolver_nombre_vendedor(row.vendedor) for row in vend if row.vendedor
    }
    vendedores_nombres.update(
        row.nombre_visible
        for row in db.session.query(ComercialVendedor.nombre_visible)
        .filter_by(activo=True)
        .all()
    )
    return jsonify({
        "vendedores": sorted(vendedores_nombres, key=str.casefold),
        "clientes": [r.cliente for r in clientes],
        "productos": [r.producto for r in prod],
    })


@api.get("/dashboard-comercial/analisis")
def api_dashboard_comercial_analisis():
    """Top 15 + evolución 6M para producto / cliente / vendedor."""
    from models.sabiogo.staging import StgSabiogoVentas
    from services.comercial_criterios import filtro_comprobante_panel_ventas
    from services.comercial_pre import expresion_vendedor_resuelta
    from services.vendedores_comerciales import resolver_nombre_vendedor

    tipo_raw = (request.args.get("tipo") or "producto").lower().strip()
    tipo = tipo_raw if tipo_raw in ("producto", "cliente", "vendedor") else "producto"
    medida_raw = (request.args.get("medida") or "cajas").lower().strip()
    medida = medida_raw if medida_raw in ("importe", "cajas", "kilos") else "cajas"

    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    vendedor_filter = (request.args.get("vendedor") or "").strip()
    cliente_filter = (request.args.get("cliente") or "").strip()
    producto_filter = (request.args.get("producto") or "").strip()

    hoy = date.today()
    try:
        fecha_desde = datetime.fromisoformat(request.args.get("fecha_desde") or "").date()
        fecha_hasta = datetime.fromisoformat(request.args.get("fecha_hasta") or "").date()
    except (ValueError, TypeError):
        fecha_desde = hoy - timedelta(days=30)
        fecha_hasta = hoy

    # Seis meses calendario hasta la fecha de corte seleccionada.
    corte_mes = fecha_hasta.year * 12 + fecha_hasta.month - 1
    evo_anio, evo_mes = divmod(corte_mes - 5, 12)
    evo_desde = date(evo_anio, evo_mes + 1, 1)
    evo_hasta = fecha_hasta

    vendedor_expr = expresion_vendedor_resuelta()
    col_expr = vendedor_expr if tipo == "vendedor" else getattr(StgSabiogoVentas, tipo)

    def base_filters(fd, fh):
        f = [
            StgSabiogoVentas.estado == "procesado",
            StgSabiogoVentas.fecha.between(fd, fh),
            filtro_comprobante_panel_ventas(),
        ]
        if empresa not in ("", "TODAS"):
            f.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa)
        if vendedor_filter and tipo != "vendedor":
            f.append(
                vendedor_expr == resolver_nombre_vendedor(vendedor_filter)
            )
        if cliente_filter and tipo != "cliente":
            f.append(StgSabiogoVentas.cliente == cliente_filter)
        if producto_filter and tipo != "producto":
            f.append(StgSabiogoVentas.producto == producto_filter)
        return f

    medida_expr = {
        "importe": StgSabiogoVentas.subtot,
        "cajas": StgSabiogoVentas.cajas,
        "kilos": StgSabiogoVentas.kilos,
    }[medida]
    # El orden del ranking sigue la medida elegida.
    top15_rows = (
        db.session.query(
            col_expr.label("nombre"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
            func.sum(StgSabiogoVentas.kilos).label("kilos"),
            func.sum(StgSabiogoVentas.subtot).label("monto"),
            func.count(func.distinct(StgSabiogoVentas.nro_comprob)).label("facturas"),
        )
        .filter(*base_filters(fecha_desde, fecha_hasta))
        .filter(col_expr.isnot(None))
        .group_by(col_expr)
        .order_by(func.sum(medida_expr).desc(), col_expr.asc())
        .limit(15)
        .all()
    )

    # Evolución mensual últimos 6M
    evo_rows = (
        db.session.query(
            func.date_trunc("month", StgSabiogoVentas.fecha).label("periodo"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
            func.sum(StgSabiogoVentas.kilos).label("kilos"),
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
            "medida": medida,
            "titulo": titulos.get(tipo, "Top 15"),
            "top15": [
                {
                    "nombre": r.nombre or "–",
                    "cajas": float(r.cajas or 0),
                    "kilos": float(r.kilos or 0),
                    "monto": float(r.monto or 0),
                    "facturas": int(r.facturas or 0),
                }
                for r in top15_rows
            ],
            "evo_6m": [
                {
                    "periodo": _formatear_mes(r.periodo),
                    "cajas": float(r.cajas or 0),
                    "kilos": float(r.kilos or 0),
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
    from services.comercial_criterios import filtro_comprobante_panel_ventas
    from services.comercial_pre import expresion_vendedor_resuelta
    from services.vendedores_comerciales import resolver_nombre_vendedor

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

    # Seis meses calendario hasta la fecha de corte seleccionada.
    corte_mes = fecha_hasta.year * 12 + fecha_hasta.month - 1
    evo_anio, evo_mes = divmod(corte_mes - 5, 12)
    evo_desde = date(evo_anio, evo_mes + 1, 1)
    evo_hasta = fecha_hasta

    vendedor_expr = expresion_vendedor_resuelta()

    def base_f(fd, fh):
        f = [
            StgSabiogoVentas.estado == "procesado",
            StgSabiogoVentas.fecha.between(fd, fh),
            filtro_comprobante_panel_ventas(),
        ]
        if empresa not in ("", "TODAS"):
            f.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa)
        if vendedor_f:
            f.append(vendedor_expr == resolver_nombre_vendedor(vendedor_f))
        if cliente_f:
            f.append(StgSabiogoVentas.cliente == cliente_f)
        if producto_f:
            f.append(StgSabiogoVentas.producto == producto_f)
        return f

    # ── 1. Mix global: top 10 productos + "Otros" ──
    producto_mix_expr = func.coalesce(
        func.nullif(func.trim(StgSabiogoVentas.producto), ""), "Sin producto"
    )
    mg_rows = (
        db.session.query(
            producto_mix_expr.label("producto"),
            func.sum(StgSabiogoVentas.cajas).label("cajas"),
        )
        .filter(*base_f(fecha_desde, fecha_hasta))
        .group_by(producto_mix_expr)
        .order_by(func.sum(StgSabiogoVentas.cajas).desc())
        .all()
    )
    total_cajas = sum(float(r.cajas or 0) for r in mg_rows)
    mix_global = []
    otros = 0.0
    for i, r in enumerate(mg_rows):
        c = float(r.cajas or 0)
        if i < 10:
            mix_global.append({
                "producto": r.producto,
                "cajas": c,
                "pct": round(c / total_cajas * 100, 1) if total_cajas else 0,
            })
        else:
            otros += c
    if len(mg_rows) > 10:
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
        .filter(*base_f(evo_desde, evo_hasta))
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
            .filter(*base_f(evo_desde, evo_hasta))
            .filter(StgSabiogoVentas.producto.in_(top3_prods))
            .group_by(func.date_trunc("month", StgSabiogoVentas.fecha), StgSabiogoVentas.producto)
            .order_by(func.date_trunc("month", StgSabiogoVentas.fecha))
            .all()
        )
        # agrupar por mes
        evo_map: dict[str, dict[str, float]] = {}
        for r in evo_raw:
            mes = _formatear_mes(r.periodo) or "?"
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
    from services.comercial_criterios import filtro_comprobante_panel_ventas
    from services.comercial_pre import expresion_vendedor_resuelta
    from services.vendedores_comerciales import resolver_nombre_vendedor

    hoy = today_local_date()
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
    if fecha_desde and fecha_hasta:
        desde, hasta = fecha_desde, fecha_hasta
    elif fecha_desde:
        desde, hasta = fecha_desde, hoy
    elif fecha_hasta:
        desde, hasta = fecha_hasta - timedelta(days=29), fecha_hasta
    else:
        desde, hasta = hoy - timedelta(days=29), hoy

    empresa = (request.args.get("empresa") or "TODAS").upper().strip()
    vendedor_filter = (request.args.get("vendedor") or "").strip()
    cliente_filter = (request.args.get("cliente") or "").strip()
    producto_filter = (request.args.get("producto") or "").strip()
    medida_filter = (request.args.get("medida") or "importe").strip().lower()
    if medida_filter not in ("importe", "cajas", "kilos"):
        return jsonify({"error": "medida debe ser importe, cajas o kilos"}), 400
    pagina = request.args.get("pagina", default=1, type=int)
    if pagina is None or pagina < 1:
        return jsonify({"error": "pagina debe ser un entero mayor que cero"}), 400
    vendedor_expr = expresion_vendedor_resuelta()
    cliente_expr = func.trim(StgSabiogoVentas.cliente)
    producto_expr = func.coalesce(
        func.nullif(func.trim(StgSabiogoVentas.producto), ""), "Sin producto"
    )
    comprobante_expr = func.trim(StgSabiogoVentas.nro_comprob)
    documento_expr = case(
        (func.nullif(comprobante_expr, "").isnot(None), comprobante_expr),
        else_="linea:" + cast(StgSabiogoVentas.id, String),
    )
    filtros_documento = [
        StgSabiogoVentas.estado == "procesado",
        filtro_comprobante_panel_ventas(),
        StgSabiogoVentas.fecha <= hasta,
        StgSabiogoVentas.vendedor.isnot(None),
        func.trim(StgSabiogoVentas.vendedor) != "",
        cliente_expr.isnot(None),
        cliente_expr != "",
    ]
    if empresa not in ("", "TODAS"):
        filtros_documento.append(
            func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa
        )
    if vendedor_filter:
        filtros_documento.append(
            vendedor_expr == resolver_nombre_vendedor(vendedor_filter)
        )
    if cliente_filter:
        filtros_documento.append(cliente_expr == cliente_filter)
    if producto_filter:
        filtros_documento.append(producto_expr == producto_filter)

    dias_ventana = (hasta - desde).days + 1
    desde_anterior = desde - timedelta(days=dias_ventana)
    hasta_anterior = desde - timedelta(days=1)

    # Una fila lógica por comprobante, aunque tenga varias líneas de productos.
    documentos = (
        db.session.query(
            vendedor_expr.label("vendedor"),
            cliente_expr.label("cliente"),
            documento_expr.label("nro_comprob"),
            func.min(StgSabiogoVentas.fecha).label("fecha"),
        )
        .filter(*filtros_documento)
        .group_by(vendedor_expr, cliente_expr, documento_expr)
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
    def como_date(value):
        return value.date() if isinstance(value, datetime) else value

    clientes_por_vendedor: dict[str, dict[str, dict]] = {}
    for row in clientes_rows:
        clientes_por_vendedor.setdefault(row.vendedor, {})[row.cliente] = {
            "primera_compra": como_date(row.primera_compra),
            "ultima_compra": como_date(row.ultima_compra),
        }

    activos_rows = (
        db.session.query(documentos.c.vendedor, documentos.c.cliente)
        .filter(documentos.c.fecha.between(desde, hasta))
        .distinct()
        .all()
    )
    activos_por_vendedor: dict[str, set[str]] = {}
    for vendedor, cliente in activos_rows:
        activos_por_vendedor.setdefault(vendedor, set()).add(cliente)

    def agrupar_ventas_por_cliente(inicio, fin):
        return (
            db.session.query(
                vendedor_expr.label("vendedor"),
                cliente_expr.label("cliente"),
                func.sum(StgSabiogoVentas.subtot).label("plata"),
                func.sum(StgSabiogoVentas.cajas).label("cajas"),
                func.sum(StgSabiogoVentas.kilos).label("kilos"),
            )
            .filter(*filtros_documento)
            .filter(StgSabiogoVentas.fecha.between(inicio, fin))
            .group_by(vendedor_expr, cliente_expr)
            .all()
        )

    def mapear_ventas(rows):
        resultado: dict[str, dict[str, dict[str, float]]] = {}
        for row in rows:
            resultado.setdefault(row.vendedor, {})[row.cliente] = {
                "plata": float(_to_float(row.plata)),
                "cajas": float(_to_float(row.cajas)),
                "kilos": float(_to_float(row.kilos)),
            }
        return resultado

    plata_actual_por_cliente = mapear_ventas(agrupar_ventas_por_cliente(desde, hasta))
    plata_anterior_por_cliente = mapear_ventas(
        agrupar_ventas_por_cliente(desde_anterior, hasta_anterior)
    )
    compras_previas_rows = (
        db.session.query(
            documentos.c.vendedor,
            documentos.c.cliente,
            func.max(documentos.c.fecha).label("ultima_compra"),
        )
        .filter(documentos.c.fecha.between(desde_anterior, hasta_anterior))
        .group_by(documentos.c.vendedor, documentos.c.cliente)
        .all()
    )
    ultima_compra_anterior: dict[str, dict[str, date]] = {}
    clientes_previos_por_vendedor: dict[str, set[str]] = {}
    for row in compras_previas_rows:
        ultima_compra_anterior.setdefault(row.vendedor, {})[row.cliente] = como_date(
            row.ultima_compra
        )
        clientes_previos_por_vendedor.setdefault(row.vendedor, set()).add(row.cliente)

    productos_activos_rows = (
        db.session.query(
            vendedor_expr.label("vendedor"),
            cliente_expr.label("cliente"),
            func.count(
                func.distinct(func.nullif(func.trim(StgSabiogoVentas.producto), ""))
            ).label("productos"),
        )
        .filter(*filtros_documento)
        .filter(StgSabiogoVentas.fecha.between(desde, hasta))
        .group_by(vendedor_expr, cliente_expr)
        .all()
    )
    productos_por_cliente: dict[str, dict[str, int]] = {}
    for row in productos_activos_rows:
        productos_por_cliente.setdefault(row.vendedor, {})[row.cliente] = int(
            row.productos or 0
        )

    productos_anteriores_rows = (
        db.session.query(
            vendedor_expr.label("vendedor"),
            cliente_expr.label("cliente"),
            func.count(
                func.distinct(func.nullif(func.trim(StgSabiogoVentas.producto), ""))
            ).label("productos"),
        )
        .filter(*filtros_documento)
        .filter(StgSabiogoVentas.fecha.between(desde_anterior, hasta_anterior))
        .group_by(vendedor_expr, cliente_expr)
        .all()
    )
    productos_anteriores_por_cliente: dict[str, dict[str, int]] = {}
    for row in productos_anteriores_rows:
        productos_anteriores_por_cliente.setdefault(row.vendedor, {})[row.cliente] = int(
            row.productos or 0
        )

    productos_rows = (
        db.session.query(
            vendedor_expr.label("vendedor"),
            producto_expr.label("producto"),
            func.sum(StgSabiogoVentas.subtot).label("plata"),
        )
        .filter(*filtros_documento)
        .filter(StgSabiogoVentas.fecha.between(desde, hasta))
        .group_by(vendedor_expr, producto_expr)
        .all()
    )
    plata_por_producto: dict[str, dict[str, float]] = {}
    for row in productos_rows:
        plata_por_producto.setdefault(row.vendedor, {})[row.producto] = float(
            _to_float(row.plata)
        )

    vendedores = []
    clientes_atencion = []
    medida_clave = {"importe": "plata", "cajas": "cajas", "kilos": "kilos"}[medida_filter]
    for vendedor in sorted(clientes_por_vendedor, key=str.casefold):
        clientes = clientes_por_vendedor[vendedor]
        nombres = sorted(clientes, key=str.casefold)
        nuevos_nombres = [
            nombre
            for nombre in nombres
            if desde <= clientes[nombre]["primera_compra"] <= hasta
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
                "dias": (hasta - clientes[nombre]["ultima_compra"]).days,
            }
            for nombre in nombres
        ]
        ultimas.sort(key=lambda item: (-item["dias"], item["nombre"].casefold()))

        activos = activos_por_vendedor.get(vendedor, set())
        clientes_previos = clientes_previos_por_vendedor.get(vendedor, set())
        ventas_actuales = plata_actual_por_cliente.get(vendedor, {})
        ventas_anteriores = plata_anterior_por_cliente.get(vendedor, {})
        ultima_anterior = ultima_compra_anterior.get(vendedor, {})
        recurrentes_nombres = sorted(activos & clientes_previos, key=str.casefold)
        recuperados_nombres = sorted(
            (
                nombre
                for nombre in activos - clientes_previos
                if clientes.get(nombre, {}).get("primera_compra")
                and clientes[nombre]["primera_compra"] < desde
            ),
            key=str.casefold,
        )

        caidos = [
            {
                "nombre": nombre,
                "dias": (hasta - fecha).days,
                "plata_anterior": float(
                    ventas_anteriores.get(nombre, {}).get("plata", 0.0)
                ),
            }
            for nombre, fecha in ultima_anterior.items()
            if nombre not in activos
        ]
        caidos.sort(key=lambda item: (-item["dias"], item["nombre"].casefold()))

        baja = []
        for nombre in sorted(activos & set(ultima_anterior), key=str.casefold):
            anterior = float(ventas_anteriores.get(nombre, {}).get("plata", 0.0))
            actual = float(ventas_actuales.get(nombre, {}).get("plata", 0.0))
            if anterior <= 0 or actual > anterior * 0.8:
                continue
            baja.append(
                {
                    "nombre": nombre,
                    "plata_actual": actual,
                    "plata_anterior": anterior,
                    "variacion_pct": round((actual - anterior) / anterior * 100, 1),
                }
            )
        baja.sort(key=lambda item: (item["variacion_pct"], item["nombre"].casefold()))


        productos_activos = productos_por_cliente.get(vendedor, {})
        promedio_productos = (
            sum(productos_activos.get(nombre, 0) for nombre in activos) / len(activos)
            if len(activos) > 1
            else None
        )
        canasta_flaca = []
        if promedio_productos is not None:
            for nombre in sorted(activos, key=str.casefold):
                cantidad_productos = productos_activos.get(nombre, 0)
                if cantidad_productos < promedio_productos / 2:
                    canasta_flaca.append(
                        {
                            "nombre": nombre,
                            "productos": cantidad_productos,
                            "promedio": round(promedio_productos, 1),
                        }
                    )
        canasta_flaca.sort(key=lambda item: (item["productos"], item["nombre"].casefold()))

        def fila_atencion(nombre, senal, ultima, medida="importe", valor_anterior=None, valor_actual=None):
            datos_anteriores = ventas_anteriores.get(nombre, {})
            datos_actuales = ventas_actuales.get(nombre, {})
            importe_anterior = float(datos_anteriores.get("plata", 0.0))
            importe_actual = float(datos_actuales.get("plata", 0.0))
            base_variacion = valor_anterior if valor_anterior is not None else importe_anterior
            actual_variacion = valor_actual if valor_actual is not None else importe_actual
            variacion_pct = (
                round((actual_variacion - base_variacion) / abs(base_variacion) * 100, 1)
                if base_variacion != 0
                else None
            )
            return {
                "vendedor": vendedor,
                "cliente": nombre,
                "senal": senal,
                "ultima_compra": ultima.isoformat() if ultima else None,
                "dias_sin_comprar": (hasta - ultima).days if ultima else None,
                "importe_anterior": importe_anterior,
                "importe_actual": importe_actual,
                "diferencia": importe_actual - importe_anterior,
                "variacion_pct": variacion_pct,
                "medida": medida,
                "valor_anterior": valor_anterior,
                "valor_actual": valor_actual,
            }

        for item in caidos:
            clientes_atencion.append(
                fila_atencion(
                    item["nombre"],
                    "Sin recompra",
                    ultima_anterior.get(item["nombre"]),
                )
            )

        for nombre in sorted(activos & set(ultima_anterior), key=str.casefold):
            datos_anteriores = ventas_anteriores.get(nombre, {})
            datos_actuales = ventas_actuales.get(nombre, {})
            valor_anterior = float(datos_anteriores.get(medida_clave, 0.0))
            valor_actual = float(datos_actuales.get(medida_clave, 0.0))
            if valor_anterior > 0 and valor_actual <= valor_anterior * 0.8:
                clientes_atencion.append(
                    fila_atencion(
                        nombre,
                        "Compra en baja",
                        clientes.get(nombre, {}).get("ultima_compra"),
                        medida=medida_filter,
                        valor_anterior=valor_anterior,
                        valor_actual=valor_actual,
                    )
                )

        productos_anteriores = productos_anteriores_por_cliente.get(vendedor, {})
        for nombre in sorted(activos & set(productos_anteriores), key=str.casefold):
            productos_previos = productos_anteriores.get(nombre, 0)
            productos_actuales = productos_activos.get(nombre, 0)
            if productos_previos >= 2 and productos_actuales * 2 <= productos_previos:
                clientes_atencion.append(
                    fila_atencion(
                        nombre,
                        "Menor variedad",
                        clientes.get(nombre, {}).get("ultima_compra"),
                        medida="productos",
                        valor_anterior=float(productos_previos),
                        valor_actual=float(productos_actuales),
                    )
                )

        vendedores.append(
            {
                "nombre": vendedor,
                "total": len(nombres),
                "activos": len(activos),
                "clientes_compradores": len(activos),
                "clientes_sin_recompra": len(caidos),
                "importe_pre_sin_recompra_anterior": sum(
                    item["plata_anterior"] for item in caidos
                ),
                "nuevos": [{"nombre": nombre} for nombre in nuevos_nombres],
                "recurrentes": [{"nombre": nombre} for nombre in recurrentes_nombres],
                "recuperados": [{"nombre": nombre} for nombre in recuperados_nombres],
                "lista": [{"nombre": nombre} for nombre in nombres],
                "productos": productos,
                "ultimas": [
                    {**item, "fecha": item["fecha"].isoformat()}
                    for item in ultimas[:12]
                ],
                "caidos": caidos[:8],
                "baja": baja[:8],
                "canasta_flaca": canasta_flaca[:8],
            }
        )

    for vendedor_data in vendedores:
        vendedor_data["clientes_reduccion"] = [
            alerta
            for alerta in clientes_atencion
            if alerta["vendedor"] == vendedor_data["nombre"]
            and alerta["senal"] == "Compra en baja"
        ]
        vendedor_data["clientes_menor_variedad"] = [
            alerta
            for alerta in clientes_atencion
            if alerta["vendedor"] == vendedor_data["nombre"]
            and alerta["senal"] == "Menor variedad"
        ]

    clientes_atencion.sort(
        key=lambda item: (
            -max(0.0, -float(item["diferencia"])),
            -(item["dias_sin_comprar"] or 0),
            item["vendedor"].casefold(),
            item["cliente"].casefold(),
            item["senal"],
        )
    )
    total_casos = len(clientes_atencion)
    por_pagina = 20
    inicio_pagina = (pagina - 1) * por_pagina
    clientes_atencion_pagina = clientes_atencion[inicio_pagina : inicio_pagina + por_pagina]

    return jsonify(
        {
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "vendedores": vendedores,
            "clientes_atencion": clientes_atencion_pagina,
            "total_casos": total_casos,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": max(1, (total_casos + por_pagina - 1) // por_pagina),
        }
    )


@api.get("/dashboard-comercial/equipo")
def api_dashboard_comercial_equipo():
    """Resumen de equipo, cumplimiento mensual y diagnóstico PRE."""
    from services.comercial_pre import calcular_resumen_pre
    from services.comercial_cartera import calcular_cartera_comercial
    from services.objetivos_comerciales import obtener_objetivos_comerciales
    from services.vendedores_comerciales import resolver_nombre_vendedor

    hoy = today_local_date()
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

    if fecha_desde and fecha_hasta:
        desde, hasta = fecha_desde, fecha_hasta
    elif fecha_desde:
        desde, hasta = fecha_desde, hoy
    elif fecha_hasta:
        desde, hasta = date(fecha_hasta.year, fecha_hasta.month, 1), fecha_hasta
    else:
        desde, hasta = date(hoy.year, hoy.month, 1), hoy

    empresa = (request.args.get("empresa") or "TODAS").strip().upper()
    if empresa not in ("TODAS", "CARNES", "LACTEOS"):
        return jsonify({"error": "empresa debe ser TODAS, CARNES o LACTEOS"}), 400
    medida = (request.args.get("medida") or "importe").strip().lower()
    if medida not in ("importe", "cajas", "kilos"):
        return jsonify({"error": "medida debe ser importe, cajas o kilos"}), 400

    vendedor_filter = (request.args.get("vendedor") or "").strip()
    vendedor_visible = resolver_nombre_vendedor(vendedor_filter) if vendedor_filter else None
    cliente_filter = (request.args.get("cliente") or "").strip() or None
    producto_filter = (request.args.get("producto") or "").strip() or None
    rango_dias = (hasta - desde).days + 1
    anterior_hasta = desde - timedelta(days=1)
    anterior_desde = anterior_hasta - timedelta(days=rango_dias - 1)
    primer_dia_mes = date(hasta.year, hasta.month, 1)
    mes_objetivos = hasta.strftime("%Y-%m")

    try:
        resumen_actual = calcular_resumen_pre(
            desde,
            hasta,
            empresa=empresa,
            vendedor=vendedor_filter or None,
            criterio_clientes=True,
        )
        resumen_anterior = calcular_resumen_pre(
            anterior_desde,
            anterior_hasta,
            empresa=empresa,
            vendedor=vendedor_filter or None,
            criterio_clientes=True,
        )
        resumen_mes = calcular_resumen_pre(
            primer_dia_mes,
            hasta,
            empresa=empresa,
            limite=100000,
            criterio_clientes=True,
        )
        objetivos = obtener_objetivos_comerciales(
            mes=mes_objetivos,
            empresa=empresa,
            medida=medida,
            corte=hasta,
            criterio_clientes=True,
        )

        seguimiento_query = {key: value for key, value in request.args.items()}
        seguimiento_query["fecha_desde"] = desde.isoformat()
        seguimiento_query["fecha_hasta"] = hasta.isoformat()
        seguimiento_query["empresa"] = empresa
        seguimiento_query["medida"] = medida
        with current_app.test_request_context(
            "/api/dashboard-comercial/seguimiento",
            query_string=seguimiento_query,
        ):
            seguimiento_resultado = api_dashboard_comercial_seguimiento()
        if isinstance(seguimiento_resultado, tuple):
            return seguimiento_resultado
        if seguimiento_resultado.status_code >= 400:
            return seguimiento_resultado
        seguimiento = seguimiento_resultado.get_json(silent=True) or {}
        seguimiento_por_vendedor = {
            fila["nombre"]: fila for fila in seguimiento.get("vendedores", [])
        }

        from services.comercial_paneles import comparativo

        resumen_keys = {
            "importe_pre": "importe_pre",
            "cajas": "cajas",
            "kilos": "kilos",
            "clientes_compradores": "clientes_compradores",
        }
        kpis = {
            etiqueta: comparativo(
                resumen_actual[clave],
                resumen_anterior[clave],
            )
            for etiqueta, clave in resumen_keys.items()
        }

        medida_resumen_key = {"importe": "plata", "cajas": "cajas", "kilos": "kilos"}[medida]
        realizado_mes_por_vendedor = {
            fila["nombre"]: float(fila.get(medida_resumen_key) or 0)
            for fila in resumen_mes.get("por_vendedor", [])
        }
        equipo = []
        nombres_objetivo = set()
        for objetivo in objetivos:
            nombre = objetivo["nombre_visible"]
            nombres_objetivo.add(nombre)
            seguimiento_vendedor = seguimiento_por_vendedor.get(nombre, {})
            equipo.append(
                {
                    "vendedor_id": objetivo["vendedor_id"],
                    "vendedor": nombre,
                    "realizado": objetivo["realizado"],
                    "meta": objetivo["meta"],
                    "cumplimiento": objetivo["cumplimiento"],
                    "desvio": objetivo["desvio"],
                    "estado": objetivo["estado"],
                    "cobertura": objetivo["cobertura"],
                    "clientes_compradores": seguimiento_vendedor.get(
                        "clientes_compradores", 0
                    ),
                    "clientes_sin_recompra": seguimiento_vendedor.get(
                        "clientes_sin_recompra", 0
                    ),
                    "importe_pre_sin_recompra_anterior": seguimiento_vendedor.get(
                        "importe_pre_sin_recompra_anterior", 0.0
                    ),
                }
            )

        for nombre, seguimiento_vendedor in seguimiento_por_vendedor.items():
            if nombre in nombres_objetivo:
                continue
            equipo.append(
                {
                    "vendedor_id": None,
                    "vendedor": nombre,
                    "realizado": realizado_mes_por_vendedor.get(nombre, 0.0),
                    "meta": None,
                    "cumplimiento": None,
                    "desvio": None,
                    "estado": "Sin meta",
                    "cobertura": "sin_meta",
                    "clientes_compradores": seguimiento_vendedor.get(
                        "clientes_compradores", 0
                    ),
                    "clientes_sin_recompra": seguimiento_vendedor.get(
                        "clientes_sin_recompra", 0
                    ),
                    "importe_pre_sin_recompra_anterior": seguimiento_vendedor.get(
                        "importe_pre_sin_recompra_anterior", 0.0
                    ),
                }
            )

        if vendedor_visible:
            equipo = [fila for fila in equipo if fila["vendedor"] == vendedor_visible]

        def orden_equipo(fila):
            if fila["estado"] == "Sin meta":
                return (2, 0.0, fila["vendedor"].casefold())
            if fila["desvio"] is None:
                return (1, 0.0, fila["vendedor"].casefold())
            return (0, float(fila["desvio"]), fila["vendedor"].casefold())

        equipo.sort(key=orden_equipo)

        diagnostico = None
        if vendedor_filter:
            resumen_detalle_actual = calcular_resumen_pre(
                desde,
                hasta,
                empresa=empresa,
                vendedor=vendedor_filter,
                cliente=cliente_filter,
                producto=producto_filter,
                limite=100000,
                criterio_clientes=True,
            )
            resumen_detalle_anterior = calcular_resumen_pre(
                anterior_desde,
                anterior_hasta,
                empresa=empresa,
                vendedor=vendedor_filter,
                cliente=cliente_filter,
                producto=producto_filter,
                limite=100000,
                criterio_clientes=True,
            )
            fila_seguimiento = seguimiento_por_vendedor.get(vendedor_visible, {})

            def concentracion(filas):
                ordenadas = sorted(
                    filas,
                    key=lambda fila: (-float(fila.get("plata") or 0), fila["nombre"].casefold()),
                )
                principales = ordenadas[:9]
                resto = ordenadas[9:]
                if resto:
                    total_otros = sum(float(fila.get("plata") or 0) for fila in resto)
                    total = sum(float(fila.get("plata") or 0) for fila in ordenadas)
                    principales.append(
                        {
                            "nombre": "Otros",
                            "plata": total_otros,
                            "pct": round(total_otros / total * 100, 1) if total else 0.0,
                        }
                    )
                return sorted(
                    principales,
                    key=lambda fila: (-float(fila.get("pct") or 0), fila["nombre"].casefold()),
                )

            diagnostico = {
                "vendedor": vendedor_visible or vendedor_filter,
                "estado_datos": (
                    "disponible" if resumen_detalle_actual["lineas_pre"] else "sin_operaciones"
                ),
                "serie_actual": resumen_detalle_actual["por_fecha"],
                "serie_anterior": resumen_detalle_anterior["por_fecha"],
                "nuevos": fila_seguimiento.get("nuevos", []),
                "recurrentes": fila_seguimiento.get("recurrentes", []),
                "recuperados": fila_seguimiento.get("recuperados", []),
                "clientes_reduccion": fila_seguimiento.get("clientes_reduccion", []),
                "clientes_menor_variedad": fila_seguimiento.get(
                    "clientes_menor_variedad", []
                ),
                "concentracion_clientes": concentracion(
                    resumen_detalle_actual["por_cliente"]
                ),
                "concentracion_productos": concentracion(
                    resumen_detalle_actual["por_producto"]
                ),
            }

        cartera = calcular_cartera_comercial(
            desde,
            hasta,
            empresa=empresa,
            vendedor=vendedor_filter or None,
            cliente=cliente_filter,
            producto=producto_filter,
            criterio_clientes=True,
        )
        return jsonify(
            {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
                "desde_anterior": anterior_desde.isoformat(),
                "hasta_anterior": anterior_hasta.isoformat(),
                "mes_objetivos": mes_objetivos,
                "empresa": empresa,
                "medida": medida,
                "estado_datos": (
                    "disponible" if resumen_actual["lineas_pre"] else "sin_operaciones"
                ),
                "kpis": kpis,
                "equipo": equipo,
                "cartera": cartera,
                "total_casos": seguimiento.get("total_casos", 0),
                "pagina": seguimiento.get("pagina", 1),
                "por_pagina": seguimiento.get("por_pagina", 20),
                "total_paginas": seguimiento.get("total_paginas", 1),
                "clientes_atencion": seguimiento.get("clientes_atencion", []),
                "diagnostico": diagnostico,
                "ultima_importacion": resumen_actual["ultima_importacion"],
                "fecha_maxima_pre": resumen_actual["fecha_maxima_pre"],
            }
        )
    except Exception:
        return jsonify({"error": "No se pudo cargar el equipo comercial"}), 500
