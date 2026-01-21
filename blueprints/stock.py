from flask import Blueprint, redirect, render_template, request, url_for

from models import Location, Product, StockLevel, db

stock_bp = Blueprint("stock", __name__)


@stock_bp.route("/stock")
def stock_list():
    stock_rows = StockLevel.query.all()
    products = {p.id: p for p in Product.query.all()}
    locations = {location.id: location for location in Location.query.all()}
    return render_template(
        "stock_list.html", stock_rows=stock_rows, products=products, locations=locations
    )


@stock_bp.route("/stock/new", methods=["GET", "POST"])
def stock_new():
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        product_id = int(request.form["product_id"])
        location_id = int(request.form["location_id"])
        quantity = int(request.form["quantity"])

        # Ver si ya existe ese registro producto+ubicación
        existing = StockLevel.query.filter_by(
            product_id=product_id, location_id=location_id
        ).first()

        if existing:
            existing.quantity = quantity
        else:
            sl = StockLevel(product_id=product_id, location_id=location_id, quantity=quantity)
            db.session.add(sl)

        db.session.commit()
        return redirect(url_for("stock.stock_list"))

    return render_template("stock_form.html", products=products, locations=locations)


@stock_bp.route("/stock/edit/<int:stock_id>", methods=["GET", "POST"])
def stock_edit(stock_id):
    stock = StockLevel.query.get_or_404(stock_id)
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        stock.product_id = int(request.form["product_id"])
        stock.location_id = int(request.form["location_id"])
        stock.quantity = int(request.form["quantity"])
        db.session.commit()
        return redirect(url_for("stock.stock_list"))

    return render_template("stock_form.html", stock=stock, products=products, locations=locations)
