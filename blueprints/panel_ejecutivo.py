from flask import Blueprint, render_template
from security import protect_blueprint

panel_bp = Blueprint("panel_ejecutivo", __name__)

protect_blueprint(panel_bp, "panel")


@panel_bp.route("/panel-ejecutivo")
def panel_ejecutivo():
    return render_template("panel_ejecutivo.html")
