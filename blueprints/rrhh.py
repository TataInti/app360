from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func

from models import (
    db,
    Headcount,
    Absence,
    Location,
    Employee,
    Attendance,
    Goal,
    Survey,
    SurveyResponse,
)
from security import protect_blueprint

rrhh_bp = Blueprint("rrhh", __name__)

protect_blueprint(rrhh_bp, "rrhh")

def _parse_date(value):
    if not value:
        return date.today()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return date.today()


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@rrhh_bp.route("/rrhh")
def rrhh_home():
    total_headcount = db.session.query(func.sum(Headcount.headcount)).scalar() or 0
    total_days_lost = db.session.query(func.sum(Absence.days_lost)).scalar() or 0
    total_employees = Employee.query.filter_by(active=True).count()
    attendance_today = Attendance.query.filter_by(date=date.today()).count()
    survey_avg = db.session.query(func.avg(SurveyResponse.score)).scalar() or 0
    avg_absence = round(total_days_lost / total_headcount, 2) if total_headcount else 0

    latest_surveys = Survey.query.order_by(Survey.start_date.desc()).limit(3).all()

    return render_template(
        "rrhh_panel.html",
        total_headcount=total_headcount,
        total_days_lost=total_days_lost,
        avg_absence=avg_absence,
        total_employees=total_employees,
        attendance_today=attendance_today,
        survey_avg=round(survey_avg, 2) if survey_avg else 0,
        latest_surveys=latest_surveys,
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


@rrhh_bp.route("/rrhh/empleados", methods=["GET", "POST"])
def rrhh_empleados():
    locations = Location.query.order_by(Location.name).all()
    employees = Employee.query.order_by(Employee.full_name).all()

    if request.method == "POST":
        employee = Employee(
            full_name=request.form["full_name"],
            role=request.form.get("role"),
            location_id=request.form.get("location_id") or None,
            email=request.form.get("email"),
            active=request.form.get("active") == "on"
        )
        db.session.add(employee)
        db.session.commit()
        flash("Empleado registrado.", "success")
        return redirect(url_for("rrhh.rrhh_empleados"))

    return render_template(
        "rrhh_empleados.html",
        employees=employees,
        locations=locations
    )


@rrhh_bp.route("/rrhh/asistencia", methods=["GET", "POST"])
def rrhh_asistencia():
    employees = Employee.query.filter_by(active=True).order_by(Employee.full_name).all()
    attendances = Attendance.query.order_by(Attendance.date.desc(), Attendance.check_in.desc()).limit(20).all()

    if request.method == "POST":
        employee_id = int(request.form["employee_id"])
        attendance = Attendance(
            employee_id=employee_id,
            date=_parse_date(request.form.get("date")),
            check_in=_parse_datetime(request.form.get("check_in")),
            check_out=_parse_datetime(request.form.get("check_out")),
            notes=request.form.get("notes")
        )
        db.session.add(attendance)
        db.session.commit()
        flash("Asistencia registrada.", "success")
        return redirect(url_for("rrhh.rrhh_asistencia"))

    return render_template(
        "rrhh_asistencia.html",
        employees=employees,
        attendances=attendances
    )


@rrhh_bp.route("/rrhh/objetivos", methods=["GET", "POST"])
def rrhh_objetivos():
    employees = Employee.query.order_by(Employee.full_name).all()
    goals = Goal.query.order_by(Goal.period.desc()).all()

    if request.method == "POST":
        goal = Goal(
            employee_id=request.form["employee_id"],
            description=request.form["description"],
            period=request.form.get("period"),
            target_value=float(request.form["target_value"]),
            current_value=float(request.form.get("current_value") or 0.0),
            status=request.form.get("status") or "en progreso"
        )
        db.session.add(goal)
        db.session.commit()
        flash("Objetivo registrado.", "success")
        return redirect(url_for("rrhh.rrhh_objetivos"))

    return render_template(
        "rrhh_objetivos.html",
        employees=employees,
        goals=goals
    )


@rrhh_bp.route("/rrhh/clima", methods=["GET", "POST"])
def rrhh_clima():
    surveys = Survey.query.order_by(Survey.start_date.desc()).all()
    responses = SurveyResponse.query.order_by(SurveyResponse.submitted_at.desc()).limit(20).all()

    if request.method == "POST":
        if "survey_name" in request.form:
            survey = Survey(
                name=request.form["survey_name"],
                start_date=_parse_date(request.form.get("start_date")),
                end_date=_parse_date(request.form.get("end_date")),
                location_id=request.form.get("location_id") or None
            )
            db.session.add(survey)
            db.session.commit()
            flash("Encuesta creada.", "success")
            return redirect(url_for("rrhh.rrhh_clima"))
        else:
            response = SurveyResponse(
                survey_id=request.form["survey_id"],
                employee_id=request.form["employee_id"],
                score=int(request.form["score"]),
                comments=request.form.get("comments")
            )
            db.session.add(response)
            db.session.commit()
            flash("Respuesta registrada.", "success")
            return redirect(url_for("rrhh.rrhh_clima"))

    employees = Employee.query.order_by(Employee.full_name).all()
    return render_template(
        "rrhh_clima.html",
        surveys=surveys,
        responses=responses,
        employees=employees,
        locations=Location.query.order_by(Location.name).all()
    )
