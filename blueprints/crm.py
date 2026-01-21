from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, redirect, render_template, request, url_for

from models import (
    BusinessUnit,
    Campaign,
    Lead,
    LeadDemo,
    LeadInteraction,
    Location,
    Product,
    Quotation,
    db,
)
from security import protect_blueprint

crm_bp = Blueprint("crm", __name__)

protect_blueprint(crm_bp, "crm")

PIPELINE_STAGES = [
    "nuevo",
    "contactado",
    "demo",
    "cotizacion",
    "negociacion",
    "ganado",
    "perdido",
]

INTERACTION_CHANNELS = [
    "Web",
    "Teléfono",
    "WhatsApp",
    "Email",
    "Presencial",
]


def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


@crm_bp.route("/leads")
def leads_list():
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    units = {u.id: u.name for u in BusinessUnit.query.all()}
    products = {p.id: p.name for p in Product.query.all()}
    locations = {location.id: location.name for location in Location.query.all()}
    campaigns = {c.id: c.name for c in Campaign.query.all()}
    return render_template(
        "leads_list.html",
        leads=leads,
        units=units,
        products=products,
        locations=locations,
        campaigns=campaigns,
    )


@crm_bp.route("/leads/new", methods=["GET", "POST"])
def leads_new():
    units = BusinessUnit.query.all()
    products = Product.query.all()
    locations = Location.query.all()
    campaigns = Campaign.query.all()

    if request.method == "POST":
        lead = Lead(
            name=request.form["name"],
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            source=request.form.get("source", "no especificado"),
            status=request.form.get("status", "nuevo"),
            stage=request.form.get("stage", "nuevo"),
            owner_name=request.form.get("owner_name"),
            last_contacted_at=parse_datetime(request.form.get("last_contacted_at")),
            business_unit_id=request.form["business_unit_id"],
            product_id=request.form.get("product_id"),
            location_id=request.form.get("location_id"),
            campaign_id=request.form.get("campaign_id") or None,
        )
        db.session.add(lead)
        db.session.commit()
        return redirect(url_for("crm.leads_list"))

    return render_template(
        "lead_form.html",
        units=units,
        products=products,
        locations=locations,
        campaigns=campaigns,
        stages=PIPELINE_STAGES,
    )


@crm_bp.route("/leads/edit/<int:lead_id>", methods=["GET", "POST"])
def leads_edit(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    units = BusinessUnit.query.all()
    products = Product.query.all()
    locations = Location.query.all()
    campaigns = Campaign.query.all()

    if request.method == "POST":
        lead.name = request.form["name"]
        lead.phone = request.form.get("phone")
        lead.email = request.form.get("email")
        lead.source = request.form.get("source")
        lead.status = request.form.get("status")
        lead.stage = request.form.get("stage", lead.stage)
        lead.owner_name = request.form.get("owner_name")
        lead.last_contacted_at = parse_datetime(request.form.get("last_contacted_at"))
        lead.business_unit_id = request.form["business_unit_id"]
        lead.product_id = request.form.get("product_id")
        lead.location_id = request.form.get("location_id")
        lead.campaign_id = request.form.get("campaign_id") or None

        db.session.commit()
        return redirect(url_for("crm.leads_list"))

    return render_template(
        "lead_form.html",
        lead=lead,
        units=units,
        products=products,
        locations=locations,
        campaigns=campaigns,
        stages=PIPELINE_STAGES,
    )


@crm_bp.route("/leads/<int:lead_id>")
def lead_detail(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    interactions = lead.interactions
    demos = lead.demos
    quotations = lead.quotations
    units = BusinessUnit.query.all()
    products = Product.query.all()
    locations = Location.query.all()
    campaigns = Campaign.query.all()

    return render_template(
        "lead_detail.html",
        lead=lead,
        interactions=interactions,
        demos=demos,
        quotations=quotations,
        units=units,
        products=products,
        locations=locations,
        campaigns=campaigns,
        stages=PIPELINE_STAGES,
        channels=INTERACTION_CHANNELS,
    )


@crm_bp.route("/leads/<int:lead_id>/update", methods=["POST"])
def lead_update(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    lead.stage = request.form.get("stage", lead.stage)
    lead.owner_name = request.form.get("owner_name")
    lead.status = request.form.get("status", lead.status)
    lead.last_contacted_at = parse_datetime(request.form.get("last_contacted_at"))
    campaign_id = request.form.get("campaign_id")
    lead.campaign_id = campaign_id if campaign_id else None

    db.session.commit()
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/interactions/new", methods=["POST"])
def lead_interactions_new(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    interaction = LeadInteraction(
        lead=lead,
        contact_date=parse_datetime(request.form.get("contact_date")) or datetime.utcnow(),
        type=request.form.get("type"),
        channel=request.form.get("channel"),
        owner_name=request.form.get("owner_name"),
        notes=request.form.get("notes"),
    )
    db.session.add(interaction)
    db.session.commit()
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/demos/new", methods=["POST"])
def lead_demos_new(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    demo = LeadDemo(
        lead=lead,
        product_id=request.form["product_id"],
        location_id=request.form.get("location_id") or None,
        scheduled_at=parse_datetime(request.form.get("scheduled_at")) or datetime.utcnow(),
        responsible=request.form.get("responsible"),
        status=request.form.get("status", "programado"),
        notes=request.form.get("notes"),
    )
    db.session.add(demo)
    db.session.commit()
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/quotations/new", methods=["POST"])
def lead_quotations_new(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    amount_raw = request.form.get("amount", "0").replace(",", ".")
    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, TypeError):
        amount = Decimal("0")

    quotation = Quotation(
        lead=lead,
        product_id=request.form["product_id"],
        amount=amount,
        currency=request.form.get("currency", "ARS"),
        status=request.form.get("status", "borrador"),
        notes=request.form.get("notes"),
    )
    db.session.add(quotation)
    db.session.commit()
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/campaigns")
def campaigns_list():
    campaigns = Campaign.query.order_by(Campaign.start_date.desc()).all()
    return render_template("campaigns_list.html", campaigns=campaigns)


@crm_bp.route("/campaigns/new", methods=["POST"])
def campaigns_new():
    cost_raw = request.form.get("cost_estimate", "").replace(",", ".")
    try:
        cost_value = Decimal(cost_raw) if cost_raw else None
    except (InvalidOperation, TypeError):
        cost_value = None

    campaign = Campaign(
        name=request.form["name"],
        channel=request.form.get("channel"),
        cost_estimate=cost_value,
        start_date=parse_date(request.form.get("start_date")),
        end_date=parse_date(request.form.get("end_date")),
        active=request.form.get("active") == "on",
    )

    db.session.add(campaign)
    db.session.commit()
    return redirect(url_for("crm.campaigns_list"))
