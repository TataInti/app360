"""Client-level document selection used only by the Panel de Ventas."""

from sqlalchemy import and_, func, or_

from models import db
from models.comercial import ComercialClienteCriterio
from models.sabiogo.staging import StgSabiogoVentas


def filtro_comprobante_panel_ventas(session=None):
    """Choose PRE by default; choose non-PRE documents for clients marked FAC."""
    session = session or db.session
    cliente = func.trim(StgSabiogoVentas.cliente)
    comprobante = func.coalesce(func.upper(func.trim(StgSabiogoVentas.comprobante)), "")
    criterio_fac = (
        session.query(ComercialClienteCriterio.id)
        .filter(
            ComercialClienteCriterio.cliente == cliente,
            ComercialClienteCriterio.criterio == "FAC",
        )
        .exists()
    )
    return or_(
        and_(criterio_fac, comprobante != "PRE", comprobante != ""),
        and_(~criterio_fac, comprobante == "PRE"),
    )
