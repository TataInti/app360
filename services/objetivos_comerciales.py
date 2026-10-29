"""Objetivos comerciales por líneas; el realizado se lee de PRE al consultar."""

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from sqlalchemy import case, func

from models import db
from models.comercial import ComercialObjetivo, ComercialVendedor
from models.sabiogo.staging import StgSabiogoVentas
from models.time_utils import today_local_date
from services.comercial_pre import expresion_vendedor_resuelta
from services.vendedores_comerciales import resolver_nombre_vendedor


EMPRESAS_COMERCIALES = ("CARNES", "LACTEOS")
MEDIDAS_COMERCIALES = {
    "importe": "subtot",
    "cajas": "cajas",
    "kilos": "kilos",
}
DIMENSIONES_STAGING = {
    "empresa": "origen",
    "rubro": "rubro",
    "subrubro": "subrubro",
    "marca": "marca",
    "producto": "producto",
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
    numero = decimal_no_negativo(valor)
    if numero <= 0:
        raise ValueError("meta debe ser un número positivo")
    return numero


def decimal_no_negativo(valor) -> Decimal:
    if isinstance(valor, bool) or valor is None:
        raise ValueError("cada meta debe ser un número mayor o igual a cero")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("cada meta debe ser un número mayor o igual a cero") from exc
    if not numero.is_finite() or numero < 0:
        raise ValueError("cada meta debe ser un número mayor o igual a cero")
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


def normalizar_dimension(dimension_tipo, dimension_valor):
    tipo = str(dimension_tipo or "").strip().lower()
    if tipo not in DIMENSIONES_STAGING:
        raise ValueError("dimension_tipo debe ser empresa, rubro, subrubro, marca o producto")
    if not isinstance(dimension_valor, str) or not dimension_valor.strip():
        raise ValueError("Selecciona un valor del catálogo de staging")
    valor = dimension_valor.strip()
    if len(valor) > 255:
        raise ValueError("El valor de la dimensión no puede superar 255 caracteres")
    if tipo == "empresa":
        valor = valor.upper()
        if valor not in EMPRESAS_COMERCIALES:
            raise ValueError("empresa debe ser CARNES o LACTEOS")
    return tipo, valor


def dimension_existe_en_staging(dimension_tipo, dimension_valor) -> bool:
    tipo, valor = normalizar_dimension(dimension_tipo, dimension_valor)
    if tipo == "empresa":
        return True
    columna = getattr(StgSabiogoVentas, DIMENSIONES_STAGING[tipo])
    expression = func.trim(columna)
    return db.session.query(StgSabiogoVentas.id).filter(
        StgSabiogoVentas.estado == "procesado",
        columna.isnot(None),
        expression != "",
        expression == valor,
        func.upper(func.coalesce(StgSabiogoVentas.origen, "")).in_(EMPRESAS_COMERCIALES),
    ).first() is not None


def obtener_opciones_dimension(dimension_tipo, busqueda="", limite=100) -> list[dict]:
    tipo = str(dimension_tipo or "").strip().lower()
    if tipo not in DIMENSIONES_STAGING:
        raise ValueError("Selecciona empresa, rubro, subrubro, marca o producto")
    query = (busqueda or "").strip()
    if tipo == "empresa":
        values = [
            {"value": empresa, "supports_cajas": True, "supports_kilos": True}
            for empresa in EMPRESAS_COMERCIALES
            if not query or query.casefold() in empresa.casefold()
        ]
        return values[: max(1, min(int(limite), 100))]

    columna = getattr(StgSabiogoVentas, DIMENSIONES_STAGING[tipo])
    expression = func.trim(columna)
    consulta = db.session.query(expression.label("value")).filter(
        StgSabiogoVentas.estado == "procesado",
        columna.isnot(None),
        expression != "",
    )
    if tipo != "empresa":
        consulta = consulta.filter(
            func.upper(func.coalesce(StgSabiogoVentas.origen, "")).in_(EMPRESAS_COMERCIALES)
        )
    if query:
        consulta = consulta.filter(expression.ilike(f"%{query}%"))
    values = [row.value for row in consulta.distinct().order_by(expression).limit(max(1, min(int(limite), 100))).all()]
    result = [{"value": value, "supports_cajas": True, "supports_kilos": True} for value in values]
    if tipo == "producto" and result:
        productos = [item["value"] for item in result]
        rows = (
            db.session.query(
                expression.label("value"),
                func.max(case((func.coalesce(StgSabiogoVentas.cajas, 0) != 0, 1), else_=0)).label("cajas"),
                func.max(case((func.coalesce(StgSabiogoVentas.kilos, 0) != 0, 1), else_=0)).label("kilos"),
            )
            .filter(
                StgSabiogoVentas.estado == "procesado",
                expression.in_(productos),
                func.upper(func.coalesce(StgSabiogoVentas.origen, "")).in_(EMPRESAS_COMERCIALES),
            )
            .group_by(expression)
            .all()
        )
        capabilities = {row.value: (bool(row.cajas), bool(row.kilos)) for row in rows}
        for item in result:
            cajas, kilos = capabilities.get(item["value"], (False, False))
            item["supports_cajas"] = cajas
            item["supports_kilos"] = kilos
    return result


def obtener_opciones_vendedores(busqueda="") -> list[dict]:
    query = (busqueda or "").strip().casefold()
    vendedores = {}
    for vendedor in ComercialVendedor.query.filter_by(activo=True).order_by(
        ComercialVendedor.nombre_visible
    ):
        key = " ".join(vendedor.nombre_visible.split()).casefold()
        vendedores[key] = {
            "id": vendedor.id,
            "nombre_visible": vendedor.nombre_visible,
            "referencia": f"id:{vendedor.id}",
        }

    nombres_staging = (
        db.session.query(StgSabiogoVentas.vendedor)
        .filter(
            StgSabiogoVentas.estado == "procesado",
            StgSabiogoVentas.vendedor.isnot(None),
            func.trim(StgSabiogoVentas.vendedor) != "",
        )
        .distinct()
        .all()
    )
    for (nombre_origen,) in nombres_staging:
        nombre = " ".join(resolver_nombre_vendedor(nombre_origen).split())
        key = nombre.casefold()
        if nombre and key not in vendedores:
            vendedores[key] = {
                "id": None,
                "nombre_visible": nombre,
                "referencia": f"nombre:{nombre}",
            }
    return [
        item
        for item in sorted(vendedores.values(), key=lambda row: row["nombre_visible"].casefold())
        if not query or query in item["nombre_visible"].casefold()
    ]


def capacidades_producto(producto):
    expression = func.trim(StgSabiogoVentas.producto)
    row = (
        db.session.query(
            func.max(case((func.coalesce(StgSabiogoVentas.cajas, 0) != 0, 1), else_=0)).label("cajas"),
            func.max(case((func.coalesce(StgSabiogoVentas.kilos, 0) != 0, 1), else_=0)).label("kilos"),
        )
        .filter(
            StgSabiogoVentas.estado == "procesado",
            expression == producto,
            func.upper(func.coalesce(StgSabiogoVentas.origen, "")).in_(EMPRESAS_COMERCIALES),
        )
        .one()
    )
    return {"supports_cajas": bool(row.cajas), "supports_kilos": bool(row.kilos)}


def _avance_esperado(desde: date, hasta: date, corte: date) -> float:
    if corte < desde:
        return 0.0
    if corte >= hasta:
        return 1.0
    dias_del_mes = (hasta - desde).days + 1
    return corte.day / dias_del_mes


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


def _filtros_pre(desde, hasta, vendedor, vendedor_expression=None):
    nombre_vendedor = resolver_nombre_vendedor(vendedor)
    if vendedor_expression is None:
        vendedor_expression = expresion_vendedor_resuelta()
    return [
        StgSabiogoVentas.estado == "procesado",
        StgSabiogoVentas.fecha >= desde,
        StgSabiogoVentas.fecha <= hasta,
        func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
        vendedor_expression == nombre_vendedor,
    ]


def _sumas_pre(
    desde,
    hasta,
    vendedor,
    dimension_tipo=None,
    dimension_valor=None,
    vendedor_expression=None,
):
    if hasta < desde:
        return {"importe": Decimal("0"), "cajas": Decimal("0"), "kilos": Decimal("0")}
    filtros = _filtros_pre(desde, hasta, vendedor, vendedor_expression)
    if dimension_tipo:
        columna = getattr(StgSabiogoVentas, DIMENSIONES_STAGING[dimension_tipo])
        if dimension_tipo == "empresa":
            filtros.append(func.upper(func.trim(func.coalesce(columna, ""))) == dimension_valor)
        else:
            filtros.extend(
                (
                    columna.isnot(None),
                    func.trim(columna) == dimension_valor,
                    func.upper(func.coalesce(StgSabiogoVentas.origen, "")).in_(
                        EMPRESAS_COMERCIALES
                    ),
                )
            )
    row = (
        db.session.query(
            func.coalesce(func.sum(StgSabiogoVentas.subtot), 0).label("importe"),
            func.coalesce(func.sum(StgSabiogoVentas.cajas), 0).label("cajas"),
            func.coalesce(func.sum(StgSabiogoVentas.kilos), 0).label("kilos"),
        )
        .filter(*filtros)
        .one()
    )
    return {measure: _decimal(getattr(row, measure)) for measure in MEDIDAS_COMERCIALES}


def _serializar_linea(objetivo, realizados):
    metas = {
        "importe": _decimal(objetivo.meta_importe),
        "cajas": _decimal(objetivo.meta_cajas),
        "kilos": _decimal(objetivo.meta_kilos),
    }
    legacy_measure = objetivo.medida if objetivo.medida in MEDIDAS_COMERCIALES else None
    capacidades = (
        capacidades_producto(objetivo.dimension_valor)
        if objetivo.dimension_tipo == "producto"
        else {"supports_cajas": True, "supports_kilos": True}
    )
    return {
        "id": objetivo.id,
        "vendedor_id": objetivo.vendedor_id,
        "vendedor": objetivo.vendedor.nombre_visible,
        "nombre_visible": objetivo.vendedor.nombre_visible,
        "mes": objetivo.mes,
        "dimension_tipo": objetivo.dimension_tipo,
        "dimension_valor": objetivo.dimension_valor,
        "capacidades": capacidades,
        "metas": {measure: float(value) for measure, value in metas.items()},
        "realizados": {measure: float(value) for measure, value in realizados.items()},
        "meta_importe": float(metas["importe"]),
        "meta_cajas": float(metas["cajas"]),
        "meta_kilos": float(metas["kilos"]),
        "realizado_importe": float(realizados["importe"]),
        "realizado_cajas": float(realizados["cajas"]),
        "realizado_kilos": float(realizados["kilos"]),
        "descripcion": objetivo.descripcion,
        "empresa": objetivo.empresa,
        "medida": legacy_measure,
        "meta": float(objetivo.meta) if objetivo.meta is not None else None,
        "realizado": float(realizados[legacy_measure]) if legacy_measure else None,
    }


def _item_vendedor(vendedor, mes, medida, lineas, realizados_sin_lineas, desde, hasta, corte):
    avance_esperado = _avance_esperado(desde, hasta, corte)
    metas_total = {}
    realizados_total = {}
    for measure in MEDIDAS_COMERCIALES:
        selected_lines = [
            line
            for line in lineas
            if _decimal(line[f"meta_{measure}"]) > 0
        ]
        meta = sum((_decimal(line[f"meta_{measure}"]) for line in selected_lines), Decimal("0"))
        if selected_lines:
            realizado = sum(
                (_decimal(line[f"realizado_{measure}"]) for line in selected_lines),
                Decimal("0"),
            )
        elif lineas:
            realizado = sum(
                (_decimal(line[f"realizado_{measure}"]) for line in lineas),
                Decimal("0"),
            )
        else:
            realizado = realizados_sin_lineas[measure]
        metas_total[measure] = meta if meta > 0 else None
        realizados_total[measure] = realizado

    meta = metas_total[medida]
    realizado = realizados_total[medida]
    if meta is None:
        cumplimiento = faltante = desvio = None
        estado = "Sin meta"
        cobertura = "sin_meta"
    else:
        cumplimiento, faltante, desvio, estado = _evaluar_estado(
            desde, hasta, corte, realizado, meta, avance_esperado
        )
        cobertura = "completa"
    return {
        "vendedor_id": vendedor.id,
        "vendedor": vendedor.nombre_visible,
        "nombre_visible": vendedor.nombre_visible,
        "vendedor_activo": getattr(vendedor, "activo", True),
        "empresa": "TODAS",
        "mes": mes,
        "medida": medida,
        "lineas": lineas,
        "cantidad_lineas": len(lineas),
        "metas": {key: float(value) if value is not None else None for key, value in metas_total.items()},
        "realizados": {key: float(value) for key, value in realizados_total.items()},
        "meta_importe": float(metas_total["importe"]) if metas_total["importe"] is not None else None,
        "meta_cajas": float(metas_total["cajas"]) if metas_total["cajas"] is not None else None,
        "meta_kilos": float(metas_total["kilos"]) if metas_total["kilos"] is not None else None,
        "realizado_importe": float(realizados_total["importe"]),
        "realizado_cajas": float(realizados_total["cajas"]),
        "realizado_kilos": float(realizados_total["kilos"]),
        "meta": float(meta) if meta is not None else None,
        "realizado": float(realizado),
        "cumplimiento": float(cumplimiento) if cumplimiento is not None else None,
        "faltante": float(faltante) if faltante is not None else None,
        "desvio": float(desvio) if desvio is not None else None,
        "avance_esperado": avance_esperado,
        "nota_ritmo": NOTA_RITMO,
        "estado": estado,
        "cobertura": cobertura,
    }


def linea_objetivo_dict(objetivo, corte: date | None = None) -> dict:
    desde, hasta = _periodo(objetivo.mes)
    corte = corte or today_local_date()
    hasta_real = min(corte, hasta)
    vendedor_expression = expresion_vendedor_resuelta()
    realizados = _sumas_pre(
        desde,
        hasta_real,
        objetivo.vendedor.nombre_visible,
        objetivo.dimension_tipo,
        objetivo.dimension_valor,
        vendedor_expression,
    )
    return _serializar_linea(objetivo, realizados)


def obtener_objetivos_comerciales(
    mes: str,
    empresa: str = "TODAS",
    medida: str = "importe",
    corte: date | None = None,
    criterio_clientes: bool = False,
    incluir_vendedores_venta: bool = False,
) -> list[dict]:
    """Calcula metas y realizados agregando las líneas del vendedor sin promediar porcentajes."""
    desde, hasta = _periodo(mes)
    empresa = (empresa or "TODAS").strip().upper()
    medida = (medida or "").strip().lower()
    if empresa not in ("TODAS", *EMPRESAS_COMERCIALES):
        raise ValueError("empresa debe ser TODAS, CARNES o LACTEOS")
    if medida not in MEDIDAS_COMERCIALES:
        raise ValueError("medida debe ser importe, cajas o kilos")
    corte = corte or today_local_date()

    objetivos = ComercialObjetivo.query.filter_by(mes=mes).order_by(ComercialObjetivo.id).all()
    vendedores = {vendedor.id: vendedor for vendedor in ComercialVendedor.query.all()}
    for objetivo in objetivos:
        vendedores.setdefault(objetivo.vendedor_id, objetivo.vendedor)

    vendedores_temporales = {}
    if incluir_vendedores_venta and corte >= desde:
        filtros = [
            StgSabiogoVentas.estado == "procesado",
            StgSabiogoVentas.fecha >= desde,
            StgSabiogoVentas.fecha <= min(corte, hasta),
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
            StgSabiogoVentas.vendedor.isnot(None),
            func.trim(StgSabiogoVentas.vendedor) != "",
        ]
        nombres = db.session.query(StgSabiogoVentas.vendedor).filter(*filtros).distinct().all()
        claves = {" ".join(v.nombre_visible.split()).casefold() for v in vendedores.values()}
        for (nombre_origen,) in nombres:
            nombre = " ".join(resolver_nombre_vendedor(nombre_origen).split())
            clave = nombre.casefold()
            if nombre and clave not in claves:
                vendedores_temporales[clave] = SimpleNamespace(id=None, nombre_visible=nombre)
                claves.add(clave)

    objetivos_por_vendedor = {}
    for objetivo in objetivos:
        objetivos_por_vendedor.setdefault(objetivo.vendedor_id, []).append(objetivo)

    resultado = []
    vendedores_para_listar = [*vendedores.values(), *vendedores_temporales.values()]
    vendedor_expression = (
        expresion_vendedor_resuelta() if vendedores_para_listar else None
    )
    for vendedor in sorted(vendedores_para_listar, key=lambda item: item.nombre_visible.casefold()):
        lineas = []
        for objetivo in objetivos_por_vendedor.get(vendedor.id, []):
            actual = _sumas_pre(
                desde,
                min(corte, hasta),
                vendedor.nombre_visible,
                objetivo.dimension_tipo,
                objetivo.dimension_valor,
                vendedor_expression,
            )
            lineas.append(_serializar_linea(objetivo, actual))
        realizados_sin_lineas = _sumas_pre(
            desde,
            min(corte, hasta),
            vendedor.nombre_visible,
            vendedor_expression=vendedor_expression,
        )
        resultado.append(
            _item_vendedor(
                vendedor,
                mes,
                medida,
                lineas,
                realizados_sin_lineas,
                desde,
                hasta,
                corte,
            )
        )
    return resultado
