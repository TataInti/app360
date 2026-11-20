from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models import Location, Product, StockLevel, db
from security import protect_blueprint

stock_bp = Blueprint("stock", __name__)
protect_blueprint(stock_bp, "stock")

MENSAJE_PRODUCTO_Y_UBICACION = "Elegí un producto y una ubicación."


def _pide_json():
    """El panel lateral declara Accept: application/json; el formulario HTML no lo envía."""
    return "application/json" in request.headers.get("Accept", "")


def _datos_del_pedido():
    """Campos del alta: cuerpo JSON si llega como JSON, o el formulario HTML. Sin csrf_token."""
    if request.is_json:
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            return {}
        return {clave: valor for clave, valor in datos.items() if clave != "csrf_token"}
    return {clave: valor for clave, valor in request.form.items() if clave != "csrf_token"}


def _entero_o_none(valor):
    """Id de producto o ubicación: entero, o None si falta o no es numérico."""
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _cantidad_valida(valor):
    """Cantidad de stock: entero mayor o igual que cero. Negativa o no numérica se rechaza."""
    texto = "" if valor is None else str(valor).strip()
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


def crear_stock_desde_pedido():
    """Validación y persistencia compartidas por el formulario HTML y el panel JSON.

    Devuelve (registro, errores, duplicado). errores es {campo: mensaje}; vacío si se guardó.
    duplicado es True cuando el par producto×ubicación ya tiene stock: el HTML responde 409 y el
    JSON 422, con el aviso en location_id.
    """
    datos = _datos_del_pedido()
    errores = {}
    product_id = _entero_o_none(datos.get("product_id"))
    location_id = _entero_o_none(datos.get("location_id"))
    if product_id is None:
        errores["product_id"] = MENSAJE_PRODUCTO_Y_UBICACION
    if location_id is None:
        errores["location_id"] = MENSAJE_PRODUCTO_Y_UBICACION
    quantity = None
    try:
        quantity = _cantidad_valida(datos.get("quantity"))
    except ValueError as error:
        errores["quantity"] = str(error)
    if errores:
        return None, errores, False

    # Un par producto×ubicación no se duplica: si ya existe, se avisa y no se pisa.
    existing = StockLevel.query.filter_by(product_id=product_id, location_id=location_id).first()
    if existing:
        return None, {"location_id": _mensaje_par_existente(existing)}, True

    registro = StockLevel(product_id=product_id, location_id=location_id, quantity=quantity)
    db.session.add(registro)
    db.session.commit()
    return registro, {}, False


@stock_bp.route("/stock")
def stock_list():
    stock_rows = StockLevel.query.all()
    products = {p.id: p for p in Product.query.all()}
    locations = {location.id: location for location in Location.query.all()}
    return render_template(
        "stock_list.html",
        stock_rows=stock_rows,
        products=products,
        locations=locations,
        catalogo_productos=list(products.values()),
        catalogo_ubicaciones=list(locations.values()),
    )


@stock_bp.route("/stock/new", methods=["GET", "POST"])
def stock_new():
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        if _pide_json():
            registro, errores, _duplicado = crear_stock_desde_pedido()
            if errores:
                return jsonify({"ok": False, "errors": errores}), 422
            return jsonify({
                "ok": True,
                "id": registro.id,
                "producto": registro.product.name if registro.product else "",
                "ubicacion": registro.location.name if registro.location else "",
                "cantidad": registro.quantity,
            }), 201
        registro, errores, duplicado = crear_stock_desde_pedido()
        if errores:
            flash(next(iter(errores.values())), "warning")
            estado = 409 if duplicado else 400
            return render_template("stock_form.html", products=products, locations=locations), estado
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
