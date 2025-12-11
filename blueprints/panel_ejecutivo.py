from flask import Blueprint, render_template
from models import db, Lead, Product, StockLevel, Location, BusinessUnit
from sqlalchemy import func

panel_bp = Blueprint("panel_ejecutivo", __name__)

@panel_bp.route("/panel-ejecutivo")
def panel_ejecutivo():

    # Totales generales
    total_leads = Lead.query.count()
    total_products = Product.query.count()
    total_locations = Location.query.count()

    # Leads por estado
    estados = ["nuevo", "contactado", "propuesta", "ganado", "perdido"]
    leads_por_estado = {
        estado: Lead.query.filter_by(status=estado).count()
        for estado in estados
    }

    # Conversión
    ganados = leads_por_estado["ganado"]
    conversion = round((ganados / total_leads * 100), 2) if total_leads else 0

    # Stock total por unidad de negocio
    stock_por_unidad = (
        db.session.query(
            BusinessUnit.name,
            func.sum(StockLevel.quantity)
        )
        .join(Product, Product.business_unit_id == BusinessUnit.id)
        .join(StockLevel, StockLevel.product_id == Product.id)
        .group_by(BusinessUnit.name)
        .all()
    )

    # Productos con stock bajo (regla simple: < 5 unidades en total)
    stock_bajo = (
        db.session.query(Product.name, func.sum(StockLevel.quantity))
        .join(StockLevel, StockLevel.product_id == Product.id)
        .group_by(Product.name)
        .having(func.sum(StockLevel.quantity) < 5)
        .all()
    )

    return render_template(
        "panel_ejecutivo.html",
        total_leads=total_leads,
        total_products=total_products,
        total_locations=total_locations,
        leads_por_estado=leads_por_estado,
        conversion=conversion,
        stock_por_unidad=stock_por_unidad,
        stock_bajo=stock_bajo
    )
