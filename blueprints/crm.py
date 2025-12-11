from flask import Blueprint, render_template, request, redirect, url_for
from models import db, Lead, BusinessUnit, Product, Location

crm_bp = Blueprint("crm", __name__)

@crm_bp.route("/leads")
def leads_list():
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    units = {u.id: u.name for u in BusinessUnit.query.all()}
    products = {p.id: p.name for p in Product.query.all()}
    locations = {l.id: l.name for l in Location.query.all()}
    return render_template(
        "leads_list.html",
        leads=leads,
        units=units,
        products=products,
        locations=locations
    )

@crm_bp.route("/leads/new", methods=["GET", "POST"])
def leads_new():
    units = BusinessUnit.query.all()
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        lead = Lead(
            name=request.form["name"],
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            source=request.form.get("source", "no especificado"),
            status=request.form.get("status", "nuevo"),
            business_unit_id=request.form["business_unit_id"],
            product_id=request.form.get("product_id"),
            location_id=request.form.get("location_id")
        )
        db.session.add(lead)
        db.session.commit()
        return redirect(url_for("crm.leads_list"))

    return render_template(
        "lead_form.html",
        units=units,
        products=products,
        locations=locations
    )

@crm_bp.route("/leads/edit/<int:lead_id>", methods=["GET", "POST"])
def leads_edit(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    units = BusinessUnit.query.all()
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == "POST":
        lead.name = request.form["name"]
        lead.phone = request.form.get("phone")
        lead.email = request.form.get("email")
        lead.source = request.form.get("source")
        lead.status = request.form.get("status")
        lead.business_unit_id = request.form["business_unit_id"]
        lead.product_id = request.form.get("product_id")
        lead.location_id = request.form.get("location_id")

        db.session.commit()
        return redirect(url_for("crm.leads_list"))

    return render_template(
        "lead_form.html",
        lead=lead,
        units=units,
        products=products,
        locations=locations
    )
