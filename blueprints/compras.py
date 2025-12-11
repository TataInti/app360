from flask import Blueprint, render_template, request, redirect, url_for
from models import db, PurchaseOrder, PurchaseOrderItem, Product, Location

compras_bp = Blueprint("compras", __name__)

@compras_bp.route("/compras")
def compras_home():
    # Listado simple de órdenes de compra
    orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    return render_template("compras_panel.html", orders=orders)

@compras_bp.route("/compras/orden-nueva", methods=["GET", "POST"])
def compras_nueva():
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        supplier = request.form.get("supplier")
        location_id = int(request.form["location_id"])
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])
        notes = request.form.get("notes")

        # Creamos la orden
        po = PurchaseOrder(
            supplier=supplier,
            location_id=location_id,
            status="borrador",
            notes=notes
        )
        db.session.add(po)
        db.session.flush()  # para obtener po.id

        # Creamos 1 ítem (MVP: una línea por OC)
        item = PurchaseOrderItem(
            order_id=po.id,
            product_id=product_id,
            quantity=quantity
        )
        db.session.add(item)

        db.session.commit()

        return redirect(url_for("compras.compras_home"))

    return render_template(
        "compras_orden_nueva.html",
        products=products,
        locations=locations
    )
