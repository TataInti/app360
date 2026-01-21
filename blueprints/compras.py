from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import (
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    StockLevel,
    db,
)
from security import protect_blueprint

compras_bp = Blueprint("compras", __name__)

protect_blueprint(compras_bp, "compras")

ORDER_STATUSES = ["borrador", "enviada", "recibida", "cerrada"]


@compras_bp.route("/compras")
def compras_home():
    # Listado simple de órdenes de compra
    orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    return render_template(
        "compras_panel.html",
        orders=orders,
        statuses=ORDER_STATUSES,
    )


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
            supplier=supplier, location_id=location_id, status="borrador", notes=notes
        )
        db.session.add(po)
        db.session.flush()  # para obtener po.id

        # Creamos 1 ítem (MVP: una línea por OC)
        item = PurchaseOrderItem(order_id=po.id, product_id=product_id, quantity=quantity)
        db.session.add(item)

        db.session.commit()

        return redirect(url_for("compras.compras_home"))

    return render_template("compras_orden_nueva.html", products=products, locations=locations)


@compras_bp.route("/compras/<int:order_id>")
def compras_detail(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    return render_template(
        "compras_detail.html",
        order=order,
        statuses=ORDER_STATUSES,
    )


@compras_bp.route("/compras/<int:order_id>/estado", methods=["POST"])
def compras_change_status(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    status = request.form.get("status")

    if status in ORDER_STATUSES:
        order.status = status
        db.session.commit()
        flash("Estado actualizado.", "success")
    else:
        flash("Estado inválido.", "warning")

    return redirect(url_for("compras.compras_detail", order_id=order_id))


@compras_bp.route("/compras/<int:order_id>/recepciones", methods=["POST"])
def compras_add_receipt(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    quantity = int(request.form.get("quantity", 0))

    if quantity <= 0:
        flash("Cantidad inválida.", "warning")
        return redirect(url_for("compras.compras_detail", order_id=order_id))

    receipt = PurchaseReceipt(
        order=order,
        product_id=(
            request.form.get("product_id") or order.items[0].product_id if order.items else None
        ),
        location_id=order.location_id,
        quantity_received=quantity,
    )
    db.session.add(receipt)

    stock = StockLevel.query.filter_by(
        product_id=receipt.product_id, location_id=receipt.location_id
    ).first()
    if not stock:
        stock = StockLevel(
            product_id=receipt.product_id, location_id=receipt.location_id, quantity=0
        )
        db.session.add(stock)

    stock.quantity += receipt.quantity_received
    db.session.commit()
    flash("Recepción registrada y stock actualizado.", "success")
    return redirect(url_for("compras.compras_detail", order_id=order_id))
