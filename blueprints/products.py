from flask import Blueprint, render_template

from models import BusinessUnit
from services.product_service import ProductService
from .base_crud import BaseCRUD

products_bp = Blueprint("products", __name__)

# Create CRUD instance
crud = BaseCRUD("products", None, ProductService, "products")
products_bp = crud.bp

# Override list to include business units
@products_bp.route("/products")
def list_products():
    products = crud.service.get_all()
    units = {u.id: u.name for u in BusinessUnit.query.all()}
    return render_template("products_list.html", products=products, units=units)

# Keep custom new and edit for now, but can refactor later
