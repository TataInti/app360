"""Selección de comprobantes por cliente para los paneles comerciales.

Cada cliente tiene un criterio: PRE (presupuestos, valor por defecto), FAC (comprobantes
no PRE) o AMBOS (PRE más comprobantes no PRE). Las notas de crédito (NPF) no suman en los
totales de un cliente AMBOS: el Seguimiento de clientes las muestra aparte.
"""

from sqlalchemy import and_, func, or_

from models import db
from models.comercial import ComercialClienteCriterio
from models.sabiogo.staging import StgSabiogoVentas

CRITERIO_PRE = "PRE"
CRITERIO_FAC = "FAC"
CRITERIO_AMBOS = "AMBOS"
CRITERIOS_VALIDOS = (CRITERIO_PRE, CRITERIO_FAC, CRITERIO_AMBOS)
# Comprobantes que son notas de crédito (hoy solo NPF); ampliar acá si aparecen otros.
COMPROBANTES_NC = ("NPF",)
TIPO_PRE, TIPO_FAC, TIPO_NC = "PRE", "FAC", "NC"


def normalizar_criterio(valor):
    """Devuelve PRE, FAC o AMBOS (en mayúsculas) o None si el valor no es válido."""
    texto = str(valor or "").strip().upper()
    return texto if texto in CRITERIOS_VALIDOS else None


def tipo_origen(comprobante):
    """Clasifica un comprobante: PRE, NC (nota de crédito), FAC (otro con código) o None."""
    codigo = str(comprobante or "").strip().upper()
    if not codigo:
        return None
    if codigo == "PRE":
        return TIPO_PRE
    if codigo in COMPROBANTES_NC:
        return TIPO_NC
    return TIPO_FAC


def criterios_por_cliente(session=None):
    """Mapa cliente -> criterio guardado; el cliente sin fila no figura (equivale a PRE)."""
    session = session or db.session
    return {
        fila.cliente: fila.criterio
        for fila in session.query(
            ComercialClienteCriterio.cliente, ComercialClienteCriterio.criterio
        ).all()
    }


def filtro_comprobante_panel_ventas(session=None, incluir_nc_ambos=False):
    """Elige los comprobantes de cada cliente según su criterio.

    - Sin fila o PRE: solo PRE.
    - FAC: todo comprobante con código que no sea PRE (incluye NPF, como siempre).
    - AMBOS: PRE y no PRE con código, sin NPF. Con ``incluir_nc_ambos`` también trae
      las NPF, para listarlas sin sumarlas (Seguimiento de clientes).
    """
    session = session or db.session
    cliente = func.trim(StgSabiogoVentas.cliente)
    comprobante = func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "")

    def _tiene(valor):
        return (
            session.query(ComercialClienteCriterio.id)
            .filter(
                ComercialClienteCriterio.cliente == cliente,
                ComercialClienteCriterio.criterio == valor,
            )
            .exists()
        )

    criterio_fac = _tiene(CRITERIO_FAC)
    criterio_ambos = _tiene(CRITERIO_AMBOS)
    cond_ambos = and_(criterio_ambos, comprobante != "")
    if not incluir_nc_ambos:
        cond_ambos = and_(cond_ambos, comprobante.notin_(COMPROBANTES_NC))
    return or_(
        and_(criterio_fac, comprobante != "PRE", comprobante != ""),
        and_(~criterio_fac, ~criterio_ambos, comprobante == "PRE"),
        cond_ambos,
    )
