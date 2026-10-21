"""Cálculos compartidos sobre PRE procesados de staging."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func

from models import db
from models.sabiogo.staging import StgSabiogoVentas
from services.vendedores_comerciales import resolver_nombre_vendedor


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _presentacion(valor: Decimal) -> float:
    return float(valor)


def _pedido_key(fila):
    numero = (fila.nro_comprob or "").strip()
    if not numero:
        return None
    return (
        fila.origen,
        fila.sucursal,
        fila.tipo,
        numero,
        fila.fecha,
    )


def expresion_vendedor_resuelta(session=None):
    """Expresión SQL que agrupa cada texto de staging por su identidad resuelta."""
    session = session or db.session
    nombres_origen = (
        session.query(StgSabiogoVentas.vendedor)
        .filter(
            StgSabiogoVentas.estado == "procesado",
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
        )
        .distinct()
        .all()
    )
    condiciones = []
    for (nombre_origen,) in nombres_origen:
        if nombre_origen is None:
            continue
        nombre_visible = resolver_nombre_vendedor(nombre_origen)
        condiciones.append(
            (StgSabiogoVentas.vendedor == nombre_origen, nombre_visible or "Sin vendedor")
        )
    if not condiciones:
        return func.trim(StgSabiogoVentas.vendedor)
    return case(*condiciones, else_=func.trim(StgSabiogoVentas.vendedor))


def _nuevo_acumulador():
    return {
        "plata": Decimal("0"),
        "cajas": Decimal("0"),
        "kilos": Decimal("0"),
        "plata_pedidos": Decimal("0"),
        "pedidos": set(),
        "clientes": set(),
        "productos": set(),
        "fechas": set(),
        "lineas": 0,
        "lineas_sin_numero": 0,
        "fecha_maxima": None,
        "ultima_importacion": None,
    }


def _agregar_linea(acumulador, fila, cliente, producto):
    plata = _decimal(fila.subtot)
    acumulador["plata"] += plata
    acumulador["cajas"] += _decimal(fila.cajas)
    acumulador["kilos"] += _decimal(fila.kilos)
    acumulador["lineas"] += 1

    pedido = _pedido_key(fila)
    if pedido is None:
        acumulador["lineas_sin_numero"] += 1
    else:
        acumulador["pedidos"].add(pedido)
        acumulador["plata_pedidos"] += plata

    if cliente:
        acumulador["clientes"].add(cliente)
    if producto:
        acumulador["productos"].add(producto)
    if fila.fecha:
        acumulador["fechas"].add(fila.fecha)
        if acumulador["fecha_maxima"] is None or fila.fecha > acumulador["fecha_maxima"]:
            acumulador["fecha_maxima"] = fila.fecha
    if fila.fecha_import:
        if (
            acumulador["ultima_importacion"] is None
            or fila.fecha_import > acumulador["ultima_importacion"]
        ):
            acumulador["ultima_importacion"] = fila.fecha_import


def _formatear_dimension(nombre, acumulador, importe_total, incluir_productos=False):
    plata = acumulador["plata"]
    fechas = acumulador["fechas"]
    primera = min(fechas) if fechas else None
    ultima = max(fechas) if fechas else None
    frecuencia = None
    if len(fechas) > 1 and primera is not None and ultima is not None:
        frecuencia = float((ultima - primera).days / (len(fechas) - 1))
    return {
        "nombre": nombre,
        "plata": _presentacion(plata),
        "cajas": _presentacion(acumulador["cajas"]),
        "kilos": _presentacion(acumulador["kilos"]),
        "compras": len(acumulador["pedidos"]),
        "clientes": len(acumulador["clientes"]),
        "pct": round(float(plata / importe_total * 100), 1) if importe_total else 0.0,
        "productos": len(acumulador["productos"]) if incluir_productos else 0,
        "ultima_compra": ultima.isoformat() if ultima else None,
        "frecuencia_dias": frecuencia if incluir_productos else None,
        "lineas_sin_numero": acumulador["lineas_sin_numero"],
    }


def _ordenar_dimension(acumuladores, importe_total, limite=10, incluir_productos=False):
    ordenados = sorted(
        acumuladores.items(),
        key=lambda item: (-item[1]["plata"], item[0].casefold()),
    )
    return [
        _formatear_dimension(nombre, acumulador, importe_total, incluir_productos)
        for nombre, acumulador in ordenados[:limite]
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
    filtros = [
        StgSabiogoVentas.estado == "procesado",
        StgSabiogoVentas.fecha >= desde,
        StgSabiogoVentas.fecha <= hasta,
    ]
    if criterio_clientes:
        from services.comercial_criterios import filtro_comprobante_panel_ventas

        filtros.append(filtro_comprobante_panel_ventas(session=session))
    else:
        filtros.append(
            func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "") == "PRE"
        )
    empresa_normalizada = (empresa or "").strip().upper()
    if empresa_normalizada and empresa_normalizada != "TODAS":
        filtros.append(
            func.upper(func.coalesce(StgSabiogoVentas.origen, "")) == empresa_normalizada
        )
    if cliente:
        filtros.append(StgSabiogoVentas.cliente == cliente)
    if producto:
        filtros.append(StgSabiogoVentas.producto == producto)

    filas = (
        session.query(
            StgSabiogoVentas.vendedor.label("vendedor"),
            StgSabiogoVentas.cliente.label("cliente"),
            StgSabiogoVentas.producto.label("producto"),
            StgSabiogoVentas.origen.label("origen"),
            StgSabiogoVentas.sucursal.label("sucursal"),
            StgSabiogoVentas.tipo.label("tipo"),
            StgSabiogoVentas.nro_comprob.label("nro_comprob"),
            StgSabiogoVentas.fecha.label("fecha"),
            StgSabiogoVentas.fecha_import.label("fecha_import"),
            StgSabiogoVentas.subtot.label("subtot"),
            StgSabiogoVentas.cajas.label("cajas"),
            StgSabiogoVentas.kilos.label("kilos"),
        )
        .filter(*filtros)
        .all()
    )
    vendedor_objetivo = resolver_nombre_vendedor(vendedor) if vendedor else None
    vendedores_resueltos = {}
    por_vendedor = defaultdict(_nuevo_acumulador)
    por_cliente = defaultdict(_nuevo_acumulador)
    por_producto = defaultdict(_nuevo_acumulador)
    por_fecha = defaultdict(_nuevo_acumulador)
    total = _nuevo_acumulador()
    clientes_compradores = set()
    detalle_cliente = None

    for fila in filas:
        origen = fila.vendedor
        if origen not in vendedores_resueltos:
            vendedores_resueltos[origen] = resolver_nombre_vendedor(origen)
        nombre_vendedor = vendedores_resueltos[origen]
        if vendedor_objetivo is not None and nombre_vendedor != vendedor_objetivo:
            continue

        nombre_vendedor = nombre_vendedor or "Sin vendedor"
        nombre_cliente = (fila.cliente or "").strip()
        nombre_producto = (fila.producto or "").strip()
        cliente_dimension = nombre_cliente or "Sin cliente"
        producto_dimension = nombre_producto or "Sin producto"

        _agregar_linea(total, fila, nombre_cliente, nombre_producto)
        _agregar_linea(
            por_vendedor[nombre_vendedor],
            fila,
            nombre_cliente,
            nombre_producto,
        )
        _agregar_linea(
            por_cliente[cliente_dimension],
            fila,
            nombre_cliente,
            nombre_producto,
        )
        _agregar_linea(
            por_producto[producto_dimension],
            fila,
            nombre_cliente,
            nombre_producto,
        )
        _agregar_linea(por_fecha[fila.fecha], fila, nombre_cliente, nombre_producto)
        if nombre_cliente:
            clientes_compradores.add(nombre_cliente)

    importe_total = total["plata"]
    pedido_count = len(total["pedidos"])
    ticket = (
        _presentacion(total["plata_pedidos"] / pedido_count)
        if pedido_count
        else None
    )

    if cliente:
        detalle_cliente = por_cliente.get((cliente or "").strip())

    por_dia = [
        {
            "fecha": fecha.isoformat(),
            "cantidad": acumulador["lineas"],
            "monto": _presentacion(acumulador["plata"]),
            "cajas": _presentacion(acumulador["cajas"]),
            "kilos": _presentacion(acumulador["kilos"]),
        }
        for fecha, acumulador in sorted(por_fecha.items())
    ]

    fecha_maxima = total["fecha_maxima"]
    ultima_importacion = total["ultima_importacion"]
    return {
        "importe_pre": _presentacion(importe_total),
        "cajas": _presentacion(total["cajas"]),
        "kilos": _presentacion(total["kilos"]),
        "clientes_compradores": len(clientes_compradores),
        "pedidos_identificados": pedido_count,
        "importe_pedidos_identificados": _presentacion(total["plata_pedidos"]),
        "ticket_promedio": ticket,
        "lineas_sin_numero": total["lineas_sin_numero"],
        "lineas_pre": total["lineas"],
        "fecha_maxima_pre": fecha_maxima.isoformat() if fecha_maxima else None,
        "ultima_importacion": (
            ultima_importacion.isoformat() if ultima_importacion else None
        ),
        "por_vendedor": _ordenar_dimension(por_vendedor, importe_total, limite),
        "por_cliente": _ordenar_dimension(
            por_cliente,
            importe_total,
            limite,
            incluir_productos=True,
        ),
        "por_producto": _ordenar_dimension(por_producto, importe_total, limite),
        "por_fecha": por_dia,
        "cliente_seleccionado": (
            _formatear_dimension(
                (cliente or "").strip() or "Sin cliente",
                detalle_cliente,
                importe_total,
                incluir_productos=True,
            )
            if detalle_cliente is not None
            else None
        ),
    }
