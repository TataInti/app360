from flask import Blueprint, render_template
from sqlalchemy import func

from models import db, Product, Location, StockLevel, BusinessUnit
from security import protect_blueprint

dashboard_bp = Blueprint("dashboard", __name__)

protect_blueprint(dashboard_bp, "dashboard")

@dashboard_bp.route("/dashboard")
def dashboard():

    total_products = Product.query.count()
    total_locations = Location.query.count()
    total_stock_records = StockLevel.query.count()

    # Stock total por unidad de negocio
    stock_per_unit = (
        db.session.query(
            BusinessUnit.name,
            func.sum(StockLevel.quantity)
        )
        .join(Product, Product.business_unit_id == BusinessUnit.id)
        .join(StockLevel, StockLevel.product_id == Product.id)
        .group_by(BusinessUnit.name)
        .all()
    )

    # Stock total por ubicación
    stock_per_location = (
        db.session.query(
            Location.name,
            func.sum(StockLevel.quantity)
        )
        .join(StockLevel, StockLevel.location_id == Location.id)
        .group_by(Location.name)
        .all()
    )

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_locations=total_locations,
        total_stock_records=total_stock_records,
        stock_per_unit=stock_per_unit,
        stock_per_location=stock_per_location
    )
