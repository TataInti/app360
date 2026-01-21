from flask import Blueprint, redirect, render_template, request, url_for

from models import Location, db

locations_bp = Blueprint("locations", __name__)


@locations_bp.route("/locations")
def list_locations():
    locations = Location.query.all()
    return render_template("locations_list.html", locations=locations)


@locations_bp.route("/locations/new", methods=["GET", "POST"])
def new_location():
    if request.method == "POST":
        name = request.form["name"]
        loc_type = request.form["type"]

        location = Location(name=name, type=loc_type)
        db.session.add(location)
        db.session.commit()

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
