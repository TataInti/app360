"""Cálculo compartido para Ejecutivo y Resultado comercial.

La métrica es deliberadamente un indicador de gestión:
facturación sin PRE - compras + conceptos de ingreso - conceptos de egreso.
No representa costo de mercadería vendida ni utilidad contable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy import and_, case, extract, func, or_

from models import CategoriaGasto, MovimientoCaja, StgSabiogoCompras, StgSabiogoVentas, db


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class ResultadoComercialService:
    METODO = "facturacion_menos_compras_mas_movimientos_configurados"

    @staticmethod
    def _ventas_filters(desde: date, hasta: date, empresa: str = "TODAS"):
        filters = [
            StgSabiogoVentas.estado == "procesado",
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") != "PRE",
            StgSabiogoVentas.fecha.between(desde, hasta),
        ]
        if empresa and empresa not in ("TODAS", ""):
            filters.append(
                func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa.upper()
            )
        return filters

    @staticmethod
    def _compras_filters(desde: date, hasta: date, empresa: str = "TODAS"):
        filters = [
            StgSabiogoCompras.estado == "procesado",
            StgSabiogoCompras.fecha.between(desde, hasta),
        ]
        if empresa and empresa not in ("TODAS", ""):
            filters.append(
                func.upper(func.coalesce(StgSabiogoCompras.origen, "")) == empresa.upper()
            )
        return filters

    @staticmethod
    def _movimientos_filters(desde: date, hasta: date):
        return [
            MovimientoCaja.fecha_hora >= datetime.combine(desde, time.min),
            MovimientoCaja.fecha_hora <= datetime.combine(hasta, time.max),
            MovimientoCaja.estado != "anulado",
        ]

    @staticmethod
    def _compatible_expr():
        return or_(
            CategoriaGasto.naturaleza == "ambos",
            CategoriaGasto.naturaleza == MovimientoCaja.tipo,
        )

    def calcular(self, desde: date, hasta: date, empresa: str = "TODAS") -> dict:
        # Las rutas entregan ``date``, pero las consultas agregadas de algunas
        # bases históricas devuelven ``datetime`` para la misma columna. El
        # servicio también se usa directamente en tareas y pruebas, por lo que
        # normalizamos el contrato en un único lugar.
        if isinstance(desde, datetime):
            desde = desde.date()
        if isinstance(hasta, datetime):
            hasta = hasta.date()
        empresa = (empresa or "TODAS").upper().strip()
        ventas_filters = self._ventas_filters(desde, hasta, empresa)
        compras_filters = self._compras_filters(desde, hasta, empresa)
        movimientos_filters = self._movimientos_filters(desde, hasta)

        facturacion = _float(
            db.session.query(func.sum(StgSabiogoVentas.subtot))
            .filter(*ventas_filters)
            .scalar()
        )
        compras = _float(
            db.session.query(func.sum(StgSabiogoCompras.subtot))
            .filter(*compras_filters)
            .scalar()
        )

        caja_row = (
            db.session.query(
                func.sum(
                    case((MovimientoCaja.tipo == "ingreso", MovimientoCaja.monto), else_=0)
                ).label("ingresos"),
                func.sum(
                    case((MovimientoCaja.tipo == "egreso", MovimientoCaja.monto), else_=0)
                ).label("egresos"),
                func.count(MovimientoCaja.id).label("cantidad"),
            )
            .filter(*movimientos_filters)
            .first()
        )
        ingresos_caja = _float(getattr(caja_row, "ingresos", 0))
        egresos_caja = _float(getattr(caja_row, "egresos", 0))

        concepto_rows = (
            db.session.query(
                CategoriaGasto.id,
                CategoriaGasto.nombre,
                CategoriaGasto.naturaleza,
                MovimientoCaja.tipo,
                func.sum(MovimientoCaja.monto).label("monto"),
                func.count(MovimientoCaja.id).label("cantidad"),
            )
            .join(CategoriaGasto, CategoriaGasto.id == MovimientoCaja.categoria_gasto_id)
            .filter(
                *movimientos_filters,
                CategoriaGasto.incluye_resultado.is_(True),
                CategoriaGasto.naturaleza.isnot(None),
                self._compatible_expr(),
            )
            .group_by(
                CategoriaGasto.id,
                CategoriaGasto.nombre,
                CategoriaGasto.naturaleza,
                MovimientoCaja.tipo,
            )
            .order_by(CategoriaGasto.nombre, MovimientoCaja.tipo)
            .all()
        )

        ingresos_incluidos = 0.0
        egresos_incluidos = 0.0
        desglose = []
        for row in concepto_rows:
            monto = _float(row.monto)
            if row.tipo == "ingreso":
                ingresos_incluidos += monto
                efecto = "suma"
            else:
                egresos_incluidos += monto
                efecto = "resta"
            desglose.append(
                {
                    "concepto_id": int(row.id),
                    "concepto": row.nombre,
                    "naturaleza": row.naturaleza,
                    "tipo": row.tipo,
                    "efecto": efecto,
                    "monto": monto,
                    "cantidad": int(row.cantidad or 0),
                }
            )

        conflictos = int(
            db.session.query(func.count(MovimientoCaja.id))
            .join(CategoriaGasto, CategoriaGasto.id == MovimientoCaja.categoria_gasto_id)
            .filter(
                *movimientos_filters,
                CategoriaGasto.naturaleza.isnot(None),
                CategoriaGasto.naturaleza != "ambos",
                CategoriaGasto.naturaleza != MovimientoCaja.tipo,
            )
            .scalar()
            or 0
        )
        conceptos_pendientes = int(
            db.session.query(func.count(CategoriaGasto.id))
            .filter(
                CategoriaGasto.activo.is_(True),
                CategoriaGasto.naturaleza.is_(None),
            )
            .scalar()
            or 0
        )

        diferencia = facturacion - compras
        resultado = diferencia + ingresos_incluidos - egresos_incluidos
        resultado_pct = (resultado / facturacion * 100) if facturacion else 0.0

        actividad_mensual = self._actividad_mensual(
            desde,
            hasta,
            empresa,
        )
        caja_mensual = self._caja_mensual(desde, hasta)
        self._aplicar_conceptos_mensuales(actividad_mensual, desde, hasta)

        top_clientes = self._top_clientes(ventas_filters, facturacion)
        freshness = self._freshness()
        warnings = self._warnings(
            hasta=hasta,
            freshness=freshness,
            conflictos=conflictos,
            pendientes=conceptos_pendientes,
            empresa=empresa,
        )

        return {
            "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
            "empresa": empresa,
            "kpis": {
                "facturacion": facturacion,
                "compras": compras,
                "diferencia_facturacion_compras": diferencia,
                "ingresos_incluidos": ingresos_incluidos,
                "egresos_incluidos": egresos_incluidos,
                "resultado_gestion": resultado,
                "resultado_sobre_facturacion_pct": resultado_pct,
                "ingresos_caja": ingresos_caja,
                "egresos_caja": egresos_caja,
                "caja_neta": ingresos_caja - egresos_caja,
                "movimientos_caja": int(getattr(caja_row, "cantidad", 0) or 0),
            },
            "series": {
                "actividad_mensual": list(actividad_mensual.values()),
                "caja_mensual": list(caja_mensual.values()),
            },
            "conceptos": {
                "desglose": desglose,
                "conflictos": conflictos,
                "pendientes": conceptos_pendientes,
            },
            "clientes": top_clientes,
            "meta": {
                "method": self.METODO,
                "method_label": "Facturación − Compras + Ingresos incluidos − Egresos incluidos",
                "accounting_profit": False,
                "treasury_scope": "global",
                "freshness": freshness,
                "warnings": warnings,
            },
        }

    def _actividad_mensual(self, desde, hasta, empresa):
        result = defaultdict(
            lambda: {
                "periodo": None,
                "facturacion": 0.0,
                "compras": 0.0,
                "diferencia": 0.0,
                "ingresos_incluidos": 0.0,
                "egresos_incluidos": 0.0,
                "resultado_gestion": 0.0,
            }
        )
        ventas = (
            db.session.query(
                extract("year", StgSabiogoVentas.fecha).label("y"),
                extract("month", StgSabiogoVentas.fecha).label("m"),
                func.sum(StgSabiogoVentas.subtot),
            )
            .filter(*self._ventas_filters(desde, hasta, empresa))
            .group_by("y", "m")
            .all()
        )
        compras = (
            db.session.query(
                extract("year", StgSabiogoCompras.fecha).label("y"),
                extract("month", StgSabiogoCompras.fecha).label("m"),
                func.sum(StgSabiogoCompras.subtot),
            )
            .filter(*self._compras_filters(desde, hasta, empresa))
            .group_by("y", "m")
            .all()
        )
        for y, m, total in ventas:
            key = f"{int(y):04d}-{int(m):02d}"
            result[key]["periodo"] = f"{key}-01"
            result[key]["facturacion"] = _float(total)
        for y, m, total in compras:
            key = f"{int(y):04d}-{int(m):02d}"
            result[key]["periodo"] = f"{key}-01"
            result[key]["compras"] = _float(total)
        return dict(sorted(result.items()))

    def _aplicar_conceptos_mensuales(self, actividad, desde, hasta):
        rows = (
            db.session.query(
                extract("year", MovimientoCaja.fecha_hora).label("y"),
                extract("month", MovimientoCaja.fecha_hora).label("m"),
                MovimientoCaja.tipo,
                func.sum(MovimientoCaja.monto),
            )
            .join(CategoriaGasto, CategoriaGasto.id == MovimientoCaja.categoria_gasto_id)
            .filter(
                *self._movimientos_filters(desde, hasta),
                CategoriaGasto.incluye_resultado.is_(True),
                CategoriaGasto.naturaleza.isnot(None),
                self._compatible_expr(),
            )
            .group_by("y", "m", MovimientoCaja.tipo)
            .all()
        )
        for y, m, tipo, total in rows:
            key = f"{int(y):04d}-{int(m):02d}"
            if key not in actividad:
                actividad[key] = {
                    "periodo": f"{key}-01",
                    "facturacion": 0.0,
                    "compras": 0.0,
                    "diferencia": 0.0,
                    "ingresos_incluidos": 0.0,
                    "egresos_incluidos": 0.0,
                    "resultado_gestion": 0.0,
                }
            target = "ingresos_incluidos" if tipo == "ingreso" else "egresos_incluidos"
            actividad[key][target] += _float(total)

        for item in actividad.values():
            item["diferencia"] = item["facturacion"] - item["compras"]
            item["resultado_gestion"] = (
                item["diferencia"]
                + item["ingresos_incluidos"]
                - item["egresos_incluidos"]
            )
        ordered = dict(sorted(actividad.items()))
        actividad.clear()
        actividad.update(ordered)

    def _caja_mensual(self, desde, hasta):
        result = defaultdict(
            lambda: {
                "periodo": None,
                "ingresos": 0.0,
                "egresos": 0.0,
                "neto": 0.0,
            }
        )
        rows = (
            db.session.query(
                extract("year", MovimientoCaja.fecha_hora).label("y"),
                extract("month", MovimientoCaja.fecha_hora).label("m"),
                MovimientoCaja.tipo,
                func.sum(MovimientoCaja.monto),
            )
            .filter(*self._movimientos_filters(desde, hasta))
            .group_by("y", "m", MovimientoCaja.tipo)
            .all()
        )
        for y, m, tipo, total in rows:
            key = f"{int(y):04d}-{int(m):02d}"
            result[key]["periodo"] = f"{key}-01"
            result[key]["ingresos" if tipo == "ingreso" else "egresos"] += _float(total)
        for item in result.values():
            item["neto"] = item["ingresos"] - item["egresos"]
        return dict(sorted(result.items()))

    @staticmethod
    def _top_clientes(ventas_filters, total_facturacion):
        rows = (
            db.session.query(
                StgSabiogoVentas.cliente,
                func.sum(StgSabiogoVentas.subtot).label("monto"),
            )
            .filter(*ventas_filters)
            .group_by(StgSabiogoVentas.cliente)
            .order_by(func.sum(StgSabiogoVentas.subtot).desc())
            .limit(5)
            .all()
        )
        clientes = [
            {
                "cliente": cliente or "(sin cliente)",
                "monto": _float(monto),
                "participacion_pct": (
                    _float(monto) / total_facturacion * 100 if total_facturacion else 0.0
                ),
            }
            for cliente, monto in rows
        ]
        return {
            "top": clientes,
            "top_1_pct": clientes[0]["participacion_pct"] if clientes else 0.0,
            "top_5_pct": sum(item["participacion_pct"] for item in clientes),
        }

    @staticmethod
    def _freshness():
        def iso(value):
            return value.isoformat() if value else None

        return {
            "ventas": iso(db.session.query(func.max(StgSabiogoVentas.fecha)).scalar()),
            "compras": iso(db.session.query(func.max(StgSabiogoCompras.fecha)).scalar()),
            "tesoreria": iso(
                db.session.query(func.max(MovimientoCaja.fecha_hora))
                .filter(MovimientoCaja.estado != "anulado")
                .scalar()
            ),
        }

    @staticmethod
    def _warnings(*, hasta, freshness, conflictos, pendientes, empresa):
        warnings = []
        for source, value in freshness.items():
            if not value:
                warnings.append(
                    {
                        "code": f"{source}_sin_datos",
                        "severity": "warning",
                        "message": f"{source.capitalize()} no tiene datos cargados.",
                    }
                )
                continue
            source_date = date.fromisoformat(value[:10])
            if source_date < hasta:
                warnings.append(
                    {
                        "code": f"{source}_corte_parcial",
                        "severity": "warning",
                        "message": (
                            f"{source.capitalize()} tiene datos hasta "
                            f"{source_date.strftime('%d/%m/%Y')}."
                        ),
                    }
                )
        if conflictos:
            warnings.append(
                {
                    "code": "movimientos_incompatibles",
                    "severity": "danger",
                    "message": f"{conflictos} movimientos contradicen la naturaleza de su concepto.",
                }
            )
        if pendientes:
            warnings.append(
                {
                    "code": "conceptos_pendientes",
                    "severity": "warning",
                    "message": f"{pendientes} conceptos activos todavía no tienen naturaleza.",
                }
            )
        if empresa not in ("", "TODAS"):
            warnings.append(
                {
                    "code": "tesoreria_global",
                    "severity": "info",
                    "message": (
                        "Los conceptos de Tesorería son globales y no se distribuyen por empresa."
                    ),
                }
            )
        return warnings
