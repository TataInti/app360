"""Cartera de clientes y participación para el Panel de Ventas."""

from datetime import date, datetime, timedelta

from sqlalchemy import func

from models import db
from models.sabiogo.staging import StgSabiogoVentas
from services.comercial_pre import calcular_resumen_pre, expresion_vendedor_resuelta
from services.comercial_criterios import filtro_comprobante_panel_ventas
from services.vendedores_comerciales import resolver_nombre_vendedor


def _as_date(value):
    return value.date() if isinstance(value, datetime) else value


def _historial_filters(corte, empresa, vendedor, cliente, producto, vendedor_expr, cliente_expr, producto_expr, session, criterio_clientes):
    filtros = [
        StgSabiogoVentas.estado == "procesado",
        StgSabiogoVentas.fecha <= corte,
        StgSabiogoVentas.vendedor.isnot(None),
        func.trim(StgSabiogoVentas.vendedor) != "",
        cliente_expr.isnot(None),
        cliente_expr != "",
    ]
    if criterio_clientes:
        filtros.append(filtro_comprobante_panel_ventas(session=session))
    else:
        filtros.append(
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE"
        )
    empresa_normalizada = (empresa or "TODAS").strip().upper()
    if empresa_normalizada not in ("", "TODAS"):
        filtros.append(
            func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa_normalizada
        )
    if vendedor:
        filtros.append(vendedor_expr == resolver_nombre_vendedor(vendedor))
    if cliente:
        filtros.append(cliente_expr == cliente)
    if producto:
        filtros.append(producto_expr == producto)
    return filtros


def _producto_mix(rows, limite=10):
    filas = [
        {
            "nombre": row["nombre"],
            "plata": float(row.get("plata") or 0),
            "pct": float(row.get("pct") or 0),
        }
        for row in rows
    ]
    if len(filas) <= limite:
        return filas
    principales = filas[: limite - 1]
    resto = filas[limite - 1 :]
    importe_otros = sum(float(row.get("plata") or 0) for row in resto)
    return principales + [
        {
            "nombre": "Otros",
            "plata": importe_otros,
            "pct": round(sum(float(row.get("pct") or 0) for row in resto), 1),
        }
    ]


def calcular_cartera_comercial(
    desde: date,
    hasta: date,
    empresa: str = "TODAS",
    vendedor: str | None = None,
    cliente: str | None = None,
    producto: str | None = None,
    *,
    session=None,
    criterio_clientes: bool = False,
) -> dict:
    """Devuelve cartera deduplicada, nuevos de 30 días y comparación de vendedores."""
    session = session or db.session
    desde_30d = hasta - timedelta(days=29)
    vendedor_expr = expresion_vendedor_resuelta(session=session)
    cliente_expr = func.trim(StgSabiogoVentas.cliente)
    producto_expr = func.coalesce(
        func.nullif(func.trim(StgSabiogoVentas.producto), ""), "Sin producto"
    )

    # La comparación permanece a nivel de equipo aunque haya un vendedor elegido.
    resumen_equipo = calcular_resumen_pre(
        desde,
        hasta,
        empresa=empresa,
        cliente=cliente,
        producto=producto,
        session=session,
        limite=100000,
        criterio_clientes=criterio_clientes,
    )
    resumen_serie = calcular_resumen_pre(
        desde,
        hasta,
        empresa=empresa,
        vendedor=vendedor,
        cliente=cliente,
        producto=producto,
        session=session,
        limite=100000,
        criterio_clientes=criterio_clientes,
    )

    comparacion = []
    for item in resumen_equipo["por_vendedor"]:
        comparacion.append(
            {
                "vendedor": item["nombre"],
                "importe_pre": item["plata"],
                "participacion": item["pct"],
                "clientes_compradores": item["clientes"],
            }
        )

    filtros_historial = _historial_filters(
        hasta,
        empresa,
        vendedor,
        cliente,
        producto,
        vendedor_expr,
        cliente_expr,
        producto_expr,
        session,
        criterio_clientes,
    )
    historial_rows = (
        session.query(
            cliente_expr.label("cliente"),
            func.max(StgSabiogoVentas.fecha).label("ultima_compra"),
        )
        .filter(*filtros_historial)
        .group_by(cliente_expr)
        .order_by(cliente_expr)
        .all()
    )
    clientes = []
    for row in historial_rows:
        ultima = _as_date(row.ultima_compra)
        dias = (hasta - ultima).days if ultima else None
        clientes.append(
            {
                "cliente": row.cliente,
                "ultima_compra": ultima.isoformat() if ultima else None,
                "dias": dias,
                "estado": "Activo" if ultima and ultima >= desde_30d else "Sin compra en 30 días",
            }
        )

    # La compra inicial usa el criterio actual de cada cliente y nunca fechas
    # posteriores al corte; no depende del período elegido ni de la empresa.
    filtros_primeras = [
        StgSabiogoVentas.estado == "procesado",
        StgSabiogoVentas.fecha <= hasta,
        StgSabiogoVentas.vendedor.isnot(None),
        func.trim(StgSabiogoVentas.vendedor) != "",
        cliente_expr.isnot(None),
        cliente_expr != "",
    ]
    if criterio_clientes:
        filtros_primeras.append(filtro_comprobante_panel_ventas(session=session))
    else:
        filtros_primeras.append(
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE"
        )
    primeras_rows = (
        session.query(
            vendedor_expr.label("vendedor"),
            cliente_expr.label("cliente"),
            func.min(StgSabiogoVentas.fecha).label("primera_compra"),
        )
        .filter(*filtros_primeras)
        .group_by(vendedor_expr, cliente_expr)
        .all()
    )
    nombres_nuevos = set()
    nuevos_por_vendedor = {}
    vendedor_visible = resolver_nombre_vendedor(vendedor) if vendedor else None
    for row in primeras_rows:
        primera = _as_date(row.primera_compra)
        if not primera or not (desde_30d <= primera <= hasta):
            continue
        if cliente and row.cliente != cliente:
            continue
        nombres_nuevos.add(row.cliente)
        nuevos_por_vendedor.setdefault(row.vendedor, set()).add(row.cliente)
    for item in comparacion:
        item["clientes_nuevos_30d"] = len(nuevos_por_vendedor.get(item["vendedor"], set()))

    clientes_nuevos_30d = (
        len(nuevos_por_vendedor.get(vendedor_visible, set()))
        if vendedor_visible
        else len(nombres_nuevos)
    )
    clientes_activos = sum(1 for row in clientes if row["estado"] == "Activo")
    productos = _producto_mix(resumen_serie["por_producto"])
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "desde_30d": desde_30d.isoformat(),
        "vendedor": vendedor_visible,
        "estado_datos": "disponible" if resumen_serie["lineas_pre"] else "sin_operaciones",
        "importe_pre": resumen_serie["importe_pre"],
        "total_clientes": len(clientes),
        "clientes_activos_30d": clientes_activos,
        "clientes_nuevos_30d": clientes_nuevos_30d,
        "clientes": clientes,
        "productos": productos,
        "comparacion_vendedores": comparacion,
    }
