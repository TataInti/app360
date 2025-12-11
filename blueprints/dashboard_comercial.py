from flask import Blueprint, render_template
from models import db, Lead, BusinessUnit
from sqlalchemy import func

dashboard_com_bp = Blueprint("dashboard_comercial", __name__)

@dashboard_com_bp.route("/dashboard-comercial")
def dashboard_comercial():

    total_leads = Lead.query.count()

    # Conteo por estado
    estados = ["nuevo", "contactado", "propuesta", "ganado", "perdido"]
    leads_por_estado = {
        estado: Lead.query.filter_by(status=estado).count()
        for estado in estados
    }

    # Conversión (ganados / totales)
    ganados = leads_por_estado["ganado"]
    conversion = round((ganados / total_leads * 100), 2) if total_leads else 0

    # Leads por unidad de negocio
    leads_por_unidad = (
        db.session.query(BusinessUnit.name, func.count(Lead.id))
        .join(Lead, Lead.business_unit_id == BusinessUnit.id)
        .group_by(BusinessUnit.name)
        .all()
    )

    # Origen de leads
    leads_por_origen = (
        db.session.query(Lead.source, func.count(Lead.id))
        .group_by(Lead.source)
        .all()
    )

    return render_template(
        "dashboard_comercial.html",
        total_leads=total_leads,
        leads_por_estado=leads_por_estado,
        conversion=conversion,
        leads_por_unidad=leads_por_unidad,
        leads_por_origen=leads_por_origen
    )
