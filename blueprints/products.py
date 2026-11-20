from flask import Blueprint, flash, jsonify, render_template, request, redirect, url_for

from sqlalchemy.exc import IntegrityError

from models import BusinessUnit, db
from services.product_service import ProductService
from security import protect_blueprint
from .base_crud import BaseCRUD

products_bp = Blueprint("products", __name__)

# Create CRUD instance
crud = BaseCRUD("products", None, ProductService, "products", ruta_alta="products.new_product")
products_bp = crud.bp
# Incluye las rutas de BaseCRUD (/, /new, /edit/<id>) además de las propias.
protect_blueprint(products_bp, "products")

# Override list to include business units
@products_bp.route("/products")
def list_products():
    products = crud.service.get_all()
    unidades = BusinessUnit.query.all()
    units = {u.id: u.name for u in unidades}
    return render_template("products_list.html", products=products, units=units, unidades=unidades)


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


def crear_producto_desde_pedido():
    """Validación y persistencia compartidas por el formulario HTML y el panel JSON.

    Devuelve (producto, errores). errores es {campo: mensaje}; vacío si se guardó.
    """
    datos = _datos_del_pedido()
    errores = {}
    if not str(datos.get("name") or "").strip():
        errores["name"] = "Ingresá el nombre del producto."
    unidades_ids = {str(u.id) for u in BusinessUnit.query.all()}
    if str(datos.get("business_unit_id") or "") not in unidades_ids:
        errores["business_unit_id"] = "Elegí una unidad de negocio."
    if errores:
        return None, errores
    try:
        producto = crud.service.create(**datos)
    except ValueError as error:
        return None, {"sku": str(error)}
    except IntegrityError:
        db.session.rollback()
        return None, {"sku": "No se pudo guardar el producto. Revisá el SKU y la unidad de negocio."}
    return producto, {}


# Override new to include business units
@products_bp.route("/products/new", methods=["GET", "POST"])
def new_product():
    units = BusinessUnit.query.all()
    if request.method == "POST":
        if _pide_json():
            producto, errores = crear_producto_desde_pedido()
            if errores:
                return jsonify({"ok": False, "errors": errores}), 422
            return jsonify({"ok": True, "id": producto.id, "nombre": producto.name}), 201
        producto, errores = crear_producto_desde_pedido()
        if errores:
            flash(next(iter(errores.values())), "warning")
            return render_template("product_form.html", units=units), 400
        return redirect(url_for("products.list_products"))
    return render_template("product_form.html", units=units)


# Override edit to include business units
@products_bp.route("/products/edit/<int:item_id>", methods=["GET", "POST"])
def edit_product(item_id):
    units = BusinessUnit.query.all()
    product = crud.service.get_by_id(item_id)
    if not product:
        return "Producto no encontrado", 404
    
    if request.method == "POST":
        kwargs = {key: value for key, value in request.form.items() if key != "csrf_token"}
        try:
            crud.service.update(item_id, **kwargs)
        except ValueError as error:
            flash(str(error), "warning")
            return render_template("product_form.html", product=product, units=units), 400
        except IntegrityError:
            db.session.rollback()
            flash("No se pudo guardar el producto. Revisá el SKU y la unidad de negocio.", "warning")
            return render_template("product_form.html", product=product, units=units), 400
        return redirect(url_for("products.list_products"))
    
    return render_template("product_form.html", product=product, units=units)
