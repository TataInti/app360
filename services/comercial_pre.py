"""Cálculos compartidos sobre PRE procesados de staging."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func

from models import db
from models.comercial import ComercialVendedor, ComercialVendedorAlias
from models.sabiogo.staging import StgSabiogoVentas
from services.vendedores_comerciales import (
    colapsar_espacios,
    normalizar_nombre_origen,
    resolver_nombre_vendedor,
)


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _presentacion(valor: Decimal) -> float:
    return float(valor)


def expresion_vendedor_resuelta(session=None, nombres_origen=None):
    """Agrupa alias y variantes de mayúsculas/espacios con una expresión SQL."""
    session = session or db.session
    if nombres_origen is None:
        nombres_origen = [
            nombre
            for (nombre,) in session.query(StgSabiogoVentas.vendedor)
            .filter(StgSabiogoVentas.estado == "procesado")
            .distinct()
            .all()
        ]

    alias_rows = (
        session.query(
            ComercialVendedorAlias.nombre_normalizado,
            ComercialVendedor.nombre_visible,
        )
        .join(ComercialVendedor, ComercialVendedor.id == ComercialVendedorAlias.vendedor_id)
        .all()
    )
    aliases = {normalizado: visible for normalizado, visible in alias_rows}
    condiciones = []
    for nombre_origen in nombres_origen:
        if nombre_origen is None:
            continue
        clave = normalizar_nombre_origen(nombre_origen)
        visible = aliases.get(clave, colapsar_espacios(nombre_origen))
        condiciones.append((StgSabiogoVentas.vendedor == nombre_origen, visible))
    if not condiciones:
        return func.trim(StgSabiogoVentas.vendedor)
    return case(*condiciones, else_=func.trim(StgSabiogoVentas.vendedor))


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            return None
    return None


def _fecha_importacion(valor):
    return valor.isoformat() if valor is not None else None


def _numero_comprobante():
    return func.nullif(func.trim(func.coalesce(StgSabiogoVentas.nro_comprob, "")), "")


def _clave_fecha():
    return func.date(StgSabiogoVentas.fecha)


def _formatear_dimension(nombre, fila, compras, importe_total, incluir_productos=False):
    plata = _decimal(fila.plata)
    primera = _fecha(fila.primera_fecha)
    ultima = _fecha(fila.ultima_fecha)
    dias = int(fila.fechas_count or 0)
    frecuencia = None
    if dias > 1 and primera is not None and ultima is not None:
        frecuencia = float((ultima - primera).days / (dias - 1))
    return {
        "nombre": nombre,
        "plata": _presentacion(plata),
        "cajas": _presentacion(_decimal(fila.cajas)),
        "kilos": _presentacion(_decimal(fila.kilos)),
        "compras": int(compras),
        "clientes": int(fila.clientes_count or 0),
        "pct": round(float(plata / importe_total * 100), 1) if importe_total else 0.0,
        "productos": int(fila.productos_count or 0) if incluir_productos else 0,
        "ultima_compra": ultima.isoformat() if ultima else None,
        "frecuencia_dias": frecuencia if incluir_productos else None,
        "lineas_sin_numero": int(fila.lineas_sin_numero or 0),
    }


def _agregar_dimension(session, filtros, expresion, importe_total, limite, incluir_productos=False):
    numero = _numero_comprobante()
    cliente = func.nullif(func.trim(StgSabiogoVentas.cliente), "")
    producto = func.nullif(func.trim(StgSabiogoVentas.producto), "")
    fecha = _clave_fecha()
    plata = func.coalesce(func.sum(StgSabiogoVentas.subtot), 0)
    filas = (
        session.query(
            expresion.label("nombre"),
            plata.label("plata"),
            func.coalesce(func.sum(StgSabiogoVentas.cajas), 0).label("cajas"),
            func.coalesce(func.sum(StgSabiogoVentas.kilos), 0).label("kilos"),
            func.sum(case((numero.is_(None), 1), else_=0)).label("lineas_sin_numero"),
            func.count(func.distinct(cliente)).label("clientes_count"),
            func.count(func.distinct(producto)).label("productos_count"),
            func.count(func.distinct(fecha)).label("fechas_count"),
            func.min(fecha).label("primera_fecha"),
            func.max(fecha).label("ultima_fecha"),
        )
        .filter(*filtros)
        .group_by(expresion)
        .order_by(plata.desc(), func.lower(expresion), expresion)
        .limit(limite)
        .all()
    )
    nombres = [fila.nombre for fila in filas]
    compras_por_nombre = {}
    if nombres:
        tickets = (
            session.query(
                expresion.label("nombre"),
                StgSabiogoVentas.origen,
                StgSabiogoVentas.sucursal,
                StgSabiogoVentas.tipo,
                numero.label("numero"),
                fecha.label("fecha"),
            )
            .filter(*filtros, expresion.in_(nombres), numero.isnot(None))
            .group_by(
                expresion,
                StgSabiogoVentas.origen,
                StgSabiogoVentas.sucursal,
                StgSabiogoVentas.tipo,
                numero,
                fecha,
            )
            .subquery()
        )
        compras_por_nombre = {
            fila.nombre: int(fila.compras)
            for fila in session.query(
                tickets.c.nombre,
                func.count().label("compras"),
            )
            .group_by(tickets.c.nombre)
            .all()
        }
    return [
        _formatear_dimension(
            fila.nombre,
            fila,
            compras_por_nombre.get(fila.nombre, 0),
            importe_total,
            incluir_productos,
        )
        for fila in filas
    ]


def calcular_resumen_pre(
    desde: date,
    hasta: date,
    empresa: str | None = None,
    vendedor: str | None = None,
    cliente: str | None = None,
    producto: str | None = None,
    *,
    session=None,
    limite: int = 10,
    criterio_clientes: bool = False,
) -> dict:
    """Calcula métricas completas; permite criterios mixtos solo al solicitarlo."""
    session = session or db.session
    filtros_base = [
        StgSabiogoVentas.estado == "procesado",
        StgSabiogoVentas.fecha >= desde,
        StgSabiogoVentas.fecha < hasta + timedelta(days=1),
    ]
    if criterio_clientes:
        from services.comercial_criterios import filtro_comprobante_panel_ventas

        filtros_base.append(filtro_comprobante_panel_ventas(session=session))
    else:
        filtros_base.append(
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE"
        )
    empresa_normalizada = (empresa or "").strip().upper()
    if empresa_normalizada and empresa_normalizada != "TODAS":
        filtros_base.append(
            func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa_normalizada
        )
    if cliente:
        filtros_base.append(func.trim(StgSabiogoVentas.cliente) == cliente)
    if producto:
        filtros_base.append(func.trim(StgSabiogoVentas.producto) == producto)

    nombres_origen = [
        nombre
        for (nombre,) in session.query(StgSabiogoVentas.vendedor)
        .filter(*filtros_base)
        .distinct()
        .all()
    ]
    vendedor_expr = expresion_vendedor_resuelta(session, nombres_origen)
    filtros = list(filtros_base)
    vendedor_objetivo = resolver_nombre_vendedor(vendedor) if vendedor else None
    if vendedor_objetivo is not None:
        filtros.append(vendedor_expr == vendedor_objetivo)

    cliente_no_vacio = func.nullif(func.trim(StgSabiogoVentas.cliente), "")
    numero = _numero_comprobante()
    fecha = _clave_fecha()
    total = (
        session.query(
            func.count(StgSabiogoVentas.id).label("lineas"),
            func.coalesce(func.sum(StgSabiogoVentas.subtot), 0).label("plata"),
            func.coalesce(func.sum(StgSabiogoVentas.cajas), 0).label("cajas"),
            func.coalesce(func.sum(StgSabiogoVentas.kilos), 0).label("kilos"),
            func.sum(case((numero.is_(None), 1), else_=0)).label("lineas_sin_numero"),
            func.count(func.distinct(cliente_no_vacio)).label("clientes_compradores"),
            func.max(fecha).label("fecha_maxima"),
            func.max(StgSabiogoVentas.fecha_import).label("ultima_importacion"),
        )
        .filter(*filtros)
        .one()
    )
    tickets = (
        session.query(
            StgSabiogoVentas.origen.label("origen"),
            StgSabiogoVentas.sucursal.label("sucursal"),
            StgSabiogoVentas.tipo.label("tipo"),
            numero.label("numero"),
            fecha.label("fecha"),
            func.coalesce(func.sum(StgSabiogoVentas.subtot), 0).label("plata"),
        )
        .filter(*filtros, numero.isnot(None))
        .group_by(
            StgSabiogoVentas.origen,
            StgSabiogoVentas.sucursal,
            StgSabiogoVentas.tipo,
            numero,
            fecha,
        )
        .subquery()
    )
    resumen_tickets = (
        session.query(
            func.count().label("pedidos"),
            func.coalesce(func.sum(tickets.c.plata), 0).label("plata_pedidos"),
        )
        .select_from(tickets)
        .one()
    )
    importe_total = _decimal(total.plata)
    pedido_count = int(resumen_tickets.pedidos or 0)
    importe_pedidos = _decimal(resumen_tickets.plata_pedidos)
    ticket = _presentacion(importe_pedidos / pedido_count) if pedido_count else None

    limite_dimension = max(0, int(limite))
    vendedor_dimension = func.coalesce(func.nullif(func.trim(vendedor_expr), ""), "Sin vendedor")
    cliente_dimension = func.coalesce(
        func.nullif(func.trim(StgSabiogoVentas.cliente), ""), "Sin cliente"
    )
    producto_dimension = func.coalesce(
        func.nullif(func.trim(StgSabiogoVentas.producto), ""), "Sin producto"
    )
    por_vendedor = _agregar_dimension(
        session, filtros, vendedor_dimension, importe_total, limite_dimension
    )
    por_cliente = _agregar_dimension(
        session,
        filtros,
        cliente_dimension,
        importe_total,
        limite_dimension,
        incluir_productos=True,
    )
    por_producto = _agregar_dimension(
        session, filtros, producto_dimension, importe_total, limite_dimension
    )
    detalle_cliente = None
    if cliente:
        detalle_rows = _agregar_dimension(
            session,
            filtros,
            cliente_dimension,
            importe_total,
            1,
            incluir_productos=True,
        )
        detalle_cliente = detalle_rows[0] if detalle_rows else None

    filas_dia = (
        session.query(
            fecha.label("fecha"),
            func.count(StgSabiogoVentas.id).label("cantidad"),
            func.coalesce(func.sum(StgSabiogoVentas.subtot), 0).label("monto"),
            func.coalesce(func.sum(StgSabiogoVentas.cajas), 0).label("cajas"),
            func.coalesce(func.sum(StgSabiogoVentas.kilos), 0).label("kilos"),
        )
        .filter(*filtros)
        .group_by(fecha)
        .order_by(fecha)
        .all()
    )
    por_dia = [
        {
            "fecha": _fecha(fila.fecha).isoformat(),
            "cantidad": int(fila.cantidad),
            "monto": _presentacion(_decimal(fila.monto)),
            "cajas": _presentacion(_decimal(fila.cajas)),
            "kilos": _presentacion(_decimal(fila.kilos)),
        }
        for fila in filas_dia
        if _fecha(fila.fecha) is not None
    ]

    fecha_maxima = _fecha(total.fecha_maxima)
    ultima_importacion = total.ultima_importacion
    return {
        "importe_pre": _presentacion(importe_total),
        "cajas": _presentacion(_decimal(total.cajas)),
        "kilos": _presentacion(_decimal(total.kilos)),
        "clientes_compradores": int(total.clientes_compradores or 0),
        "pedidos_identificados": pedido_count,
        "importe_pedidos_identificados": _presentacion(importe_pedidos),
        "ticket_promedio": ticket,
        "lineas_sin_numero": int(total.lineas_sin_numero or 0),
        "lineas_pre": int(total.lineas or 0),
        "fecha_maxima_pre": fecha_maxima.isoformat() if fecha_maxima else None,
        "ultima_importacion": _fecha_importacion(ultima_importacion),
        "por_vendedor": por_vendedor,
        "por_cliente": por_cliente,
        "por_producto": por_producto,
        "por_fecha": por_dia,
        "cliente_seleccionado": detalle_cliente,
    }
