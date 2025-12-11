from decimal import Decimal, InvalidOperation
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from security import protect_blueprint

from models import (
    db,
    Sale,
    Lead,
    Product,
    Location,
    StockReservation,
    StockLevel,
)

ventas_bp = Blueprint("ventas", __name__)

protect_blueprint(ventas_bp, "ventas")

SALE_STATUSES = ["reserva", "en_proceso", "entregada", "cancelada"]


def parse_int(value, default=1):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return default


def parse_decimal(value, default=0):
    try:
        return Decimal(value.replace(",", "."))
    except (AttributeError, InvalidOperation):
        return Decimal(default)


def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@ventas_bp.route("/ventas")
def ventas_list():
    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    return render_template(
        "ventas_list.html",
        sales=sales,
        statuses=SALE_STATUSES,
    )


@ventas_bp.route("/ventas/nuevo", methods=["GET", "POST"])
def ventas_new():
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    products = Product.query.order_by(Product.name).all()
    locations = Location.query.order_by(Location.name).all()

    if request.method == "POST":
        lead_id = request.form.get("lead_id") or None
        product_id = request.form.get("product_id")
        location_id = request.form.get("location_id")
        quantity = parse_int(request.form.get("quantity"))
        unit_price = parse_decimal(request.form.get("unit_price"))
        status = request.form.get("status") or "reserva"
        scheduled = parse_datetime(request.form.get("scheduled_delivery"))

        sale = Sale(
            lead_id=lead_id,
            product_id=product_id,
            location_id=location_id,
            quantity=quantity,
            unit_price=unit_price,
            currency=request.form.get("currency", "ARS"),
            status=status if status in SALE_STATUSES else "reserva",
            scheduled_delivery=scheduled,
        )

        db.session.add(sale)
        db.session.flush()

        reservation = StockReservation(
            sale=sale,
            product_id=product_id,
            location_id=location_id,
            quantity=quantity,
        )
        db.session.add(reservation)

        if lead_id:
            lead = Lead.query.get(lead_id)
            if lead:
                lead.status = "ganado"

        db.session.commit()
        flash("Venta registrada y stock reservado.", "success")
        return redirect(url_for("ventas.ventas_detail", sale_id=sale.id))

    return render_template(
        "ventas_form.html",
        leads=leads,
        products=products,
        locations=locations,
        statuses=SALE_STATUSES,
    )


@ventas_bp.route("/ventas/<int:sale_id>")
def ventas_detail(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    stock_levels = StockLevel.query.filter_by(
        product_id=sale.product_id, location_id=sale.location_id
    ).first()

    return render_template(
        "venta_detail.html",
        sale=sale,
        stock_level=stock_levels.quantity if stock_levels else 0,
        statuses=SALE_STATUSES,
    )


@ventas_bp.route("/ventas/<int:sale_id>/reservas/nueva", methods=["POST"])
def ventas_reservation_new(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    quantity = parse_int(request.form.get("quantity"))
    reservation = StockReservation(
        sale=sale,
        product_id=sale.product_id,
        location_id=sale.location_id,
        quantity=quantity,
    )

    db.session.add(reservation)
    db.session.commit()
    flash("Reserva adicional registrada.", "success")
    return redirect(url_for("ventas.ventas_detail", sale_id=sale.id))


@ventas_bp.route("/ventas/<int:sale_id>/estado", methods=["POST"])
def ventas_update_status(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    status = request.form.get("status")
    if status in SALE_STATUSES:
        sale.status = status
        db.session.commit()
        flash("Estado de la venta actualizado.", "success")
    else:
        flash("Estado inválido.", "warning")
    return redirect(url_for("ventas.ventas_detail", sale_id=sale.id))
