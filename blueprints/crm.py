from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from models import (
    BusinessUnit,
    Campaign,
    Lead,
    LeadDemo,
    LeadInteraction,
    LeadStage,
    LeadStageHistory,
    Location,
    Product,
    Quotation,
    db,
)
from security import protect_blueprint
from services.importes import MAXIMO_NUMERIC_12_2, ImporteInvalido, parse_importe

crm_bp = Blueprint("crm", __name__)

protect_blueprint(crm_bp, "crm")

DEFAULT_PIPELINE_STAGES = [
    {"name": "nuevo"},
    {"name": "contactado"},
    {"name": "propuesta"},
    {"name": "cierre"},
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


def _id_opcional(valor):
    """ID de una fila relacionada: None si el campo viene vacío; ValueError si no es un entero positivo."""
    texto = (valor or "").strip()
    if not texto:
        return None
    if not texto.isdigit() or int(texto) <= 0:
        raise ValueError("id inválido")
    return int(texto)


def load_pipeline_stages():
    stages = (
        LeadStage.query.filter_by(activo=True)
        .order_by(LeadStage.position.asc(), LeadStage.id.asc())
        .all()
    )
    if not stages:
        return DEFAULT_PIPELINE_STAGES
    if len(stages) > 4:
        stages = stages[:4]
    return [{"name": stage.name, "id": stage.id} for stage in stages]


def stage_names(stages):
    return [stage["name"] for stage in stages]


@crm_bp.route("/leads")
def leads_list():
    view_mode = request.args.get("view", "kanban")
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    stages = load_pipeline_stages()
    active_stage_names = stage_names(stages)
    leads_by_stage = {name: [] for name in active_stage_names}
    fallback_stage = active_stage_names[0] if active_stage_names else "nuevo"

    for lead in leads:
        stage_name = lead.stage if lead.stage in leads_by_stage else fallback_stage
        leads_by_stage[stage_name].append(lead)

    units = {u.id: u.name for u in BusinessUnit.query.all()}
    products = {p.id: p.name for p in Product.query.all()}
    locations = {location.id: location.name for location in Location.query.all()}
    campaigns = {c.id: c.name for c in Campaign.query.all()}
    return render_template(
        "leads_list.html",
        leads=leads,
        stages=stages,
        leads_by_stage=leads_by_stage,
        view_mode=view_mode,
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
    stages = load_pipeline_stages()
    active_stage_names = stage_names(stages)

    if request.method == "POST":
        try:
            business_unit_id = _id_opcional(request.form.get("business_unit_id"))
            product_id = _id_opcional(request.form.get("product_id"))
            location_id = _id_opcional(request.form.get("location_id"))
            campaign_id = _id_opcional(request.form.get("campaign_id"))
        except ValueError:
            flash("Revisá los selectores del lead: alguno no tiene un valor válido.", "warning")
            return (
                render_template(
                    "lead_form.html",
                    units=units,
                    products=products,
                    locations=locations,
                    campaigns=campaigns,
                    stages=stages,
                ),
                400,
            )
        if business_unit_id is None:
            flash("Elegí una unidad de negocio para el lead.", "warning")
            return (
                render_template(
                    "lead_form.html",
                    units=units,
                    products=products,
                    locations=locations,
                    campaigns=campaigns,
                    stages=stages,
                ),
                400,
            )

        etapa = request.form.get("stage")
        if etapa not in active_stage_names:
            etapa = active_stage_names[0] if active_stage_names else "nuevo"

        lead = Lead(
            name=request.form["name"],
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            source=request.form.get("source", "no especificado"),
            status=request.form.get("status", "nuevo"),
            stage=etapa,
            owner_name=request.form.get("owner_name"),
            last_contacted_at=parse_datetime(request.form.get("last_contacted_at")),
            business_unit_id=business_unit_id,
            product_id=product_id,
            location_id=location_id,
            campaign_id=campaign_id,
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
        stages=stages,
    )


@crm_bp.route("/leads/edit/<int:lead_id>", methods=["GET", "POST"])
def leads_edit(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    units = BusinessUnit.query.all()
    products = Product.query.all()
    locations = Location.query.all()
    campaigns = Campaign.query.all()
    stages = load_pipeline_stages()

    if request.method == "POST":
        previous_stage = lead.stage
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

        if lead.stage != previous_stage:
            history_entry = LeadStageHistory(
                lead=lead,
                from_stage=previous_stage,
                to_stage=lead.stage,
                comment=None,
                created_by=session.get("user"),
            )
            db.session.add(history_entry)

        db.session.commit()
        return redirect(url_for("crm.leads_list"))

    return render_template(
        "lead_form.html",
        lead=lead,
        units=units,
        products=products,
        locations=locations,
        campaigns=campaigns,
        stages=stages,
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
    stages = load_pipeline_stages()

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
        stages=stages,
        channels=INTERACTION_CHANNELS,
    )


@crm_bp.route("/leads/<int:lead_id>/update", methods=["POST"])
def lead_update(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    previous_stage = lead.stage
    try:
        campaign_id = _id_opcional(request.form.get("campaign_id"))
    except ValueError:
        flash("La campaña elegida no es válida.", "warning")
        return redirect(url_for("crm.lead_detail", lead_id=lead.id))
    etapa = request.form.get("stage")
    if etapa in stage_names(load_pipeline_stages()):
        lead.stage = etapa
    lead.owner_name = request.form.get("owner_name")
    lead.status = request.form.get("status", lead.status)
    lead.last_contacted_at = parse_datetime(request.form.get("last_contacted_at"))
    lead.campaign_id = campaign_id

    if lead.stage != previous_stage:
        history_entry = LeadStageHistory(
            lead=lead,
            from_stage=previous_stage,
            to_stage=lead.stage,
            comment=None,
            created_by=session.get("user"),
        )
        db.session.add(history_entry)

    db.session.commit()
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/api/crm/leads/<int:lead_id>/history", methods=["GET"])
def lead_history(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    history = (
        LeadStageHistory.query.filter_by(lead_id=lead.id)
        .order_by(LeadStageHistory.created_at.desc())
        .all()
    )
    return jsonify(
        {
            "history": [
                {
                    "id": entry.id,
                    "from_stage": entry.from_stage,
                    "to_stage": entry.to_stage,
                    "comment": entry.comment,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "created_by": entry.created_by,
                }
                for entry in history
            ]
        }
    )


@crm_bp.route("/api/crm/leads/<int:lead_id>/comments", methods=["POST"])
def lead_comment(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    payload = request.get_json(silent=True) or {}
    comment = (payload.get("comment") or "").strip()
    if not comment:
        return jsonify({"error": "Comentario requerido"}), 400
    if len(comment) > 300:
        return jsonify({"error": "Comentario supera 300 caracteres"}), 400

    history_entry = LeadStageHistory(
        lead=lead,
        from_stage=lead.stage,
        to_stage=lead.stage,
        comment=comment,
        created_by=session.get("user"),
    )
    db.session.add(history_entry)
    db.session.commit()
    return jsonify({"message": "Comentario registrado"})


@crm_bp.route("/api/crm/leads/<int:lead_id>/stage", methods=["POST"])
def lead_stage_update(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    payload = request.get_json(silent=True) or {}
    new_stage = (payload.get("stage") or "").strip()
    comment = (payload.get("comment") or "").strip()

    if not new_stage:
        return jsonify({"error": "Etapa requerida"}), 400
    if comment and len(comment) > 300:
        return jsonify({"error": "Comentario supera 300 caracteres"}), 400

    stages = load_pipeline_stages()
    allowed = set(stage_names(stages))
    if new_stage not in allowed:
        return jsonify({"error": "Etapa no valida"}), 400

    previous_stage = lead.stage
    lead.stage = new_stage

    history_entry = LeadStageHistory(
        lead=lead,
        from_stage=previous_stage,
        to_stage=new_stage,
        comment=comment or None,
        created_by=session.get("user"),
    )
    db.session.add(history_entry)
    db.session.commit()
    return jsonify({"message": "Etapa actualizada"})


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
    try:
        amount = parse_importe(request.form.get("amount"), maximo=MAXIMO_NUMERIC_12_2)
    except ImporteInvalido as error:
        flash(error.mensaje, "warning")
        return redirect(url_for("crm.lead_detail", lead_id=lead.id))

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


def crear_campana_desde_pedido():
    """Validación y persistencia compartidas por el formulario HTML y el panel JSON.

    Reglas que ya aplica el camino HTML: llega el campo name (si falta, respondía 400) y, si
    cost_estimate trae un valor, debe ser un importe válido (si no, avisa y vuelve a la lista).
    Devuelve (campaña, errores); errores es {campo: mensaje}, vacío si se guardó.
    """
    datos = _datos_del_pedido()
    errores = {}
    if "name" not in datos:
        errores["name"] = "Ingresá el nombre de la campaña."
    cost_raw = datos.get("cost_estimate", "")
    cost_value = None
    if cost_raw is not None and not (isinstance(cost_raw, str) and not cost_raw.strip()):
        try:
            cost_value = parse_importe(cost_raw, maximo=MAXIMO_NUMERIC_12_2)
        except ImporteInvalido as error:
            errores["cost_estimate"] = error.mensaje
    if errores:
        return None, errores

    campaign = Campaign(
        name=_texto(datos["name"]),
        channel=_texto(datos.get("channel")),
        cost_estimate=cost_value,
        start_date=parse_date(_texto(datos.get("start_date"))),
        end_date=parse_date(_texto(datos.get("end_date"))),
        active=datos.get("active") == "on",
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign, {}


@crm_bp.route("/campaigns/new", methods=["POST"])
def campaigns_new():
    if _pide_json():
        campana, errores = crear_campana_desde_pedido()
        if errores:
            return jsonify({"ok": False, "errors": errores}), 422
        return jsonify({"ok": True, "id": campana.id, "nombre": campana.name}), 201

    campana, errores = crear_campana_desde_pedido()
    if errores:
        if "name" in errores:
            abort(400)
        flash(next(iter(errores.values())), "warning")
    return redirect(url_for("crm.campaigns_list"))

