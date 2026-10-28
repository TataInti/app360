"""Análisis de performance de vendedores para el panel comercial.

Usa el mismo criterio PRE/FAC por cliente que el Panel de Ventas
(``filtro_comprobante_panel_ventas``). Cuando se elige un vendedor, el
análisis se recalcula sobre ese solo vendedor (series y mix), mientras la
comparación de objetivos mantiene el alcance de equipo como en el panel
estratégico.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func

from models import db
from models.sabiogo.staging import StgSabiogoVentas as Venta
from services.comercial_cartera import calcular_cartera_comercial
from services.comercial_criterios import filtro_comprobante_panel_ventas
from services.comercial_paneles import comparativo, periodo_anterior, ranking
from services.comercial_pre import (
    calcular_resumen_pre,
    expresion_vendedor_resuelta,
)
from services.objetivos_comerciales import (
    EMPRESAS_COMERCIALES,
    MEDIDAS_COMERCIALES,
    obtener_objetivos_comerciales,
)
from services.vendedores_comerciales import resolver_nombre_vendedor


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_date(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def _clave_semana(fecha: date) -> tuple[str, str]:
    ano, semana, _ = fecha.isocalendar()
    return f"{ano}-S{semana:02d}", f"Semana {semana:02d}"


def _clave_mes(fecha: date) -> tuple[str, str]:
    clave = f"{fecha.year:04d}-{fecha.month:02d}"
    return clave, f"{fecha.month:02d}/{fecha.year % 100:02d}"


def _series_por_dia(desde: date, hasta: date, *, empresa, vendedor) -> dict[date, dict]:
    """Acumula líneas de staging en una serie por día (importe/cajas/kilos)."""
    vendedor_expr = expresion_vendedor_resuelta()
    filtros = [
        Venta.estado == "procesado",
        Venta.fecha >= desde,
        Venta.fecha < hasta + timedelta(days=1),
        filtro_comprobante_panel_ventas(),
    ]
    if empresa and empresa != "TODAS":
        filtros.append(func.upper(func.coalesce(Venta.origen, "")) == empresa.upper())
    if vendedor:
        filtros.append(vendedor_expr == resolver_nombre_vendedor(vendedor))

    filas = (
        db.session.query(
            Venta.fecha.label("fecha"),
            func.sum(func.coalesce(Venta.subtot, 0)).label("importe"),
            func.sum(func.coalesce(Venta.cajas, 0)).label("cajas"),
            func.sum(func.coalesce(Venta.kilos, 0)).label("kilos"),
        )
        .filter(*filtros)
        .group_by(Venta.fecha)
        .all()
    )
    por_dia = {}
    for fila in filas:
        fecha = _as_date(fila.fecha)
        datos = por_dia.get(fecha, {"importe": 0.0, "cajas": 0.0, "kilos": 0.0})
        datos["importe"] += _float(fila.importe)
        datos["cajas"] += _float(fila.cajas)
        datos["kilos"] += _float(fila.kilos)
        por_dia[fecha] = datos
    return por_dia


def _etiqueta(clave: str, granularidad: str) -> str:
    if granularidad == "semana":
        return f"Semana {clave.split('-S')[-1]}"
    if granularidad == "mes":
        ano, mes = clave.split("-")
        return f"{mes}/{ano[2:]}"
    return clave


def _puntos(desde: date, hasta: date, por_dia: dict, granularidad: str) -> list[dict]:
    """Genera los puntos de la serie según granularidad, preservando el orden."""
    def tocar(f):
        if granularidad == "dia":
            clave = f.isoformat()
            return clave, f.isoformat()
        if granularidad == "semana":
            return _clave_semana(f)
        return _clave_mes(f)

    agrupada = {}
    orden = []
    cursor = desde
    while cursor <= hasta:
        clave, _ = tocar(cursor)
        if clave not in agrupada:
            agrupada[clave] = {"fecha": clave, "etiqueta": _etiqueta(clave, granularidad),
                               "importe": 0.0, "cajas": 0.0, "kilos": 0.0}
            orden.append(clave)
        if granularidad == "mes":
            # Avanza al primer día del mes siguiente (nunca retrocede).
            cursor = (
                date(cursor.year + 1, 1, 1)
                if cursor.month == 12
                else date(cursor.year, cursor.month + 1, 1)
            )
        else:
            cursor += timedelta(days=1)

    for inicio, datos in por_dia.items():
        clave, _ = tocar(inicio)
        bucket = agrupada.setdefault(
            clave, {"fecha": clave, "etiqueta": _etiqueta(clave, granularidad),
                    "importe": 0.0, "cajas": 0.0, "kilos": 0.0}
        )
        if clave not in orden:
            orden.append(clave)
        for medida in ("importe", "cajas", "kilos"):
            bucket[medida] += datos[medida]

    serie = [agrupada[clave] for clave in orden]
    for punto in serie:
        for medida in ("importe", "cajas", "kilos"):
            punto[medida] = round(punto[medida], 2)
    return serie


def _evolucion(desde, hasta, empresa, vendedor, granularidad):
    anterior_desde, anterior_hasta = periodo_anterior(desde, hasta)
    actual = _puntos(
        desde, hasta,
        _series_por_dia(desde, hasta, empresa=empresa, vendedor=vendedor),
        granularidad,
    )
    anterior = _puntos(
        anterior_desde, anterior_hasta,
        _series_por_dia(anterior_desde, anterior_hasta, empresa=empresa, vendedor=vendedor),
        granularidad,
    )
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "desde_anterior": anterior_desde.isoformat(),
        "hasta_anterior": anterior_hasta.isoformat(),
        "granularidad": granularidad,
        "actual": actual,
        "anterior": anterior,
    }


def _resumen(desde, hasta, *, empresa, vendedor, cliente, producto,
             criterio_clientes=True, limite=100000):
    return calcular_resumen_pre(
        desde, hasta, empresa=empresa, vendedor=vendedor, cliente=cliente, producto=producto,
        criterio_clientes=criterio_clientes, limite=limite,
    )


def performance_vendedores(
    desde: date,
    hasta: date,
    empresa: str = "TODAS",
    vendedor: str | None = None,
    cliente: str | None = None,
    producto: str | None = None,
    medida: str = "importe",
    granularidad: str = "dia",
) -> dict:
    """Devuelve todos los análisis de performance de vendedores del período."""
    if medida not in MEDIDAS_COMERCIALES:
        raise ValueError("medida debe ser importe, cajas o kilos")
    if granularidad not in {"dia", "semana", "mes"}:
        raise ValueError("granularidad debe ser dia, semana o mes")
    if isinstance(desde, datetime):
        desde = desde.date()
    if isinstance(hasta, datetime):
        hasta = hasta.date()

    vendedor_objetivo = resolver_nombre_vendedor(vendedor) if vendedor else None

    # Resumen y cartera del alcance seleccionado (recalculan al filtrar vendedor).
    resumen = _resumen(desde, hasta, empresa=empresa, vendedor=vendedor, cliente=cliente, producto=producto)
    cartera = calcular_cartera_comercial(
        desde, hasta, empresa=empresa, vendedor=vendedor, cliente=cliente, producto=producto,
        criterio_clientes=True,
    )
    anterior_desde, anterior_hasta = periodo_anterior(desde, hasta)
    resumen_anterior = _resumen(
        anterior_desde, anterior_hasta, empresa=empresa, vendedor=vendedor, cliente=cliente, producto=producto
    )

    # KPIs con comparación contra el período anterior.
    kpis = {
        "importe": comparativo(resumen["importe_pre"], resumen_anterior["importe_pre"]),
        "cajas": comparativo(resumen["cajas"], resumen_anterior["cajas"]),
        "kilos": comparativo(resumen["kilos"], resumen_anterior["kilos"]),
        "clientes": comparativo(
            resumen["clientes_compradores"], resumen_anterior["clientes_compradores"]
        ),
    }

    evolucion = _evolucion(desde, hasta, empresa, vendedor, granularidad)

    # Objetivos del mes del corte (realizado desde PRE); la UI solo los muestra si hay metas.
    mes = hasta.strftime("%Y-%m")
    objetivos = obtener_objetivos_comerciales(
        mes, empresa=empresa, medida=medida, corte=hasta, criterio_clientes=True
    )
    if vendedor_objetivo:
        objetivos = [o for o in objetivos if o["nombre_visible"] == vendedor_objetivo]
    tienen_meta = any(o.get("meta") is not None for o in objetivos)

    # Composición (vendedor/producto/cliente) y ranking con "Otros".
    composicion = {k: ranking(resumen["por_" + k]) for k in ("vendedor", "producto", "cliente")}

    # Tabla por vendedor con ticket, participación y cartera.
    cartera_por_vendedor = {c["vendedor"]: c for c in cartera["comparacion_vendedores"]}
    por_vendedor = []
    for item in resumen["por_vendedor"]:
        pedidos = item["compras"]
        ticket = round(_float(item["plata"]) / pedidos, 2) if pedidos else None
        comp = cartera_por_vendedor.get(item["nombre"], {})
        fila = {
            "vendedor": item["nombre"],
            "importe": _float(item["plata"]),
            "cajas": _float(item["cajas"]),
            "kilos": _float(item["kilos"]),
            "pedidos": pedidos,
            "ticket_promedio": ticket,
            "participacion": item["pct"],
            "clientes_compradores": comp.get("clientes_compradores", 0),
            "clientes_nuevos_30d": comp.get("clientes_nuevos_30d", 0),
        }
        if vendedor_objetivo and fila["vendedor"] != vendedor_objetivo:
            continue
        por_vendedor.append(fila)

    # Mix por empresa dentro del alcance.
    if empresa not in ("", "TODAS"):
        mix_empresa = [
            {
                "nombre": empresa,
                "importe": round(_float(resumen["importe_pre"]), 2),
                "cajas": round(resumen["cajas"], 2),
                "kilos": round(resumen["kilos"], 2),
                "pct": 100.0,
            }
        ]
    else:
        mix_empresa = []
        for dim in EMPRESAS_COMERCIALES:
            sub = _resumen(desde, hasta, empresa=dim, vendedor=vendedor, cliente=cliente,
                           producto=producto, limite=1)
            importe = _float(sub["importe_pre"])
            mix_empresa.append(
                {
                    "nombre": dim,
                    "importe": importe,
                    "cajas": _float(sub["cajas"]),
                    "kilos": _float(sub["kilos"]),
                    "pct": 0.0,
                }
            )
        total_empresa = sum(f["importe"] for f in mix_empresa) or 0
        for fila in mix_empresa:
            fila["pct"] = round(fila["importe"] / total_empresa * 100, 1) if total_empresa else 0.0

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "desde_anterior": anterior_desde.isoformat(),
        "hasta_anterior": anterior_hasta.isoformat(),
        "estado_datos": "disponible" if resumen["lineas_pre"] else "sin_operaciones",
        "ultima_importacion": resumen["ultima_importacion"],
        "fecha_maxima": resumen["fecha_maxima_pre"],
        "granularidad": granularidad,
        "kpis": kpis,
        "ticket_promedio_equipo": resumen["ticket_promedio"],
        "evolucion": evolucion,
        "por_vendedor": por_vendedor,
        "composicion": composicion,
        "mix_empresa": mix_empresa,
        "objetivos": objetivos,
        "tienen_meta": tienen_meta,
        "mes_objetivos": mes,
        "vendedor_objetivo": vendedor_objetivo,
    }