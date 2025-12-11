from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Headcount, Absence, Location
from sqlalchemy import func

rrhh_bp = Blueprint("rrhh", __name__)

@rrhh_bp.route("/rrhh")
def rrhh_home():
    # KPIs simples
    total_headcount = db.session.query(func.sum(Headcount.headcount)).scalar() or 0
    total_days_lost = db.session.query(func.sum(Absence.days_lost)).scalar() or 0

    # Ausentismo promedio (muy simple: días perdidos / dotación total, sin periodo)
    avg_absence = 0
    if total_headcount > 0:
        avg_absence = round(total_days_lost / total_headcount, 2)

    return render_template(
        "rrhh_panel.html",
        total_headcount=total_headcount,
        total_days_lost=total_days_lost,
        avg_absence=avg_absence
    )

@rrhh_bp.route("/rrhh/dotacion", methods=["GET", "POST"])
def rrhh_dotacion():
    locations = Location.query.all()

    if request.method == "POST":
        location_id = int(request.form["location_id"])
        month = request.form["month"]  # 'YYYY-MM'
        headcount = int(request.form["headcount"])

        # Si ya hay registro para esa ubicación y mes, lo actualizamos
        existing = Headcount.query.filter_by(location_id=location_id, month=month).first()
        if existing:
            existing.headcount = headcount
        else:
            rec = Headcount(location_id=location_id, month=month, headcount=headcount)
            db.session.add(rec)

        db.session.commit()
        return redirect(url_for("rrhh.rrhh_dotacion"))

    # Listado
    rows = (
        db.session.query(Headcount, Location)
        .join(Location, Headcount.location_id == Location.id)
        .order_by(Headcount.month.desc())
        .all()
    )

    return render_template(
        "rrhh_dotacion.html",
        rows=rows,
        locations=locations
    )

@rrhh_bp.route("/rrhh/ausentismo", methods=["GET", "POST"])
def rrhh_ausentismo():
    locations = Location.query.all()

    if request.method == "POST":
        location_id = int(request.form["location_id"])
        month = request.form["month"]
        days_lost = float(request.form["days_lost"])
        notes = request.form.get("notes")

        rec = Absence(
            location_id=location_id,
            month=month,
            days_lost=days_lost,
            notes=notes
        )
        db.session.add(rec)
        db.session.commit()

        return redirect(url_for("rrhh.rrhh_ausentismo"))

    rows = (
        db.session.query(Absence, Location)
        .join(Location, Absence.location_id == Location.id)
        .order_by(Absence.month.desc())
        .all()
    )

    return render_template(
        "rrhh_ausentismo.html",
        rows=rows,
        locations=locations
    )
