from datetime import datetime
from decimal import Decimal, InvalidOperation
import csv
import io

from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify, send_file

from models import (
    Client,
    Lead,
    Location,
    Product,
    Sale,
    StockLevel,
    StockReservation,
    Venta,
    db,
)
from security import protect_blueprint

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


# Endpoints para SGAC - Ventas Integradas

@ventas_bp.route("/api/ventas/importar", methods=["POST"])
def ventas_importar():
    """Importar ventas desde archivo CSV del ERP legacy"""
    if "file" not in request.files:
        return jsonify({"error": "No se encontró archivo"}), 400

    file = request.files["file"]
    if file.filename == "" or not file.filename.endswith(".csv"):
        return jsonify({"error": "Archivo CSV requerido"}), 400

    try:
        # Leer CSV
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        csv_reader = csv.DictReader(stream)

        ventas_importadas = 0
        errores = []

        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # Homologar columnas (asumiendo nombres estándar)
                fecha_str = row.get("fecha", row.get("date", ""))
                cliente_codigo = row.get("cliente", row.get("client_code", ""))
                producto_sku = row.get("producto", row.get("product_sku", ""))
                cantidad_str = row.get("cantidad", row.get("quantity", ""))
                precio_contrato_str = row.get("precio_contrato", row.get("contract_price", ""))
                precio_efectivo_str = row.get("precio_efectivo", row.get("effective_price", ""))

                # Validar datos requeridos
                if not all([fecha_str, cliente_codigo, producto_sku, cantidad_str, precio_contrato_str, precio_efectivo_str]):
                    errores.append(f"Fila {row_num}: Datos incompletos")
                    continue

                # Parsear fecha
                try:
                    fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                except ValueError:
                    errores.append(f"Fila {row_num}: Fecha inválida")
                    continue

                # Parsear números
                try:
                    cantidad = int(cantidad_str)
                    precio_contrato = Decimal(precio_contrato_str.replace(",", "."))
                    precio_efectivo = Decimal(precio_efectivo_str.replace(",", "."))
                except (ValueError, InvalidOperation):
                    errores.append(f"Fila {row_num}: Valores numéricos inválidos")
                    continue

                # Buscar o crear cliente
                cliente = Client.query.filter_by(code=cliente_codigo).first()
                if not cliente:
                    cliente = Client(name=cliente_codigo, code=cliente_codigo)
                    db.session.add(cliente)
                    db.session.flush()

                # Buscar producto
                producto = Product.query.filter_by(sku=producto_sku).first()
                if not producto:
                    errores.append(f"Fila {row_num}: Producto {producto_sku} no encontrado")
                    continue

                # Crear venta
                venta = Venta(
                    fecha=fecha,
                    cliente_id=cliente.id,
                    producto_id=producto.id,
                    cantidad=cantidad,
                    precio_contrato=precio_contrato,
                    precio_efectivo=precio_efectivo
                )
                db.session.add(venta)
                ventas_importadas += 1

            except Exception as e:
                errores.append(f"Fila {row_num}: {str(e)}")

        db.session.commit()

        return jsonify({
            "message": f"Importación completada. {ventas_importadas} ventas importadas.",
            "importadas": ventas_importadas,
            "errores": errores
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en importación: {str(e)}"}), 500


@ventas_bp.route("/api/ventas/listar", methods=["GET"])
def ventas_listar():
    """Listar ventas importadas con filtros"""
    # Filtros
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    cliente_id = request.args.get("cliente_id")
    producto_id = request.args.get("producto_id")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    query = Venta.query

    if fecha_desde:
        query = query.filter(Venta.fecha >= datetime.strptime(fecha_desde, "%Y-%m-%d").date())
    if fecha_hasta:
        query = query.filter(Venta.fecha <= datetime.strptime(fecha_hasta, "%Y-%m-%d").date())
    if cliente_id:
        query = query.filter(Venta.cliente_id == cliente_id)
    if producto_id:
        query = query.filter(Venta.producto_id == producto_id)

    # Paginación
    ventas = query.order_by(Venta.fecha.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "ventas": [{
            "id": v.id,
            "fecha": v.fecha.isoformat(),
            "cliente": v.cliente.name,
            "producto": v.producto.name,
            "cantidad": v.cantidad,
            "precio_contrato": float(v.precio_contrato),
            "precio_efectivo": float(v.precio_efectivo),
            "margen": float(v.precio_efectivo - v.precio_contrato)
        } for v in ventas.items],
        "total": ventas.total,
        "pages": ventas.pages,
        "current_page": ventas.page
    })


@ventas_bp.route("/api/ventas/exportar", methods=["GET"])
def ventas_exportar():
    """Exportar ventas filtradas a Excel"""
    # Aplicar mismos filtros que listar
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    cliente_id = request.args.get("cliente_id")
    producto_id = request.args.get("producto_id")

    query = Venta.query

    if fecha_desde:
        query = query.filter(Venta.fecha >= datetime.strptime(fecha_desde, "%Y-%m-%d").date())
    if fecha_hasta:
        query = query.filter(Venta.fecha <= datetime.strptime(fecha_hasta, "%Y-%m-%d").date())
    if cliente_id:
        query = query.filter(Venta.cliente_id == cliente_id)
    if producto_id:
        query = query.filter(Venta.producto_id == producto_id)

    ventas = query.order_by(Venta.fecha.desc()).all()

    # Crear CSV en memoria
    output = io.StringIO()
    writer = csv.writer(output)

    # Headers
    writer.writerow([
        "Fecha", "Cliente", "Producto", "Cantidad",
        "Precio Contrato", "Precio Efectivo", "Margen"
    ])

    # Datos
    for v in ventas:
        writer.writerow([
            v.fecha.isoformat(),
            v.cliente.name,
            v.producto.name,
            v.cantidad,
            float(v.precio_contrato),
            float(v.precio_efectivo),
            float(v.precio_efectivo - v.precio_contrato)
        ])

    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="ventas_exportadas.csv"
    )
