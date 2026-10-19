"""Cálculo compartido para Ejecutivo y Resultado comercial.

La métrica es deliberadamente un indicador de gestión:
facturación sin PRE - compras + conceptos de ingreso - conceptos de egreso.
No representa costo de mercadería vendida ni utilidad contable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy import and_, case, extract, func, or_

from models import (
    Adelanto,
    CategoriaGasto,
    LiquidacionSueldo,
    MovimientoCaja,
    StgSabiogoCompras,
    StgSabiogoVentas,
    db,
)
from models.empresa import EMPRESA_TODAS, empresa_es_especifica, normalizar_empresa


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
    def _movimientos_filters(
        desde: date,
        hasta: date,
        empresa: str = EMPRESA_TODAS,
    ):
        filters = [
            MovimientoCaja.fecha_hora >= datetime.combine(desde, time.min),
            MovimientoCaja.fecha_hora <= datetime.combine(hasta, time.max),
            MovimientoCaja.estado != "anulado",
        ]
        if empresa_es_especifica(empresa):
            # El NULL histórico queda exclusivamente dentro de TODAS.
            # Los checks y la normalización de altas garantizan los códigos
            # canónicos; la igualdad directa permite aprovechar el índice
            # compuesto (empresa, fecha_hora).
            filters.append(MovimientoCaja.empresa == empresa)
        return filters

    @staticmethod
    def _liquidaciones_filters(
        desde: date,
        hasta: date,
        empresa: str = EMPRESA_TODAS,
    ):
        filters = [
            LiquidacionSueldo.fecha_liquidacion >= datetime.combine(desde, time.min),
            LiquidacionSueldo.fecha_liquidacion <= datetime.combine(hasta, time.max),
        ]
        if empresa_es_especifica(empresa):
            filters.append(LiquidacionSueldo.empresa == empresa)
        return filters

    @staticmethod
    def _adelantos_pagados_filters(
        desde: date,
        hasta: date,
        empresa: str = EMPRESA_TODAS,
    ):
        filters = [
            Adelanto.aprobado.is_(True),
            Adelanto.pagado.is_(True),
            Adelanto.tipo.in_(("adelanto_efectivo", "adelanto_mercaderia")),
            Adelanto.fecha_pago >= datetime.combine(desde, time.min),
            Adelanto.fecha_pago <= datetime.combine(hasta, time.max),
        ]
        if empresa_es_especifica(empresa):
            filters.append(Adelanto.empresa == empresa)
        return filters

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
        empresa = normalizar_empresa(
            empresa,
            allow_todas=True,
            allow_none=True,
        ) or EMPRESA_TODAS
        ventas_filters = self._ventas_filters(desde, hasta, empresa)
        compras_filters = self._compras_filters(desde, hasta, empresa)
        movimientos_filters = self._movimientos_filters(desde, hasta, empresa)

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

        conceptos_configurados = (
            CategoriaGasto.query
            .filter(
                CategoriaGasto.incluye_resultado.is_(True),
                CategoriaGasto.naturaleza.isnot(None),
            )
            .order_by(CategoriaGasto.nombre)
            .all()
        )
        participantes_por_id = {
            int(concepto.id): {
                "concepto_id": int(concepto.id),
                "concepto": concepto.nombre,
                "naturaleza": concepto.naturaleza,
                "activo": bool(concepto.activo),
                "efecto": concepto.efecto_resultado,
                "suma": {"cantidad": 0, "monto": 0.0},
                "resta": {"cantidad": 0, "monto": 0.0},
            }
            for concepto in conceptos_configurados
        }

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
            participante = participantes_por_id.get(int(row.id))
            if participante:
                participante[efecto] = {
                    "cantidad": int(row.cantidad or 0),
                    "monto": monto,
                }

        participantes = list(participantes_por_id.values())

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
        sueldos_pagados = self._sueldos_pagados(
            desde,
            hasta,
            diferencia,
            empresa,
        )

        actividad_mensual = self._actividad_mensual(
            desde,
            hasta,
            empresa,
        )
        caja_mensual = self._caja_mensual(desde, hasta, empresa)
        self._aplicar_conceptos_mensuales(
            actividad_mensual,
            desde,
            hasta,
            empresa,
        )

        top_clientes = self._top_clientes(ventas_filters, facturacion)
        analisis_financiero = self._analisis_financiero(
            desde=desde,
            hasta=hasta,
            kpis={
                "facturacion": facturacion,
                "compras": compras,
                "ingresos_incluidos": ingresos_incluidos,
                "egresos_incluidos": egresos_incluidos,
                "resultado_gestion": resultado,
                "ingresos_caja": ingresos_caja,
                "egresos_caja": egresos_caja,
                "caja_neta": ingresos_caja - egresos_caja,
            },
            actividad_mensual=actividad_mensual,
            caja_mensual=caja_mensual,
            participantes=participantes,
            clientes=top_clientes,
        )
        freshness = self._freshness(empresa)
        empresa_scope = self._empresa_scope(desde, hasta, empresa)

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
            "analisis_financiero": analisis_financiero,
            "sueldos_pagados": sueldos_pagados,
            "conceptos": {
                "desglose": desglose,
                "participantes": participantes,
                "conflictos": conflictos,
                "pendientes": conceptos_pendientes,
            },
            "clientes": top_clientes,
            "meta": {
                "method": self.METODO,
                "method_label": "Facturación − Compras + Ingresos incluidos − Egresos incluidos",
                "accounting_profit": False,
                # Se conserva la clave previa, pero ahora expresa si Tesorería
                # comparte el alcance de empresa del resto del indicador.
                "treasury_scope": (
                    "company_filtered"
                    if empresa_es_especifica(empresa)
                    else "global"
                ),
                "empresa_scope": empresa_scope,
                "freshness": freshness,
                "data_quality": {
                    "movimientos_incompatibles": conflictos,
                    "conceptos_pendientes": conceptos_pendientes,
                },
                # Los cortes y pendientes son metadatos, no errores operativos.
                # Los consumidores reservan este canal para fallos accionables.
                "warnings": [],
            },
        }

    def _sueldos_pagados(
        self,
        desde: date,
        hasta: date,
        margen_comercial: float,
        empresa: str = EMPRESA_TODAS,
    ) -> dict:
        """Resume los pagos de personal sin alterar el resultado de gestión.

        Tesorería se toma por su categoría SUELDOS y los movimientos anulados
        quedan afuera. En RRHH se consideran las liquidaciones emitidas y los
        adelantos de sueldo efectivamente entregados; los préstamos no son una
        remuneración y por eso no integran esta lectura.
        """
        tesoreria = (
            db.session.query(
                func.sum(MovimientoCaja.monto).label("monto"),
                func.count(MovimientoCaja.id).label("cantidad"),
            )
            .join(CategoriaGasto, CategoriaGasto.id == MovimientoCaja.categoria_gasto_id)
            .filter(
                *self._movimientos_filters(desde, hasta, empresa),
                MovimientoCaja.tipo == "egreso",
                func.upper(func.trim(CategoriaGasto.nombre)) == "SUELDOS",
            )
            .first()
        )
        liquidaciones = (
            db.session.query(
                func.sum(LiquidacionSueldo.sueldo_neto).label("monto"),
                func.count(LiquidacionSueldo.id).label("cantidad"),
            )
            .filter(*self._liquidaciones_filters(desde, hasta, empresa))
            .first()
        )
        adelantos = (
            db.session.query(
                func.sum(Adelanto.monto).label("monto"),
                func.count(Adelanto.id).label("cantidad"),
            )
            .filter(*self._adelantos_pagados_filters(desde, hasta, empresa))
            .first()
        )

        tesoreria_monto = _float(getattr(tesoreria, "monto", 0))
        liquidaciones_monto = _float(getattr(liquidaciones, "monto", 0))
        adelantos_monto = _float(getattr(adelantos, "monto", 0))
        total = tesoreria_monto + liquidaciones_monto + adelantos_monto
        return {
            "tesoreria_sueldos": {
                "monto": tesoreria_monto,
                "cantidad": int(getattr(tesoreria, "cantidad", 0) or 0),
            },
            "liquidaciones_rrhh": {
                "monto": liquidaciones_monto,
                "cantidad": int(getattr(liquidaciones, "cantidad", 0) or 0),
            },
            "adelantos_rrhh": {
                "monto": adelantos_monto,
                "cantidad": int(getattr(adelantos, "cantidad", 0) or 0),
            },
            "total": total,
            "margen_comercial": margen_comercial,
            "margen_despues_sueldos_pagados": margen_comercial - total,
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

    def _aplicar_conceptos_mensuales(self, actividad, desde, hasta, empresa):
        rows = (
            db.session.query(
                extract("year", MovimientoCaja.fecha_hora).label("y"),
                extract("month", MovimientoCaja.fecha_hora).label("m"),
                MovimientoCaja.tipo,
                func.sum(MovimientoCaja.monto),
            )
            .join(CategoriaGasto, CategoriaGasto.id == MovimientoCaja.categoria_gasto_id)
            .filter(
                *self._movimientos_filters(desde, hasta, empresa),
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

    def _caja_mensual(self, desde, hasta, empresa):
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
            .filter(*self._movimientos_filters(desde, hasta, empresa))
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
    def _month_keys(desde, hasta):
        """Devuelve todos los meses calendario del período, incluidos los vacíos."""
        keys = []
        year, month = desde.year, desde.month
        while (year, month) <= (hasta.year, hasta.month):
            keys.append(f"{year:04d}-{month:02d}")
            month += 1
            if month == 13:
                year += 1
                month = 1
        return keys

    @staticmethod
    def _pct(numerator, denominator):
        if not denominator:
            return None
        return round(float(numerator) / float(denominator) * 100, 1)

    @staticmethod
    def _money_text(value):
        return f"{float(value):,.0f}".replace(",", ".")

    def _analisis_financiero(
        self,
        *,
        desde,
        hasta,
        kpis,
        actividad_mensual,
        caja_mensual,
        participantes,
        clientes,
    ):
        """Genera lecturas de gestión para orientar la revisión del período."""
        month_keys = self._month_keys(desde, hasta)
        actividad_por_mes = {
            key: value for key, value in actividad_mensual.items()
        }
        caja_por_mes = {key: value for key, value in caja_mensual.items()}
        flujo_mensual = []
        for key in month_keys:
            actividad = actividad_por_mes.get(key, {})
            caja = caja_por_mes.get(key, {})
            ingresos = _float(caja.get("ingresos"))
            egresos = _float(caja.get("egresos"))
            flujo_mensual.append(
                {
                    "periodo": f"{key}-01",
                    "ingresos": ingresos,
                    "egresos": egresos,
                    "neto": ingresos - egresos,
                    "resultado_gestion": _float(actividad.get("resultado_gestion")),
                }
            )

        flujo_neto = _float(kpis["caja_neta"])
        resultado = _float(kpis["resultado_gestion"])
        ingresos_caja = _float(kpis["ingresos_caja"])
        egresos_caja = _float(kpis["egresos_caja"])
        ingresos_incluidos = _float(kpis["ingresos_incluidos"])
        egresos_incluidos = _float(kpis["egresos_incluidos"])
        brecha = flujo_neto - resultado
        cobertura = self._pct(ingresos_caja, egresos_caja)
        cobertura_incluidos = self._pct(ingresos_incluidos, egresos_incluidos)
        meses_positivos = sum(item["neto"] > 0 for item in flujo_mensual)
        meses_negativos = sum(item["neto"] < 0 for item in flujo_mensual)
        meses_sin_movimiento = sum(
            item["ingresos"] == 0 and item["egresos"] == 0
            for item in flujo_mensual
        )
        resultados_positivos = sum(
            item["resultado_gestion"] > 0 for item in flujo_mensual
        )
        resultados_negativos = sum(
            item["resultado_gestion"] < 0 for item in flujo_mensual
        )
        hay_movimientos_caja = any(
            item["ingresos"] != 0 or item["egresos"] != 0
            for item in flujo_mensual
        )

        insights = []

        def add(code, severity, title, message):
            insights.append(
                {
                    "code": code,
                    "severity": severity,
                    "title": title,
                    "message": message,
                }
            )

        if not hay_movimientos_caja:
            add(
                "sin_movimientos_caja",
                "info",
                "Sin movimientos de caja registrados",
                "No se registraron ingresos ni egresos en Tesorería para este período. Revisá si faltan cargar movimientos antes de usar esta lectura.",
            )
        elif flujo_neto < 0 and resultado >= 0:
            add(
                "resultado_sin_caja",
                "danger",
                "Resultado positivo, caja negativa",
                "El resultado del período da positivo, pero salió más dinero del que entró. Revisá cobranzas pendientes, pagos adelantados y fechas de registración.",
            )
        elif flujo_neto >= 0 and resultado < 0:
            add(
                "caja_sin_resultado",
                "warning",
                "Caja positiva, resultado negativo",
                "Entró más dinero del que salió, aunque el resultado del período da negativo. Revisá si ingresaron cobranzas de ventas anteriores o si las compras todavía no se reflejan en ventas.",
            )
        elif flujo_neto < 0:
            add(
                "flujo_negativo",
                "danger",
                "Caja del período en negativo",
                "Salió más dinero del que entró. Revisá los egresos más altos y las cobranzas pendientes del período.",
            )
        else:
            add(
                "flujo_positivo",
                "positive",
                "Caja del período a favor",
                "Entró más dinero del que salió. Revisá si esta mejora se sostiene en los próximos períodos.",
            )

        if cobertura is not None and cobertura < 100:
            add(
                "cobertura_insuficiente",
                "warning",
                "Ingresos por debajo de los pagos",
                f"Por cada $100 que salieron, ingresaron $ {cobertura:.1f}. Revisá pagos próximos y cobranzas pendientes.",
            )
        elif cobertura is not None:
            add(
                "cobertura_suficiente",
                "positive",
                "Ingresos que cubren los pagos",
                f"Por cada $100 que salieron, ingresaron $ {cobertura:.1f}. Los ingresos del período alcanzaron para cubrir los pagos registrados.",
            )

        if brecha and abs(brecha) > max(100000.0, abs(resultado) * 0.1):
            add(
                "brecha_caja_resultado",
                "info",
                "Diferencia caja–resultado",
                f"Entre caja y resultado hay una diferencia de $ {self._money_text(abs(brecha))}. Revisá movimientos cobrados o pagados en fechas distintas a la operación.",
            )

        top5 = _float(clientes.get("top_5_pct"))
        if top5 >= 60:
            add(
                "concentracion_clientes",
                "warning",
                "Concentración comercial elevada",
                f"Los cinco clientes principales concentran el {top5:.1f}% de la facturación. Revisá plazos de cobro y dependencia de esas cuentas.",
            )
        elif top5 >= 40:
            add(
                "concentracion_clientes",
                "info",
                "Concentración a monitorear",
                f"Los cinco clientes principales representan el {top5:.1f}% de la facturación. Conviene seguir sus plazos de cobro por separado.",
            )

        mayor_egreso = max(
            (
                participant
                for participant in participantes
                if _float(participant.get("resta", {}).get("monto")) > 0
            ),
            key=lambda item: _float(item["resta"]["monto"]),
            default=None,
        )
        if mayor_egreso:
            add(
                "principal_egreso_incluido",
                "info",
                "Concepto que más redujo el resultado",
                f"{mayor_egreso['concepto']} fue el concepto que más redujo el resultado: $ {self._money_text(mayor_egreso['resta']['monto'])}. Revisá su composición y evolución.",
            )

        if resultados_negativos >= 2 and resultados_negativos >= resultados_positivos:
            add(
                "tendencia_resultado",
                "warning",
                "Resultado débil en la mayoría de los meses",
                f"El resultado fue negativo en {resultados_negativos} de {len(flujo_mensual)} meses. Revisá si la facturación está alcanzando para absorber compras y egresos incluidos.",
            )
        elif meses_negativos >= 2 and meses_negativos >= meses_positivos:
            add(
                "tendencia_caja",
                "warning",
                "Caja negativa en varios meses",
                f"La caja dio negativa en {meses_negativos} de {len(flujo_mensual)} meses. Revisá en qué meses se concentraron pagos y cobranzas.",
            )

        severity_order = {"danger": 0, "warning": 1, "info": 2, "positive": 3}
        insights.sort(key=lambda item: severity_order.get(item["severity"], 9))

        return {
            "flujo_caja": {
                "ingresos": ingresos_caja,
                "egresos": egresos_caja,
                "neto": flujo_neto,
                "cobertura_egresos_pct": cobertura,
                "promedio_mensual_neto": flujo_neto / len(month_keys) if month_keys else 0.0,
                "meses_positivos": meses_positivos,
                "meses_negativos": meses_negativos,
                "meses_sin_movimiento": meses_sin_movimiento,
            },
            "relacion_resultado_caja": {
                "resultado_gestion": resultado,
                "caja_neta": flujo_neto,
                "brecha_caja_menos_resultado": brecha,
                "interpretacion": "referencial_no_conciliacion_contable",
            },
            "participacion_tesoreria": {
                "ingresos_incluidos_sobre_caja_pct": self._pct(ingresos_incluidos, ingresos_caja),
                "egresos_incluidos_sobre_caja_pct": self._pct(egresos_incluidos, egresos_caja),
                "cobertura_conceptos_incluidos_pct": cobertura_incluidos,
            },
            "tendencia": {
                "meses": len(month_keys),
                "meses_resultado_positivo": resultados_positivos,
                "meses_resultado_negativo": resultados_negativos,
                "meses_flujo_positivo": meses_positivos,
                "meses_flujo_negativo": meses_negativos,
                "flujo_mensual": flujo_mensual,
            },
            "insights": insights[:6],
        }

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

    def _empresa_scope(self, desde: date, hasta: date, empresa: str) -> dict:
        """Describe el alcance aplicado y el histórico no atribuible.

        Los conteos se limitan al período y a los mismos hechos de personal que
        componen ``sueldos_pagados``. Nunca se suman al filtro de una empresa:
        sirven para que la interfaz explique la cobertura de ese corte.
        """
        historical_unassigned = {
            "movimientos": int(
                db.session.query(func.count(MovimientoCaja.id))
                .filter(
                    *self._movimientos_filters(desde, hasta, EMPRESA_TODAS),
                    MovimientoCaja.empresa.is_(None),
                )
                .scalar()
                or 0
            ),
            "adelantos": int(
                db.session.query(func.count(Adelanto.id))
                .filter(
                    *self._adelantos_pagados_filters(
                        desde,
                        hasta,
                        EMPRESA_TODAS,
                    ),
                    Adelanto.empresa.is_(None),
                )
                .scalar()
                or 0
            ),
            "liquidaciones": int(
                db.session.query(func.count(LiquidacionSueldo.id))
                .filter(
                    *self._liquidaciones_filters(
                        desde,
                        hasta,
                        EMPRESA_TODAS,
                    ),
                    LiquidacionSueldo.empresa.is_(None),
                )
                .scalar()
                or 0
            ),
        }
        return {
            "selected": empresa,
            "is_specific": empresa_es_especifica(empresa),
            "historical_unassigned": historical_unassigned,
        }

    def _freshness(self, empresa: str = EMPRESA_TODAS):
        def iso(value):
            return value.isoformat() if value else None

        ventas = db.session.query(func.max(StgSabiogoVentas.fecha))
        compras = db.session.query(func.max(StgSabiogoCompras.fecha))
        tesoreria = db.session.query(func.max(MovimientoCaja.fecha_hora)).filter(
            MovimientoCaja.estado != "anulado"
        )
        if empresa_es_especifica(empresa):
            ventas = ventas.filter(
                func.upper(func.trim(StgSabiogoVentas.origen)) == empresa
            )
            compras = compras.filter(
                func.upper(func.trim(StgSabiogoCompras.origen)) == empresa
            )
            tesoreria = tesoreria.filter(
                MovimientoCaja.empresa == empresa
            )

        return {
            "ventas": iso(ventas.scalar()),
            "compras": iso(compras.scalar()),
            "tesoreria": iso(tesoreria.scalar()),
        }
