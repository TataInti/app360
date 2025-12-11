from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from config import Config
from models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()

        if user and user.check_password(password):
            session["user"] = user.username
            session["role"] = user.role
            flash("Sesión iniciada correctamente.", "success")
            return redirect(url_for("dashboard.dashboard"))

        flash("Usuario o contraseña incorrectos.", "warning")

    return render_template(
        "login.html",
        title=Config.LOGIN_TITLE,
        logo=url_for("static", filename="images/grupo_silva_logo.svg"),
    )


@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
