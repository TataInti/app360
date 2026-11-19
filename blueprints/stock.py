from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import Location, Product, StockLevel, db
from security import protect_blueprint

stock_bp = Blueprint("stock", __name__)
protect_blueprint(stock_bp, "stock")


def _cantidad_valida(valor):
    """Cantidad de stock: entero mayor o igual que cero. Negativa o no numérica se rechaza."""
    texto = (valor or "").strip()
    if texto.startswith("-"):
        raise ValueError("La cantidad no puede ser negativa.")
    if not texto.isdigit():
        raise ValueError("La cantidad tiene que ser un número entero, por ejemplo 10.")
    return int(texto)


def _mensaje_par_existente(registro):
    return (
        f"Ya hay stock de este producto en esa ubicación ({registro.quantity}). "
        "Editalo o sumá la diferencia."
    )


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
        try:
            product_id = int(request.form.get("product_id", ""))
            location_id = int(request.form.get("location_id", ""))
        except ValueError:
            flash("Elegí un producto y una ubicación.", "warning")
            return render_template("stock_form.html", products=products, locations=locations), 400
        try:
            quantity = _cantidad_valida(request.form.get("quantity"))
        except ValueError as error:
            flash(str(error), "warning")
            return render_template("stock_form.html", products=products, locations=locations), 400

        # Un par producto×ubicación no se duplica: si ya existe, se avisa y no se pisa.
        existing = StockLevel.query.filter_by(product_id=product_id, location_id=location_id).first()
        if existing:
            flash(_mensaje_par_existente(existing), "warning")
            return render_template("stock_form.html", products=products, locations=locations), 409

        db.session.add(StockLevel(product_id=product_id, location_id=location_id, quantity=quantity))
        db.session.commit()
        return redirect(url_for("stock.stock_list"))

    return render_template("stock_form.html", products=products, locations=locations)


@stock_bp.route("/stock/edit/<int:stock_id>", methods=["GET", "POST"])
def stock_edit(stock_id):
    stock = StockLevel.query.get_or_404(stock_id)
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id", ""))
            location_id = int(request.form.get("location_id", ""))
        except ValueError:
            flash("Elegí un producto y una ubicación.", "warning")
            return render_template("stock_form.html", stock=stock, products=products, locations=locations), 400
        try:
            quantity = _cantidad_valida(request.form.get("quantity"))
        except ValueError as error:
            flash(str(error), "warning")
            return render_template("stock_form.html", stock=stock, products=products, locations=locations), 400

        # Editar no puede dejar dos filas para el mismo par producto×ubicación.
        otro = StockLevel.query.filter(
            StockLevel.product_id == product_id,
            StockLevel.location_id == location_id,
            StockLevel.id != stock.id,
        ).first()
        if otro:
            flash(_mensaje_par_existente(otro), "warning")
            return render_template("stock_form.html", stock=stock, products=products, locations=locations), 409

        stock.product_id = product_id
        stock.location_id = location_id
        stock.quantity = quantity
        db.session.commit()
        return redirect(url_for("stock.stock_list"))

    return render_template("stock_form.html", stock=stock, products=products, locations=locations)
