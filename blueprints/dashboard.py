from flask import Blueprint, redirect, render_template
from security import protect_blueprint

dashboard_bp = Blueprint("dashboard", __name__)

protect_blueprint(dashboard_bp, "dashboard")


@dashboard_bp.route("/dashboard")
def dashboard():
    return redirect("/dashboard-financiero", code=302)


@dashboard_bp.route("/dashboard-financiero")
def dashboard_financiero():
    return render_template("dashboard_financiero.html")
