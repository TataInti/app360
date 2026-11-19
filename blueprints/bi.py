from datetime import datetime, date, timedelta
from decimal import Decimal
import io

from flask import Blueprint, request, jsonify, send_file, render_template, current_app
from sqlalchemy import func, desc, extract, text
from sqlalchemy.exc import ProgrammingError

from models import (
    Adelanto,
    Asistencia,
    BusinessUnit,
    CategoriaGasto,
    Client,
    Employee,
    Lead,
    Location,
    MovimientoCaja,
    Product,
    Promocion,
    StockLevel,
    Venta,
    db,
)
from security import protect_blueprint
from services.resultado_comercial_service import ResultadoComercialService
from services.sabiogo_service import SabiogoService
from models.time_utils import today_local_date

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


def _gastos_sum(desde=None, hasta=None) -> float:
    """Suma de movimientos de caja con categoría de gasto (reemplaza tabla gasto)."""
    q = db.session.query(func.sum(MovimientoCaja.monto)).filter(
        MovimientoCaja.categoria_gasto_id.isnot(None),
        MovimientoCaja.estado != "anulado",
    )
    if desde is not None and hasta is not None:
        q = q.filter(MovimientoCaja.fecha_hora.between(desde, hasta))
    elif hasta is not None:
        q = q.filter(MovimientoCaja.fecha_hora <= hasta)
    return float(q.scalar() or 0)


def _gastos_mes_q(desde, hasta):
    """Serie mensual de gastos agrupada por año/mes."""
    return (
        db.session.query(
            extract('year', MovimientoCaja.fecha_hora).label('y'),
            extract('month', MovimientoCaja.fecha_hora).label('m'),
            func.sum(MovimientoCaja.monto),
        )
        .filter(
            MovimientoCaja.categoria_gasto_id.isnot(None),
            MovimientoCaja.estado != "anulado",
            MovimientoCaja.fecha_hora.between(desde, hasta),
        )
        .group_by('y', 'm')
        .order_by('y', 'm')
        .all()
    )


def _gastos_cat_q(desde, hasta):
    """Mix de gastos por categoría."""
    return (
        db.session.query(
            func.coalesce(CategoriaGasto.nombre, 'Otros'),
            func.sum(MovimientoCaja.monto),
        )
        .join(CategoriaGasto, MovimientoCaja.categoria_gasto_id == CategoriaGasto.id)
        .filter(
            MovimientoCaja.estado != "anulado",
            MovimientoCaja.fecha_hora.between(desde, hasta),
        )
        .group_by(func.coalesce(CategoriaGasto.nombre, 'Otros'))
        .all()
    )


# RUTAS WEB
@bi_bp.route("/bi", methods=["GET"])
def bi_dashboard_web():
    """Dashboard de Business Intelligence"""
    return render_template("bi_dashboard.html")


# Endpoint principal del dashboard BI
@bi_bp.route("/api/bi/dashboard", methods=["GET"])
def bi_dashboard():
    """Dashboard BI productivo: rentabilidad SabioGo + finanzas internas."""
    fecha_desde_raw = request.args.get("fecha_desde")
    fecha_hasta_raw = request.args.get("fecha_hasta")
    vendedor_filter = (request.args.get("vendedor") or "").strip()
    producto_filter = (request.args.get("producto") or "").strip()
    empresa_filter = (request.args.get("empresa") or "TODAS").upper().strip()

    if not fecha_desde_raw or not fecha_hasta_raw:
        fecha_hasta_base = today_local_date()
        fecha_desde_base = fecha_hasta_base - timedelta(days=29)

        if not fecha_desde_raw:
            fecha_desde_raw = fecha_desde_base.isoformat()
        if not fecha_hasta_raw:
            fecha_hasta_raw = fecha_hasta_base.isoformat()

    try:
        fecha_desde = datetime.fromisoformat(fecha_desde_raw).date()
        fecha_hasta = datetime.fromisoformat(fecha_hasta_raw).date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    if fecha_desde > fecha_hasta:
        return jsonify({"error": "fecha_desde no puede ser mayor a fecha_hasta"}), 400
    if fecha_hasta > today_local_date():
        return jsonify({"error": "fecha_hasta no puede ser una fecha futura"}), 400

    # Contrato compartido con Ejecutivo. Los filtros asimétricos de vendedor y
    # producto se conservan en la URL por compatibilidad, pero ya no alteran el
    # cálculo porque no pueden aplicarse de forma equivalente a las compras.
    resultado = ResultadoComercialService().calcular(
        fecha_desde,
        fecha_hasta,
        empresa_filter,
    )
    kpis = resultado["kpis"]
    actividad = resultado["series"]["actividad_mensual"]
    pre_fac_resumen = SabiogoService().get_resumen_pre_fac(fecha_hasta)
    warnings = list(resultado["meta"]["warnings"])
    ignored_filters = [
        name
        for name, value in (
            ("vendedor", vendedor_filter),
            ("producto", producto_filter),
        )
        if value
    ]

    payload = {
        "periodo": resultado["periodo"],
        "filtros": {
            "empresa": empresa_filter,
            "vendedor": None,
            "producto": None,
        },
        "filtros_disponibles": {"vendedores": [], "productos": []},
        "kpis": {
            "facturacion": kpis["facturacion"],
            "compras": kpis["compras"],
            "diferencia_facturacion_compras": kpis["diferencia_facturacion_compras"],
            "ingresos_incluidos": kpis["ingresos_incluidos"],
            "egresos_incluidos": kpis["egresos_incluidos"],
            "resultado_gestion": kpis["resultado_gestion"],
            "resultado_sobre_facturacion_pct": kpis["resultado_sobre_facturacion_pct"],
            "ingresos_caja": kpis["ingresos_caja"],
            "egresos_caja": kpis["egresos_caja"],
            "caja_neta": kpis["caja_neta"],
            "movimientos_caja": kpis["movimientos_caja"],
            # Compatibilidad con la pantalla/API anterior.
            "ingresos_sabiogo": kpis["facturacion"],
            "costos_sabiogo": kpis["compras"],
            "margen_bruto_sabiogo": kpis["diferencia_facturacion_compras"],
            "margen_porcentual_sabiogo": (
                None
                if kpis["datos_insuficientes"]
                else kpis["diferencia_facturacion_compras"] / kpis["facturacion"] * 100
                if kpis["facturacion"]
                else 0.0
            ),
            "datos_insuficientes": kpis["datos_insuficientes"],
            "productos_activos_sabiogo": 0,
            "gastos_finanzas": kpis["egresos_incluidos"],
            "pre_acumulado": float(pre_fac_resumen.get("pre_acumulado", 0)),
            "fac_acumulado": float(pre_fac_resumen.get("fac_acumulado", 0)),
            "pre_fac_saldo": float(pre_fac_resumen.get("saldo_pre_fac", 0)),
        },
        "series": {
            "actividad_mensual": actividad,
            "caja_mensual": resultado["series"]["caja_mensual"],
            "margen_mensual": [
                {
                    "periodo": row["periodo"],
                    "ingresos": row["facturacion"],
                    "costos": row["compras"],
                    "margen": row["diferencia"],
                }
                for row in actividad
            ],
        },
        "analisis_financiero": resultado["analisis_financiero"],
        "sueldos_pagados": resultado["sueldos_pagados"],
        "detalles": {
            "conceptos_resultado": resultado["conceptos"]["desglose"],
            "conceptos_participantes": resultado["conceptos"]["participantes"],
            "top_productos_margen": [],
            "gastos_por_categoria": [
                {
                    "categoria": row["concepto"],
                    "tipo": row["tipo"],
                    "monto_total": row["monto"],
                }
                for row in resultado["conceptos"]["desglose"]
            ],
        },
        "conceptos": resultado["conceptos"],
        "meta": {
            **resultado["meta"],
            "warnings": warnings,
            "ignored_filters": ignored_filters,
        },
        "warning": " ".join(item["message"] for item in warnings) if warnings else None,
    }
    return jsonify(payload)

    try:
        try:
            db_engine = db.engine.dialect.name
        except Exception:
            db_engine = db.session.bind.dialect.name if db.session.bind else None
        # 1) Rentabilidad SabioGo (fuente principal)
        sabiogo_service = SabiogoService()
        # Si hay filtros de vendedor/producto/empresa, calcular KPIs directamente
        if vendedor_filter or producto_filter or empresa_filter not in ("", "TODAS"):
            from models.sabiogo import StgSabiogoVentas, StgSabiogoCompras
            _vf = [
                StgSabiogoVentas.estado == "procesado",
                func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") != "PRE",
                StgSabiogoVentas.fecha.between(fecha_desde, fecha_hasta),
            ]
            if vendedor_filter:
                _vf.append(StgSabiogoVentas.vendedor == vendedor_filter)
            if producto_filter:
                _vf.append(StgSabiogoVentas.producto == producto_filter)
            if empresa_filter not in ("", "TODAS"):
                _vf.append(func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa_filter)
            total_ingresos = float(
                db.session.query(func.sum(StgSabiogoVentas.subtot)).filter(*_vf).scalar() or 0
            )
            _cf = [
                StgSabiogoCompras.estado == "procesado",
                StgSabiogoCompras.fecha.between(fecha_desde, fecha_hasta),
            ]
            if producto_filter:
                _cf.append(StgSabiogoCompras.producto == producto_filter)
            if empresa_filter not in ("", "TODAS"):
                _cf.append(func.upper(func.coalesce(StgSabiogoCompras.origen, "")) == empresa_filter)
            total_costos = float(
                db.session.query(func.sum(StgSabiogoCompras.subtot)).filter(*_cf).scalar() or 0
            )
            rentabilidad_resumen = {
                "total_ingresos": total_ingresos,
                "total_costos": total_costos,
                "margen_bruto": total_ingresos - total_costos,
                "margen_porcentual": ((total_ingresos - total_costos) / total_ingresos * 100) if total_ingresos else 0,
                "productos_activos": 0,
            }
        else:
            rentabilidad_resumen = sabiogo_service.get_rentabilidad_resumen(fecha_desde, fecha_hasta)
        pre_fac_resumen = sabiogo_service.get_resumen_pre_fac(fecha_hasta)
        top_productos = sabiogo_service.get_top_productos_margen(
            limit=10,
            fecha_inicio=fecha_desde,
            fecha_fin=fecha_hasta,
        )

        # 2) Gastos internos — movimientos con categoria_gasto_id asignada
        _gq = (
            db.session.query(MovimientoCaja)
            .filter(
                MovimientoCaja.categoria_gasto_id.isnot(None),
                MovimientoCaja.fecha_hora.between(fecha_desde, fecha_hasta),
                MovimientoCaja.estado != "anulado",
            )
        )
        gastos_total = (
            db.session.query(func.sum(MovimientoCaja.monto))
            .filter(
                MovimientoCaja.categoria_gasto_id.isnot(None),
                MovimientoCaja.fecha_hora.between(fecha_desde, fecha_hasta),
                MovimientoCaja.estado != "anulado",
            )
            .scalar() or 0
        )

        gastos_categoria_rows = (
            db.session.query(
                CategoriaGasto.nombre,
                func.sum(MovimientoCaja.monto).label("monto_total")
            )
            .join(CategoriaGasto, MovimientoCaja.categoria_gasto_id == CategoriaGasto.id)
            .filter(
                MovimientoCaja.fecha_hora.between(fecha_desde, fecha_hasta),
                MovimientoCaja.estado != "anulado",
            )
            .group_by(CategoriaGasto.nombre)
            .order_by(desc(func.sum(MovimientoCaja.monto)))
            .all()
        )

        gastos_por_categoria = [
            {
                "categoria": nombre or "Sin categoría",
                "monto_total": float(monto_total or 0),
            }
            for nombre, monto_total in gastos_categoria_rows
        ]

        # 3) Tesorería (caja)
        caja_resumen = db.session.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto ELSE 0 END), 0) AS ingresos,
                    COALESCE(SUM(CASE WHEN tipo = 'egreso' THEN monto ELSE 0 END), 0) AS egresos,
                    COUNT(*) AS movimientos
                FROM movimientos_caja
                WHERE DATE(fecha_hora) BETWEEN :fecha_desde AND :fecha_hasta
                  AND estado != 'anulado'
                """
            ),
            {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
        ).first()

        ingresos_caja = caja_resumen.ingresos if caja_resumen else 0
        egresos_caja = caja_resumen.egresos if caja_resumen else 0
        movimientos_count = caja_resumen.movimientos if caja_resumen else 0

        # 4) Series mensuales para visualización (sin depender de vw_margen_producto)
        # Construir cláusula de filtro adicional para vendedor/producto
        _ventas_extra = ""
        _compras_extra = ""
        _params_mensual = {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta}
        if vendedor_filter:
            _ventas_extra += " AND vendedor = :vendedor"
            _params_mensual["vendedor"] = vendedor_filter
        if producto_filter:
            _ventas_extra += " AND producto = :producto"
            _params_mensual["producto"] = producto_filter
        if empresa_filter not in ("", "TODAS"):
            _ventas_extra += " AND UPPER(COALESCE(origen,'')) = :empresa"
            _compras_extra += " AND UPPER(COALESCE(origen,'')) = :empresa"
            _params_mensual["empresa"] = empresa_filter

        margen_mensual_rows = db.session.execute(
            text(
                f"""
                WITH ventas AS (
                    SELECT DATE_TRUNC('month', fecha)::date AS periodo, COALESCE(SUM(subtot), 0) AS ingresos
                    FROM stg_sabiogo_ventas
                                        WHERE estado = 'procesado'
                                            AND COALESCE(UPPER(TRIM(comprobante)), '') <> 'PRE'
                                            AND fecha BETWEEN :fecha_desde AND :fecha_hasta
                                            {_ventas_extra}
                    GROUP BY DATE_TRUNC('month', fecha)::date
                ),
                compras AS (
                    SELECT DATE_TRUNC('month', fecha)::date AS periodo, COALESCE(SUM(subtot), 0) AS costos
                    FROM stg_sabiogo_compras
                    WHERE estado = 'procesado' AND fecha BETWEEN :fecha_desde AND :fecha_hasta
                          {_compras_extra}
                    GROUP BY DATE_TRUNC('month', fecha)::date
                )
                SELECT
                    COALESCE(v.periodo, c.periodo) AS periodo,
                    COALESCE(v.ingresos, 0) AS ingresos,
                    COALESCE(c.costos, 0) AS costos,
                    COALESCE(v.ingresos, 0) - COALESCE(c.costos, 0) AS margen
                FROM ventas v
                FULL OUTER JOIN compras c ON v.periodo = c.periodo
                ORDER BY COALESCE(v.periodo, c.periodo)
                """
            ),
            _params_mensual,
        )

        # Listas de vendedores/productos disponibles en el período
        _avail_params = {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta}
        _avail_empresa_clause = ""
        if empresa_filter not in ("", "TODAS"):
            _avail_empresa_clause = " AND UPPER(COALESCE(origen,'')) = :empresa"
            _avail_params["empresa"] = empresa_filter
        vendedores_disponibles = [
            r[0] for r in db.session.execute(
                text(f"SELECT DISTINCT vendedor FROM stg_sabiogo_ventas WHERE estado='procesado' AND fecha BETWEEN :fecha_desde AND :fecha_hasta AND vendedor IS NOT NULL{_avail_empresa_clause} ORDER BY 1"),
                _avail_params,
            ).fetchall()
        ]
        productos_disponibles = [
            r[0] for r in db.session.execute(
                text(f"SELECT DISTINCT producto FROM stg_sabiogo_ventas WHERE estado='procesado' AND fecha BETWEEN :fecha_desde AND :fecha_hasta AND producto IS NOT NULL{_avail_empresa_clause} ORDER BY 1"),
                _avail_params,
            ).fetchall()
        ]

        margen_mensual = [
            {
                "periodo": row.periodo.isoformat() if row.periodo else None,
                "ingresos": float(row.ingresos or 0),
                "costos": float(row.costos or 0),
                "margen": float(row.margen or 0),
            }
            for row in margen_mensual_rows
        ]

        caja_mensual_rows = db.session.execute(
            text(
                """
                SELECT
                    DATE_TRUNC('month', fecha_hora)::date AS periodo,
                    COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto ELSE 0 END), 0) AS ingresos,
                    COALESCE(SUM(CASE WHEN tipo = 'egreso' THEN monto ELSE 0 END), 0) AS egresos
                FROM movimientos_caja
                WHERE DATE(fecha_hora) BETWEEN :fecha_desde AND :fecha_hasta
                  AND estado != 'anulado'
                GROUP BY DATE_TRUNC('month', fecha_hora)::date
                ORDER BY DATE_TRUNC('month', fecha_hora)::date
                """
            ),
            {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
        )

        caja_mensual = [
            {
                "periodo": row.periodo.isoformat() if row.periodo else None,
                "ingresos": float(row.ingresos or 0),
                "egresos": float(row.egresos or 0),
                "neto": float((row.ingresos or 0) - (row.egresos or 0)),
            }
            for row in caja_mensual_rows
        ]

        # 5) Calidad de datos SabioGo
        estado_ventas = db.session.execute(
            text(
                """
                SELECT estado, COUNT(*) AS total
                FROM stg_sabiogo_ventas
                WHERE fecha BETWEEN :fecha_desde AND :fecha_hasta
                GROUP BY estado
                """
            ),
            {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
        )
        estado_compras = db.session.execute(
            text(
                """
                SELECT estado, COUNT(*) AS total
                FROM stg_sabiogo_compras
                WHERE fecha BETWEEN :fecha_desde AND :fecha_hasta
                GROUP BY estado
                """
            ),
            {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
        )

        sin_mapeo_ventas = db.session.execute(
            text(
                """
                SELECT COUNT(*) AS total
                FROM stg_sabiogo_ventas v
                                LEFT JOIN sabiogo_product_map pm
                                        ON v.codigo = pm.codigo
                                        AND COALESCE(v.origen, 'LEGACY') = COALESCE(pm.origen, 'LEGACY')
                                        AND pm.activo = true
                WHERE v.fecha BETWEEN :fecha_desde AND :fecha_hasta
                  AND v.estado = 'procesado'
                  AND pm.product_id IS NULL
                """
            ),
            {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
        ).scalar() or 0

        sin_mapeo_compras = db.session.execute(
            text(
                """
                SELECT COUNT(*) AS total
                FROM stg_sabiogo_compras c
                                LEFT JOIN sabiogo_product_map pm
                                        ON c.codigo = pm.codigo
                                        AND COALESCE(c.origen, 'LEGACY') = COALESCE(pm.origen, 'LEGACY')
                                        AND pm.activo = true
                WHERE c.fecha BETWEEN :fecha_desde AND :fecha_hasta
                  AND c.estado = 'procesado'
                  AND pm.product_id IS NULL
                """
            ),
            {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
        ).scalar() or 0

        estados_ventas = {row.estado: int(row.total or 0) for row in estado_ventas}
        estados_compras = {row.estado: int(row.total or 0) for row in estado_compras}

        estado_ventas_global = db.session.execute(
            text(
                """
                SELECT estado, COUNT(*) AS total
                FROM stg_sabiogo_ventas
                GROUP BY estado
                """
            )
        )
        estado_compras_global = db.session.execute(
            text(
                """
                SELECT estado, COUNT(*) AS total
                FROM stg_sabiogo_compras
                GROUP BY estado
                """
            )
        )

        estados_ventas_global = {row.estado: int(row.total or 0) for row in estado_ventas_global}
        estados_compras_global = {row.estado: int(row.total or 0) for row in estado_compras_global}

        total_ventas_global = sum(estados_ventas_global.values())
        total_compras_global = sum(estados_compras_global.values())
        ventas_procesado_global = estados_ventas_global.get("procesado", 0)
        compras_procesado_global = estados_compras_global.get("procesado", 0)

        warning = None
        if db_engine != "postgresql":
            warning = f"Motor de base de datos detectado: {db_engine or 'desconocido'}. Se esperaba postgresql."
        elif (total_ventas_global > 0 and ventas_procesado_global == 0) or (
            total_compras_global > 0 and compras_procesado_global == 0
        ):
            warning = "Hay datos SabioGo cargados pero sin estado 'procesado'."

        payload = {
            "periodo": {
                "desde": fecha_desde.isoformat(),
                "hasta": fecha_hasta.isoformat(),
            },
            "filtros": {
                "vendedor": vendedor_filter or None,
                "producto": producto_filter or None,
            },
            "filtros_disponibles": {
                "vendedores": vendedores_disponibles,
                "productos": productos_disponibles,
            },
            "kpis": {
                "ingresos_sabiogo": float(rentabilidad_resumen.get("total_ingresos", 0)),
                "costos_sabiogo": float(rentabilidad_resumen.get("total_costos", 0)),
                "margen_bruto_sabiogo": float(rentabilidad_resumen.get("margen_bruto", 0)),
                "margen_porcentual_sabiogo": float(rentabilidad_resumen.get("margen_porcentual", 0)),
                "productos_activos_sabiogo": int(rentabilidad_resumen.get("productos_activos", 0)),
                "pre_acumulado": float(pre_fac_resumen.get("pre_acumulado", 0)),
                "fac_acumulado": float(pre_fac_resumen.get("fac_acumulado", 0)),
                "pre_fac_saldo": float(pre_fac_resumen.get("saldo_pre_fac", 0)),
                "gastos_finanzas": float(gastos_total),
                "ingresos_caja": float(ingresos_caja),
                "egresos_caja": float(egresos_caja),
                "caja_neta": float(ingresos_caja - egresos_caja),
                "movimientos_caja": int(movimientos_count),
            },
            "series": {
                "margen_mensual": margen_mensual,
                "caja_mensual": caja_mensual,
            },
            "detalles": {
                "top_productos_margen": top_productos,
                "gastos_por_categoria": gastos_por_categoria,
                "calidad_sabiogo": {
                    "ventas_por_estado": estados_ventas,
                    "compras_por_estado": estados_compras,
                    "ventas_por_estado_global": estados_ventas_global,
                    "compras_por_estado_global": estados_compras_global,
                    "sin_mapeo_ventas": int(sin_mapeo_ventas),
                    "sin_mapeo_compras": int(sin_mapeo_compras),
                    "db_engine": db_engine,
                },
            },
        }

        if warning:
            payload["warning"] = warning

        return jsonify(payload)
    except Exception as e:
        current_app.logger.error(f"Error BI dashboard: {e}", exc_info=True)
        return jsonify(
            {
                "error": "Error interno obteniendo BI dashboard",
                "periodo": {
                    "desde": fecha_desde.isoformat(),
                    "hasta": fecha_hasta.isoformat(),
                },
            }
        ), 500


# Nuevos endpoints para Inteligencia Financiera
@bi_bp.route("/api/bi/overview", methods=["GET"])
def bi_overview():
    rango = request.args.get("range", "6m")
    fecha_desde, fecha_hasta, prev_desde, prev_hasta = _parse_range(rango)

    # Ventas y gastos del periodo y previo
    ventas_total = float(
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    gastos_total = _gastos_sum(fecha_desde, fecha_hasta)
    ventas_prev = float(
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(prev_desde, prev_hasta))
        .scalar()
        or 0
    )
    gastos_prev = _gastos_sum(prev_desde, prev_hasta)

    margen_bruto = ventas_total - gastos_total
    net_margin = (margen_bruto / ventas_total) if ventas_total else 0
    gross_margin = (margen_bruto / ventas_total) if ventas_total else 0

    # Burn y runway (aprox: gastos operativos promediados por mes)
    months = max(1, (fecha_hasta - fecha_desde).days / 30)
    burn_rate = gastos_total / float(months)
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
                    "burn_rate": _delta(burn_rate, gastos_prev / float(months) if months else 0),
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
    gastos_mes = _gastos_mes_q(fecha_desde, fecha_hasta)

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
    # float: _gastos_sum devuelve float y restar un Decimal daba TypeError con ventas cargadas.
    ventas_total = float(
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    gastos_total = _gastos_sum(fecha_desde, fecha_hasta)
    margen_bruto = ventas_total - gastos_total
    gross_margin = (margen_bruto / ventas_total) if ventas_total else 0
    net_margin = gross_margin  # no tenemos impuestos/costos financieros separados
    ebitda_margin = gross_margin  # aproximación

    # Sin ventas o sin gastos del período no hay margen que medir: null, no 0 % ni 100 %.
    datos_insuficientes = not ventas_total or not gastos_total
    kpis = {
        "gross_margin": None if datos_insuficientes else float(gross_margin),
        "net_margin": None if datos_insuficientes else float(net_margin),
        "ebitda_margin": None if datos_insuficientes else float(ebitda_margin),
        "datos_insuficientes": datos_insuficientes,
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
    costos_mix_raw = _gastos_cat_q(fecha_desde, fecha_hasta)
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
    gastos_mes = _gastos_mes_q(fecha_desde, fecha_hasta)
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

    if datos_insuficientes:
        # Sin base de margen: series y alertas se devuelven vacías o en null.
        bruto_list = [None] * len(labels)
        neto_list = [None] * len(labels)
        bruto_serie = [None] * len(bruto_serie)
        neto_serie = [None] * len(neto_serie)
        alertas = []

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
    cash_in = float(
        db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
        .filter(Venta.fecha.between(fecha_desde, fecha_hasta))
        .scalar()
        or 0
    )
    cash_out = _gastos_sum(fecha_desde, fecha_hasta)
    cash_balance = cash_in - cash_out

    months = max(1, (fecha_hasta - fecha_desde).days / 30)
    burn_rate = cash_out / float(months)
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
    gastos_mes = _gastos_mes_q(fecha_desde, fecha_hasta)
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
    gastos_mix_raw = _gastos_cat_q(fecha_desde, fecha_hasta)
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

    def _ingresos_between(desde: date, hasta: date) -> float:
        """Ingresos del periodo.

        Prioriza tabla operativa `ventas` si existe. Si no existe (entornos donde
        solo está SabioGo staging), cae a `stg_sabiogo_ventas` en estado procesado.
        """
        try:
            val = (
                db.session.query(func.sum(Venta.precio_efectivo * Venta.cantidad))
                .filter(Venta.fecha.between(desde, hasta))
                .scalar()
            )
            return float(val or 0)
        except ProgrammingError:
            db.session.rollback()
            val = db.session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(subtot), 0) AS ingresos
                    FROM stg_sabiogo_ventas
                    WHERE estado = 'procesado'
                      AND fecha BETWEEN :desde AND :hasta
                    """
                ),
                {"desde": desde, "hasta": hasta},
            ).scalar()
            return float(val or 0)

    # Caja disponible = ingresos acumulados - gastos acumulados
    cash_on_hand = _ingresos_between(date(1900, 1, 1), fecha_hasta) - _gastos_sum(hasta=fecha_hasta)

    def _fcf_days(days: int):
        start = fecha_hasta - timedelta(days=days)
        return float(_ingresos_between(start, fecha_hasta) - _gastos_sum(start, fecha_hasta))

    fcf_30d = _fcf_days(30)
    fcf_90d = _fcf_days(90)

    # Burn y runway aproximados
    months = max(1, (fecha_hasta - fecha_desde).days / 30)
    gastos_periodo = _gastos_sum(fecha_desde, fecha_hasta)
    burn = gastos_periodo / float(months)
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
        ci = _ingresos_between(current, week_end)
        co = _gastos_sum(current, week_end)
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

    # Si no se especifican fechas, usar último mes. Aceptar solo AAAA-MM-DD.
    try:
        if not fecha_desde:
            fecha_desde = date.today() - timedelta(days=30)
        else:
            fecha_desde_original = fecha_desde
            fecha_desde = date.fromisoformat(fecha_desde)
            if fecha_desde.isoformat() != fecha_desde_original:
                raise ValueError("fecha_desde")

        if not fecha_hasta:
            fecha_hasta = date.today()
        else:
            fecha_hasta_original = fecha_hasta
            fecha_hasta = date.fromisoformat(fecha_hasta)
            if fecha_hasta.isoformat() != fecha_hasta_original:
                raise ValueError("fecha_hasta")
    except (TypeError, ValueError):
        return jsonify({"error": "Fecha inválida; usá el formato AAAA-MM-DD"}), 400

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
    gastos_dia = _gastos_sum(fecha, fecha)
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
        # Resumen de gastos por período (movimientos con categoría de gasto)
        query = MovimientoCaja.query.filter(
            MovimientoCaja.categoria_gasto_id.isnot(None),
            MovimientoCaja.estado != "anulado",
        )
        if fecha_desde:
            fd = datetime.fromisoformat(fecha_desde).date()
            query = query.filter(MovimientoCaja.fecha_hora >= fd)
        if fecha_hasta:
            fh = datetime.fromisoformat(fecha_hasta).date()
            query = query.filter(MovimientoCaja.fecha_hora <= fh)

        gastos = query.order_by(MovimientoCaja.fecha_hora.desc()).all()

        data = []
        for g in gastos:
            data.append({
                "Fecha": g.fecha_hora,
                "Categoría": g.categoria_gasto.nombre if g.categoria_gasto else "",
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
