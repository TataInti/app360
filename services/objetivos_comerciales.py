"""Metas comerciales mensuales con realizado calculado desde PRE al consultar."""

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from models import db
from models.comercial import ComercialObjetivo, ComercialVendedor
from models.time_utils import today_local_date
from services.comercial_pre import calcular_resumen_pre


EMPRESAS_COMERCIALES = ("CARNES", "LACTEOS")
MEDIDAS_COMERCIALES = {
    "importe": "importe_pre",
    "cajas": "cajas",
    "kilos": "kilos",
}
NOTA_RITMO = "El avance esperado es una referencia lineal, no un pronóstico."


def validar_mes(mes: str) -> date:
    """Valida YYYY-MM y devuelve el primer día del mes."""
    if not isinstance(mes, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        raise ValueError("mes debe tener formato YYYY-MM")
    try:
        return date.fromisoformat(f"{mes}-01")
    except ValueError as exc:
        raise ValueError("mes debe tener formato YYYY-MM") from exc


def decimal_positivo(valor) -> Decimal:
    if isinstance(valor, bool) or valor is None:
        raise ValueError("meta debe ser un número positivo")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("meta debe ser un número positivo") from exc
    if not numero.is_finite() or numero <= 0:
        raise ValueError("meta debe ser un número positivo")
    return numero


def _decimal(valor) -> Decimal:
    if valor is None:
        return Decimal("0")
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _periodo(mes: str) -> tuple[date, date]:
    desde = validar_mes(mes)
    hasta = date(desde.year, desde.month, monthrange(desde.year, desde.month)[1])
    return desde, hasta


def _avance_esperado(desde: date, hasta: date, corte: date) -> float:
    if corte < desde:
        return 0.0
    if corte >= hasta:
        return 1.0
    dias_del_mes = (hasta - desde).days + 1
    return (corte.day) / dias_del_mes


def _evaluar_estado(desde, hasta, corte, realizado, meta, avance_esperado):
    cumplimiento = realizado / meta
    if corte < desde:
        estado = "No iniciado"
    elif realizado >= meta:
        estado = "Cumplido"
    elif corte < hasta:
        estado = (
            "Por debajo del ritmo esperado"
            if cumplimiento < Decimal(str(avance_esperado))
            else "En ritmo"
        )
    else:
        estado = "No cumplido"
    faltante = max(meta - realizado, Decimal("0"))
    return cumplimiento, faltante, cumplimiento - Decimal(str(avance_esperado)), estado


def _obtener_realizado(desde, hasta, empresa, vendedor, medida, corte, criterio_clientes=False):
    if corte < desde:
        return Decimal("0")
    fecha_hasta = min(corte, hasta)
    resumen = calcular_resumen_pre(
        desde,
        fecha_hasta,
        empresa=empresa,
        vendedor=vendedor,
        limite=1,
        criterio_clientes=criterio_clientes,
    )
    return _decimal(resumen[MEDIDAS_COMERCIALES[medida]])


def _base_item(vendedor, mes, empresa, medida, avance_esperado):
    return {
        "vendedor_id": vendedor.id,
        "vendedor": vendedor.nombre_visible,
        "nombre_visible": vendedor.nombre_visible,
        "vendedor_activo": getattr(vendedor, "activo", True),
        "empresa": empresa,
        "mes": mes,
        "medida": medida,
        "avance_esperado": avance_esperado,
        "nota_ritmo": NOTA_RITMO,
    }


def _item_individual(vendedor, mes, empresa, medida, meta_obj, realizado, desde, hasta, corte):
    avance_esperado = _avance_esperado(desde, hasta, corte)
    item = _base_item(vendedor, mes, empresa, medida, avance_esperado)
    item["id"] = meta_obj.id if meta_obj is not None else None
    item["realizado"] = float(realizado)

    if meta_obj is None:
        item.update(
            {
                "meta": None,
                "descripcion": None,
                "cumplimiento": None,
                "faltante": None,
                "desvio": None,
                "estado": "Sin meta",
                "cobertura": "sin_meta",
            }
        )
        return item

    meta = _decimal(meta_obj.meta)
    cumplimiento, faltante, desvio, estado = _evaluar_estado(
        desde,
        hasta,
        corte,
        realizado,
        meta,
        avance_esperado,
    )
    item.update(
        {
            "meta": float(meta),
            "descripcion": meta_obj.descripcion,
            "cumplimiento": float(cumplimiento),
            "faltante": float(faltante),
            "desvio": float(desvio),
            "estado": estado,
            "cobertura": "completa",
        }
    )
    return item


def _item_todas(vendedor, mes, medida, metas, realizados, desde, hasta, corte):
    avance_esperado = _avance_esperado(desde, hasta, corte)
    meta_total = sum((_decimal(meta.meta) for meta in metas.values()), Decimal("0"))
    realizado_total = sum(realizados.values(), Decimal("0"))
    detalle = [
        _item_individual(
            vendedor,
            mes,
            empresa,
            medida,
            metas.get(empresa),
            realizados[empresa],
            desde,
            hasta,
            corte,
        )
        for empresa in EMPRESAS_COMERCIALES
    ]
    item = _base_item(vendedor, mes, "TODAS", medida, avance_esperado)
    item["realizado"] = float(realizado_total)
    item["detalle_empresas"] = detalle

    if not metas:
        item.update(
            {
                "meta": None,
                "descripcion": None,
                "cumplimiento": None,
                "faltante": None,
                "desvio": None,
                "estado": "Sin meta",
                "cobertura": "sin_meta",
            }
        )
        return item

    item["meta"] = float(meta_total)
    item["descripcion"] = None
    if len(metas) < len(EMPRESAS_COMERCIALES):
        item.update(
            {
                "cumplimiento": None,
                "faltante": None,
                "desvio": None,
                "estado": "No iniciado" if corte < desde else "Cobertura incompleta",
                "cobertura": "incompleta",
            }
        )
        return item

    cumplimiento, faltante, desvio, estado = _evaluar_estado(
        desde,
        hasta,
        corte,
        realizado_total,
        meta_total,
        avance_esperado,
    )
    item.update(
        {
            "cumplimiento": float(cumplimiento),
            "faltante": float(faltante),
            "desvio": float(desvio),
            "estado": estado,
            "cobertura": "completa",
        }
    )
    return item


def obtener_objetivos_comerciales(
    mes: str,
    empresa: str = "TODAS",
    medida: str = "importe",
    corte: date | None = None,
    criterio_clientes: bool = False,
    incluir_vendedores_venta: bool = False,
) -> list[dict]:
    """Lista objetivos y vendedores sin meta; calcula realizados desde staging."""
    desde, hasta = _periodo(mes)
    empresa = (empresa or "TODAS").strip().upper()
    medida = (medida or "").strip().lower()
    if empresa not in ("TODAS", *EMPRESAS_COMERCIALES):
        raise ValueError("empresa debe ser TODAS, CARNES o LACTEOS")
    if medida not in MEDIDAS_COMERCIALES:
        raise ValueError("medida debe ser importe, cajas o kilos")
    corte = corte or today_local_date()

    consulta_metas = ComercialObjetivo.query.filter_by(mes=mes, medida=medida)
    if empresa != "TODAS":
        consulta_metas = consulta_metas.filter_by(empresa=empresa)
    metas = consulta_metas.all()

    vendedores = {
        vendedor.id: vendedor
        for vendedor in ComercialVendedor.query.all()
    }
    for meta in metas:
        vendedores.setdefault(meta.vendedor_id, meta.vendedor)
    vendedores_temporales = {}

    # Include sellers visible in the same PRE/FAC source used by the strategic
    # sales panel, even before they have a row in the commercial catalog.
    if incluir_vendedores_venta and corte >= desde:
        resumen_ventas = calcular_resumen_pre(
            desde,
            min(corte, hasta),
            empresa=empresa,
            limite=100000,
            criterio_clientes=criterio_clientes,
        )
        nombres_catalogo = {
            " ".join(vendedor.nombre_visible.split()).casefold()
            for vendedor in vendedores.values()
        }
        for fila in resumen_ventas["por_vendedor"]:
            nombre = " ".join((fila.get("nombre") or "").split())
            if not nombre or nombre.casefold() == "sin vendedor":
                continue
            clave = nombre.casefold()
            if clave not in nombres_catalogo:
                vendedores_temporales[clave] = SimpleNamespace(id=None, nombre_visible=nombre)
                nombres_catalogo.add(clave)

    metas_por_vendedor = {}
    for meta in metas:
        metas_por_vendedor.setdefault(meta.vendedor_id, {})[meta.empresa] = meta

    empresas_a_calcular = EMPRESAS_COMERCIALES if empresa == "TODAS" else (empresa,)
    resultado = []
    vendedores_para_listar = [*vendedores.values(), *vendedores_temporales.values()]
    for vendedor in sorted(vendedores_para_listar, key=lambda item: item.nombre_visible.casefold()):
        realizados = {
            empresa_actual: _obtener_realizado(
                desde,
                hasta,
                empresa_actual,
                vendedor.nombre_visible,
                medida,
                corte,
                criterio_clientes,
            )
            for empresa_actual in empresas_a_calcular
        }
        metas_vendedor = metas_por_vendedor.get(vendedor.id, {})
        if empresa == "TODAS":
            resultado.append(
                _item_todas(
                    vendedor,
                    mes,
                    medida,
                    metas_vendedor,
                    realizados,
                    desde,
                    hasta,
                    corte,
                )
            )
        else:
            resultado.append(
                _item_individual(
                    vendedor,
                    mes,
                    empresa,
                    medida,
                    metas_vendedor.get(empresa),
                    realizados[empresa],
                    desde,
                    hasta,
                    corte,
                )
            )
    return resultado
