from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Product, BusinessUnit

products_bp = Blueprint("products", __name__)

@products_bp.route("/products")
def list_products():
    products = Product.query.all()
    units = {u.id: u.name for u in BusinessUnit.query.all()}
    return render_template("products_list.html", products=products, units=units)

@products_bp.route("/products/new", methods=["GET", "POST"])
def new_product():
    units = BusinessUnit.query.all()

    if request.method == "POST":
        sku = request.form["sku"]
        name = request.form["name"]
        business_unit_id = request.form["business_unit_id"]
        category = request.form.get("category")

        product = Product(
            sku=sku,
            name=name,
            business_unit_id=business_unit_id,
            category=category
        )
        db.session.add(product)
        db.session.commit()

        return redirect(url_for("products.list_products"))

    return render_template("product_form.html", units=units)

@products_bp.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    units = BusinessUnit.query.all()

    if request.method == "POST":
        product.sku = request.form["sku"]
        product.name = request.form["name"]
        product.business_unit_id = request.form["business_unit_id"]
        product.category = request.form.get("category")

        db.session.commit()

        return redirect(url_for("products.list_products"))

    return render_template("product_form.html", product=product, units=units)
