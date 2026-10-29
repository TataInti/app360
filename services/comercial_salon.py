"""Lectura breve de tickets FAC del vendedor Salón desde staging procesado."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from models import db
from models.comercial import ComercialVendedor, ComercialVendedorAlias
from models.sabiogo.staging import StgSabiogoVentas as Venta
from services.vendedores_comerciales import normalizar_nombre_origen

NOMBRE_VENDEDOR_SALON = "Salón"
CLIENTE_CONSUMIDOR_FINAL = "Consumidor final"


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _fecha(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def _componente_documento(value) -> str:
    return " ".join(str(value or "").split())


def _cliente_visible(value) -> str:
    nombre = _componente_documento(value)
    if normalizar_nombre_origen(nombre) in {"", "CF", "CONSUMIDOR FINAL"}:
        return CLIENTE_CONSUMIDOR_FINAL
    return nombre


def _comparativo(actual, anterior) -> dict:
    actual = float(actual or 0)
    anterior = float(anterior or 0)
    variacion = round((actual - anterior) / abs(anterior) * 100, 1) if anterior else None
    return {
        "actual": actual,
        "anterior": anterior,
        "diferencia": actual - anterior,
        "variacion_pct": variacion,
        "variacion_texto": (
            f"{variacion:+.1f}%" if variacion is not None else "Sin base comparable"
        ),
    }


def _metricas(tickets: list[dict]) -> dict:
    return {
        "tickets": len(tickets),
        "importe": sum((ticket["_importe"] for ticket in tickets), Decimal("0")),
        "cajas": sum((ticket["_cajas"] for ticket in tickets), Decimal("0")),
        "kilos": sum((ticket["_kilos"] for ticket in tickets), Decimal("0")),
    }


def _buscar_aliases_salon(session):
    vendedor = (
        session.query(ComercialVendedor)
        .filter_by(nombre_visible=NOMBRE_VENDEDOR_SALON, activo=True)
        .one_or_none()
    )
    if vendedor is None:
        return set()
    return {
        normalizar_nombre_origen(alias.nombre_normalizado)
        for alias in session.query(ComercialVendedorAlias)
        .filter_by(vendedor_id=vendedor.id)
        .all()
        if normalizar_nombre_origen(alias.nombre_normalizado)
    }


def resumen_tablero_salon(desde: date, hasta: date, session=None) -> dict:
    """Agrupa líneas FAC en tickets identificados y compara ventanas iguales."""
    session = session or db.session
    if desde > hasta:
        raise ValueError("Desde no puede ser posterior a Hasta.")

    largo = (hasta - desde).days + 1
    desde_anterior = desde - timedelta(days=largo)
    hasta_anterior = desde - timedelta(days=1)
    alias_salon = _buscar_aliases_salon(session)

    fecha_fac = [
        Venta.estado == "procesado",
        func.upper(func.trim(func.coalesce(Venta.comprobante, ""))) == "FAC",
        Venta.fecha >= desde_anterior,
        Venta.fecha < hasta + timedelta(days=1),
    ]
    vendedores_origen = {
        fila[0]
        for fila in session.query(Venta.vendedor)
        .filter(*fecha_fac, Venta.vendedor.isnot(None))
        .distinct()
        .all()
        if normalizar_nombre_origen(fila[0]) in alias_salon
    }

    por_periodo = {"actual": {}, "anterior": {}}
    if vendedores_origen:
        filtros = [*fecha_fac, Venta.vendedor.in_(vendedores_origen)]
        for columna in (Venta.origen, Venta.sucursal, Venta.tipo, Venta.nro_comprob):
            filtros.extend((columna.isnot(None), func.trim(columna) != ""))

        filas = (
            session.query(
                Venta.origen.label("origen"),
                Venta.sucursal.label("sucursal"),
                Venta.tipo.label("tipo"),
                Venta.nro_comprob.label("numero"),
                Venta.fecha.label("fecha"),
                Venta.cliente.label("cliente"),
                func.sum(func.coalesce(Venta.subtot, 0)).label("importe"),
                func.sum(func.coalesce(Venta.cajas, 0)).label("cajas"),
                func.sum(func.coalesce(Venta.kilos, 0)).label("kilos"),
            )
            .filter(*filtros)
            .group_by(
                Venta.origen,
                Venta.sucursal,
                Venta.tipo,
                Venta.nro_comprob,
                Venta.fecha,
                Venta.cliente,
            )
            .all()
        )

        for fila in filas:
            fecha = _fecha(fila.fecha)
            periodo = "actual" if desde <= fecha <= hasta else "anterior"
            if not desde_anterior <= fecha <= hasta:
                continue

            origen = _componente_documento(fila.origen)
            sucursal = _componente_documento(fila.sucursal)
            tipo = _componente_documento(fila.tipo)
            numero = _componente_documento(fila.numero)
            if not all((origen, sucursal, tipo, numero)):
                continue
            clave = (origen, sucursal, tipo, numero, fecha)
            ticket = por_periodo[periodo].setdefault(
                clave,
                {
                    "fecha": fecha,
                    "origen": origen,
                    "sucursal": sucursal,
                    "tipo": tipo,
                    "numero": numero,
                    "_importe": Decimal("0"),
                    "_cajas": Decimal("0"),
                    "_kilos": Decimal("0"),
                    "_clientes": {},
                },
            )
            ticket["_importe"] += _decimal(fila.importe)
            ticket["_cajas"] += _decimal(fila.cajas)
            ticket["_kilos"] += _decimal(fila.kilos)

            cliente = _cliente_visible(fila.cliente)
            if cliente != CLIENTE_CONSUMIDOR_FINAL:
                clave_cliente = normalizar_nombre_origen(cliente)
                actual = ticket["_clientes"].get(clave_cliente)
                if actual is None or (cliente.casefold(), cliente) < (actual.casefold(), actual):
                    ticket["_clientes"][clave_cliente] = cliente

    tickets_actual = []
    tickets_anterior = []
    for periodo, destino in (("actual", tickets_actual), ("anterior", tickets_anterior)):
        for ticket in por_periodo[periodo].values():
            destino.append(
                {
                    "fecha": ticket["fecha"].isoformat(),
                    "origen": ticket["origen"],
                    "sucursal": ticket["sucursal"],
                    "tipo": ticket["tipo"],
                    "numero": ticket["numero"],
                    "vendedor": NOMBRE_VENDEDOR_SALON,
                    "cliente": next(
                        iter(
                            sorted(
                                ticket["_clientes"].values(),
                                key=lambda nombre: (nombre.casefold(), nombre),
                            )
                        ),
                        CLIENTE_CONSUMIDOR_FINAL,
                    ),
                    "importe": float(ticket["_importe"]),
                    "cajas": float(ticket["_cajas"]),
                    "kilos": float(ticket["_kilos"]),
                    "_importe": ticket["_importe"],
                    "_cajas": ticket["_cajas"],
                    "_kilos": ticket["_kilos"],
                }
            )

    tickets_actual.sort(
        key=lambda ticket: (
            ticket["fecha"],
            ticket["origen"].casefold(),
            ticket["sucursal"].casefold(),
            ticket["tipo"].casefold(),
            ticket["numero"].casefold(),
        ),
        reverse=True,
    )
    metricas_actuales = _metricas(tickets_actual)
    metricas_anteriores = _metricas(tickets_anterior)
    kpis = {
        nombre: _comparativo(metricas_actuales[nombre], metricas_anteriores[nombre])
        for nombre in ("tickets", "importe", "cajas", "kilos")
    }

    for ticket in (*tickets_actual, *tickets_anterior):
        ticket.pop("_importe")
        ticket.pop("_cajas")
        ticket.pop("_kilos")

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "desde_anterior": desde_anterior.isoformat(),
        "hasta_anterior": hasta_anterior.isoformat(),
        "vendedor": NOMBRE_VENDEDOR_SALON,
        "kpis": kpis,
        "tickets": tickets_actual,
    }
