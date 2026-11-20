from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models import Location, db
from security import protect_blueprint

locations_bp = Blueprint("locations", __name__)
protect_blueprint(locations_bp, "locations")


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


def _texto(valor):
    return "" if valor is None else str(valor)


def crear_ubicacion_desde_pedido():
    """Validación y persistencia compartidas por el formulario HTML y el panel JSON.

    Regla que ya aplica el camino HTML: llegan los campos name y type (si falta alguno, el
    formulario respondía 400). Devuelve (ubicacion, errores); errores es {campo: mensaje}, vacío si se guardó.
    """
    datos = _datos_del_pedido()
    errores = {}
    if "name" not in datos:
        errores["name"] = "Ingresá el nombre de la ubicación."
    if "type" not in datos:
        errores["type"] = "Elegí el tipo de ubicación."
    if errores:
        return None, errores

    ubicacion = Location(name=_texto(datos["name"]), type=_texto(datos["type"]))
    db.session.add(ubicacion)
    db.session.commit()
    return ubicacion, {}


@locations_bp.route("/locations")
def list_locations():
    locations = Location.query.all()
    return render_template("locations_list.html", locations=locations)


@locations_bp.route("/locations/new", methods=["GET", "POST"])
def new_location():
    if request.method == "POST":
        if _pide_json():
            ubicacion, errores = crear_ubicacion_desde_pedido()
            if errores:
                return jsonify({"ok": False, "errors": errores}), 422
            return jsonify({
                "ok": True,
                "id": ubicacion.id,
                "nombre": ubicacion.name,
                "tipo": ubicacion.type,
            }), 201
        ubicacion, errores = crear_ubicacion_desde_pedido()
        if errores:
            flash(next(iter(errores.values())), "warning")
            return render_template("location_form.html"), 400
        return redirect(url_for("locations.list_locations"))

    return render_template("location_form.html")


@locations_bp.route("/locations/edit/<int:location_id>", methods=["GET", "POST"])
def edit_location(location_id):
    location = Location.query.get_or_404(location_id)

    if request.method == "POST":
        location.name = request.form["name"]
        location.type = request.form["type"]
        db.session.commit()

        return redirect(url_for("locations.list_locations"))

    return render_template("location_form.html", location=location)
