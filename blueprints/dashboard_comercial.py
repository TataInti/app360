from flask import Blueprint, render_template
from security import protect_blueprint

dashboard_com_bp = Blueprint("dashboard_comercial", __name__)

protect_blueprint(dashboard_com_bp, "dashboard_comercial")


@dashboard_com_bp.route("/dashboard-comercial")
def dashboard_comercial():
    return render_template("dashboard_comercial.html")
