"""Últimas operaciones de un cliente para el desplegable de «Seguimiento de clientes».

Una operación es un comprobante: se agrupan las líneas de stg_sabiogo_ventas por fecha, código
de comprobante y número. El listado sale paginado (por desplazamiento) y solo de ese cliente.
"""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func

from models import db
from models.sabiogo.staging import StgSabiogoVentas as Venta
from services.comercial_criterios import (
    CRITERIO_AMBOS, CRITERIO_FAC, CRITERIO_PRE, TIPO_FAC, TIPO_NC, TIPO_PRE,
    criterios_por_cliente, filtro_comprobante_panel_ventas, tipo_origen)
from services.comercial_pre import expresion_vendedor_resuelta
from services.vendedores_comerciales import resolver_nombre_vendedor

LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 50
DESPLAZAMIENTO_MAXIMO = 100000
LARGO_MAXIMO_CLIENTE = 200
MODOS = ('criterio', 'todos')
TIPO_OTRO = 'OTRO'  # comprobante sin código: se lista solo con «todos los comprobantes»


def vendedor_restringido_actual():
    """Nombre del vendedor al que se limita al usuario actual, o None si ve todo el panel.

    Hoy el panel no vincula usuarios con vendedores comerciales: cualquier rol con acceso al
    módulo ve todos los clientes, igual que el resto de «Seguimiento de clientes». Este es el
    único punto donde, cuando exista ese vínculo, se fija el alcance del vendedor (se aplica
    en el servidor y anula el filtro ``vendedor`` del query string).
    """
    return None


def _cuenta_en_totales(criterio, tipo):
    """Si el panel suma esta operación según el criterio del cliente (NC de AMBOS: no)."""
    if criterio == CRITERIO_AMBOS:
        return tipo in (TIPO_PRE, TIPO_FAC)
    if criterio == CRITERIO_FAC:
        return tipo in (TIPO_FAC, TIPO_NC)
    return tipo == TIPO_PRE


def operaciones_cliente(cliente, desde, hasta, empresa='TODAS', vendedor=None, modo='criterio',
                        limite=LIMITE_POR_DEFECTO, desplazamiento=0):
    """Devuelve una página de operaciones del cliente, de la más reciente a la más antigua."""
    if modo not in MODOS:
        raise ValueError('Modo inválido')
    cliente = (cliente or '').strip()
    if not cliente or len(cliente) > LARGO_MAXIMO_CLIENTE:
        raise ValueError('Cliente inválido')
    if not 1 <= limite <= LIMITE_MAXIMO or not 0 <= desplazamiento <= DESPLAZAMIENTO_MAXIMO:
        raise ValueError('Paginación inválida')
    restringido = vendedor_restringido_actual()
    if restringido is not None:
        vendedor = restringido  # un vendedor no puede ampliar su alcance con el query string

    nombre = func.trim(Venta.cliente)
    comprobante = func.coalesce(func.upper(func.trim(Venta.comprobante)), '')
    nro = func.coalesce(func.trim(Venta.nro_comprob), '')
    filtros = [Venta.estado == 'procesado', nombre == cliente,
               Venta.fecha >= desde, Venta.fecha < hasta + timedelta(days=1)]
    if modo == 'criterio':
        filtros.append(filtro_comprobante_panel_ventas(incluir_nc_ambos=True))
    if empresa and empresa != 'TODAS':
        filtros.append(func.upper(func.coalesce(Venta.origen, '')) == empresa)
    if vendedor:
        filtros.append(expresion_vendedor_resuelta() == resolver_nombre_vendedor(vendedor))
    filas = db.session.query(
        Venta.fecha, comprobante.label('comprobante'), nro.label('nro'),
        func.sum(Venta.subtot).label('importe'), func.count(Venta.id).label('lineas'),
    ).filter(*filtros).group_by(Venta.fecha, comprobante, nro).order_by(
        Venta.fecha.desc(), nro.desc(), comprobante.asc()).limit(limite + 1).offset(desplazamiento).all()

    criterio = criterios_por_cliente().get(cliente) or CRITERIO_PRE
    operaciones = []
    for fila in filas[:limite]:
        tipo = tipo_origen(fila.comprobante) or TIPO_OTRO
        importe = Decimal(str(fila.importe or 0))
        if tipo == TIPO_NC:
            importe = -abs(importe)  # la nota de crédito se muestra siempre en negativo
        operaciones.append(dict(
            fecha=fila.fecha.isoformat(), tipo=tipo, comprobante=fila.comprobante or None,
            nro=fila.nro or None, importe=float(importe), lineas=int(fila.lineas),
            cuenta_en_totales=_cuenta_en_totales(criterio, tipo)))
    hay_mas = len(filas) > limite
    return dict(cliente=cliente, criterio=criterio, modo=modo, operaciones=operaciones,
                hay_mas=hay_mas, siguiente=desplazamiento + limite if hay_mas else None,
                desde=desde.isoformat(), hasta=hasta.isoformat())
