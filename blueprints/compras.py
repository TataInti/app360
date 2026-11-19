from datetime import datetime
import io
import uuid
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for

from models.time_utils import now_local
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
from services.importes import MAXIMO_NUMERIC_12_2, ImporteInvalido, parse_importe

compras_bp = Blueprint("compras", __name__)

protect_blueprint(compras_bp, "compras")

ORDER_STATUSES = ["borrador", "enviada", "recibida", "cerrada"]


@compras_bp.route("/compras")
def compras_home():
    return render_template("compras_overview.html")


@compras_bp.route("/compras/listado")
def compras_listado():
    # Listado simple de órdenes de compra
    try:
        orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    except Exception:
        orders = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).all()
    return render_template("compras_panel.html", orders=orders, statuses=ORDER_STATUSES)


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
                monto_total = parse_importe(monto_total_raw, maximo=MAXIMO_NUMERIC_12_2)
            except ImporteInvalido as error:
                flash(error.mensaje, "warning")
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
        total_amount = monto_total if monto_total is not None else Decimal("0")
        unit_price = Decimal("0")
        if quantity:
            try:
                unit_price = (total_amount / Decimal(quantity)).quantize(Decimal("0.01"))
            except Exception:
                unit_price = Decimal("0")

        po = PurchaseOrder(
            supplier=supplier,
            supplier_id=supplier_id,
            location_id=location_id,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
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


def _tokens_recepcion():
    """Tokens del formulario de recepción en la sesión: {token: fecha de emisión ISO}."""
    valor = session.get("recepciones_pendientes")
    return dict(valor) if isinstance(valor, dict) else {}


def _nuevo_token_recepcion():
    """Token del formulario de recepción. Solo vale si la orden no recibió nada después de emitirlo."""
    token = uuid.uuid4().hex
    emitidos = _tokens_recepcion()
    emitidos[token] = now_local().replace(tzinfo=None).isoformat()
    session["recepciones_pendientes"] = dict(list(emitidos.items())[-20:])
    return token


def _pendiente_por_producto(order):
    """Unidades pedidas menos unidades ya recibidas, por producto de la orden."""
    recibido = {}
    for receipt in order.receipts:
        recibido[receipt.product_id] = recibido.get(receipt.product_id, 0) + receipt.quantity_received
    return {
        item.product_id: max(item.quantity - recibido.get(item.product_id, 0), 0)
        for item in order.items
    }


@compras_bp.route("/compras/<int:order_id>")
def compras_detail(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    return render_template(
        "compras_detail.html",
        order=order,
        statuses=ORDER_STATUSES,
        pendientes=_pendiente_por_producto(order),
        recepcion_token=_nuevo_token_recepcion(),
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
    # La fila de la orden queda bloqueada hasta el commit: dos envíos simultáneos van en serie.
    order = db.session.query(PurchaseOrder).with_for_update().filter_by(id=order_id).first()
    if order is None:
        abort(404)
    destino = url_for("compras.compras_detail", order_id=order_id)

    token = request.form.get("recepcion_token", "")
    emitidos = _tokens_recepcion()
    if not token or token not in emitidos:
        flash("Esa recepción ya se registró. Revisá el detalle de la orden antes de cargarla de nuevo.", "warning")
        return redirect(destino)
    emitido = datetime.fromisoformat(emitidos[token])

    # Formulario viejo: si la orden recibió algo después de emitirlo, hay que recargar el detalle.
    ultima = max((r.received_at for r in order.receipts if r.received_at is not None), default=None)
    if ultima is not None and ultima.replace(tzinfo=None) >= emitido:
        emitidos.pop(token, None)
        session["recepciones_pendientes"] = emitidos
        flash("La orden cambió desde que abriste el formulario. Revisá el detalle antes de cargar la recepción.", "warning")
        return redirect(destino)

    try:
        quantity = int(request.form.get("quantity", "0"))
    except ValueError:
        quantity = 0
    if quantity <= 0:
        flash("Cantidad inválida. Ingresá un número entero mayor que cero.", "warning")
        return redirect(destino)

    producto_pedido = request.form.get("product_id") or (order.items[0].product_id if order.items else 0)
    try:
        product_id = int(producto_pedido)
    except (TypeError, ValueError):
        product_id = 0
    pendientes = _pendiente_por_producto(order)
    if product_id not in pendientes:
        flash("El producto elegido no pertenece a esta orden.", "warning")
        return redirect(destino)
    if order.location_id is None:
        flash("La orden no tiene una ubicación de destino para recibir la mercadería.", "warning")
        return redirect(destino)

    pendiente = pendientes[product_id]
    if quantity > pendiente:
        flash(f"No se puede recibir más de lo pendiente: quedan {pendiente} unidades de este producto.", "warning")
        return redirect(destino)

    db.session.add(
        PurchaseReceipt(
            order=order,
            product_id=product_id,
            location_id=order.location_id,
            quantity_received=quantity,
        )
    )
    stock = StockLevel.query.filter_by(product_id=product_id, location_id=order.location_id).first()
    if stock is None:
        stock = StockLevel(product_id=product_id, location_id=order.location_id, quantity=0)
        db.session.add(stock)
    stock.quantity = (stock.quantity or 0) + quantity

    quedan = sum(restante - (quantity if producto == product_id else 0) for producto, restante in pendientes.items())
    if quedan == 0 and order.status in ("borrador", "enviada"):
        order.status = "recibida"
    emitidos.pop(token, None)
    session["recepciones_pendientes"] = emitidos
    db.session.commit()

    if quedan == 0:
        flash("Recepción registrada. La orden quedó recibida y el stock se actualizó.", "success")
    else:
        flash(f"Recepción registrada y stock actualizado. Quedan {quedan} unidades pendientes.", "success")
    return redirect(destino)


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
