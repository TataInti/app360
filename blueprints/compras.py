from datetime import datetime
import io
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from models import (
    InstrumentoPago,
    Location,
    MovimientoCaja,
    Product,
    Proveedor,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    StockLevel,
    User,
    db,
)
from models.time_utils import today_local_date
from security import protect_blueprint

compras_bp = Blueprint("compras", __name__)

protect_blueprint(compras_bp, "compras")

ORDER_STATUSES = ["borrador", "enviada", "recibida", "cerrada"]


@compras_bp.route("/compras")
def compras_home():
    # Listado simple de órdenes de compra
    try:
        orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    except Exception:
        # Fallback si created_at no existe en la DB
        orders = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).all()
    return render_template(
        "compras_panel.html",
        orders=orders,
        statuses=ORDER_STATUSES,
    )


@compras_bp.route("/compras/orden-nueva", methods=["GET", "POST"])
def compras_nueva():
    products = Product.query.all()
    locations = Location.query.all()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    instrumentos = InstrumentoPago.query.filter_by(activo=True).order_by(InstrumentoPago.nombre).all()
    default_date = today_local_date().strftime("%Y-%m-%d")

    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        supplier_text = request.form.get("supplier_text")
        location_id = int(request.form["location_id"])
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])
        notes = request.form.get("notes")
        order_date_raw = request.form.get("order_date")
        comprobante_numero = request.form.get("comprobante_numero")
        instrumento_id = request.form.get("instrumento_id")
        monto_total_raw = request.form.get("monto_total")

        supplier_id = int(supplier_id) if supplier_id else None
        supplier = None
        if supplier_id:
            proveedor = Proveedor.query.get(supplier_id)
            if not proveedor:
                flash("Proveedor no encontrado.", "warning")
                return render_template(
                    "compras_orden_nueva.html",
                    products=products,
                    locations=locations,
                    proveedores=proveedores,
                    instrumentos=instrumentos,
                    default_date=default_date,
                )
            supplier = proveedor.nombre
        else:
            supplier = supplier_text

        order_date = None
        if order_date_raw:
            order_date = datetime.strptime(order_date_raw, "%Y-%m-%d").date()

        monto_total = None
        if monto_total_raw:
            try:
                monto_total = Decimal(monto_total_raw)
            except InvalidOperation:
                flash("Monto inválido.", "warning")
                return render_template(
                    "compras_orden_nueva.html",
                    products=products,
                    locations=locations,
                    proveedores=proveedores,
                    instrumentos=instrumentos,
                    default_date=default_date,
                )

        instrumento_id = int(instrumento_id) if instrumento_id else None

        if instrumento_id and (monto_total is None or monto_total <= 0):
            flash("Monto requerido para generar el egreso de tesorería.", "warning")
            return render_template(
                "compras_orden_nueva.html",
                products=products,
                locations=locations,
                proveedores=proveedores,
                instrumentos=instrumentos,
                default_date=default_date,
            )

        # Creamos la orden
        po = PurchaseOrder(
            supplier=supplier,
            supplier_id=supplier_id,
            location_id=location_id,
            status="borrador",
            notes=notes,
            order_date=order_date,
            comprobante_numero=comprobante_numero,
            monto_total=monto_total,
            instrumento_id=instrumento_id,
        )
        db.session.add(po)
        db.session.flush()  # para obtener po.id

        # Creamos 1 ítem (MVP: una línea por OC)
        item = PurchaseOrderItem(order_id=po.id, product_id=product_id, quantity=quantity)
        db.session.add(item)

        if instrumento_id and monto_total:
            usuario_id = None
            session_user = session.get("user")
            if session_user:
                usuario = User.query.filter_by(username=session_user).first()
                if usuario:
                    usuario_id = usuario.id
            if not usuario_id:
                flash("No se pudo identificar el usuario para registrar el egreso.", "warning")
            else:
                movimiento = MovimientoCaja(
                    tipo="egreso",
                    monto=monto_total,
                    descripcion=f"Registro de compras #{po.id}",
                    instrumento_id=instrumento_id,
                    usuario_id=usuario_id,
                    referencia=comprobante_numero,
                    cliente_proveedor=supplier,
                )
                db.session.add(movimiento)
                db.session.flush()
                po.tesoreria_movimiento_id = movimiento.id

        db.session.commit()

        return redirect(url_for("compras.compras_home"))

    return render_template(
        "compras_orden_nueva.html",
        products=products,
        locations=locations,
        proveedores=proveedores,
        instrumentos=instrumentos,
        default_date=default_date,
    )


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


@compras_bp.route("/compras/exportar", methods=["GET"])
def compras_exportar():
    try:
        import pandas as pd
    except ImportError:
        flash("Pandas no instalado para exportar.", "warning")
        return redirect(url_for("compras.compras_home"))

    orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()

    data = []
    for o in orders:
        fecha = o.order_date or (o.created_at.date() if o.created_at else None)
        data.append({
            "ID": o.id,
            "Fecha": fecha.isoformat() if fecha else "",
            "Proveedor": o.supplier or "",
            "Comprobante": o.comprobante_numero or "",
            "Monto": float(o.monto_total) if o.monto_total is not None else "",
            "Ubicacion": o.location.name if o.location else "",
            "Estado": o.status or "",
            "Items": len(o.items) if o.items else 0,
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Compras", index=False)
    output.seek(0)

    filename = f"compras_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )
