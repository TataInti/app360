from flask import Blueprint, render_template, request, redirect, url_for

from models import BusinessUnit
from services.product_service import ProductService
from security import protect_blueprint
from .base_crud import BaseCRUD

products_bp = Blueprint("products", __name__)

# Create CRUD instance
crud = BaseCRUD("products", None, ProductService, "products")
products_bp = crud.bp
# Incluye las rutas de BaseCRUD (/, /new, /edit/<id>) además de las propias.
protect_blueprint(products_bp, "products")

# Override list to include business units
@products_bp.route("/products")
def list_products():
    products = crud.service.get_all()
    units = {u.id: u.name for u in BusinessUnit.query.all()}
    return render_template("products_list.html", products=products, units=units)


# Override new to include business units
@products_bp.route("/products/new", methods=["GET", "POST"])
def new_product():
    units = BusinessUnit.query.all()
    if request.method == "POST":
        kwargs = {key: value for key, value in request.form.items() if key != "csrf_token"}
        crud.service.create(**kwargs)
        return redirect(url_for("products.list_products"))
    return render_template("product_form.html", units=units)


# Override edit to include business units
@products_bp.route("/products/edit/<int:item_id>", methods=["GET", "POST"])
def edit_product(item_id):
    units = BusinessUnit.query.all()
    product = crud.service.get_by_id(item_id)
    if not product:
        return "Producto no encontrado", 404
    
    if request.method == "POST":
        kwargs = {key: value for key, value in request.form.items() if key != "csrf_token"}
        crud.service.update(item_id, **kwargs)
        return redirect(url_for("products.list_products"))
    
    return render_template("product_form.html", product=product, units=units)
