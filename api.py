# api.py
from flask import Blueprint, jsonify
from sqlalchemy import func

import models as m
from models import db

api = Blueprint("api", __name__, url_prefix="/api")


def get_model(name):
    """Devuelve la clase de modelo si existe, si no None."""
    return getattr(m, name, None)


# -----------------------------------------------------------------------------
#  /api/dashboard
#  Dashboard operativo (equivalente a dashboard.html)
# -----------------------------------------------------------------------------
@api.get("/dashboard")
def api_dashboard():
    Product = get_model("Product")
    Location = get_model("Location")
    Stock = get_model("Stock")

    # Totales
    if Product:
        total_products = db.session.query(func.count(Product.id)).scalar() or 0
    else:
        total_products = 0

    if Location:
        total_locations = db.session.query(func.count(Location.id)).scalar() or 0
    else:
        total_locations = 0

    if Stock:
        total_stock_records = db.session.query(func.count(Stock.id)).scalar() or 0
    else:
        total_stock_records = 0

    # Stock por unidad de negocio
    stock_per_unit = []
    if Product and Stock and hasattr(Product, "business_unit_id"):
        rows_unit = (
            db.session.query(Product.business_unit_id, func.sum(Stock.quantity))
            .join(Stock, Stock.product_id == Product.id)
            .group_by(Product.business_unit_id)
            .all()
        )

        for bu_id, qty in rows_unit:
            label = f"Unidad {bu_id}" if bu_id is not None else "Sin unidad"
            stock_per_unit.append([label, int(qty or 0)])

    # Stock por ubicación
    stock_per_location = []
    if Location and Stock:
        rows_loc = (
            db.session.query(Location.name, func.sum(Stock.quantity))
            .join(Stock, Stock.location_id == Location.id)
            .group_by(Location.name)
            .all()
        )

        stock_per_location = [[name, int(qty or 0)] for name, qty in rows_loc]

    return jsonify(
        {
            "total_products": int(total_products),
            "total_locations": int(total_locations),
            "total_stock_records": int(total_stock_records),
            "stock_per_unit": stock_per_unit,
            "stock_per_location": stock_per_location,
        }
    )


# -----------------------------------------------------------------------------
#  /api/dashboard-comercial
#  Dashboard Comercial (equivalente a dashboard_comercial.html)
# -----------------------------------------------------------------------------
@api.get("/dashboard-comercial")
def api_dashboard_comercial():
    Lead = get_model("Lead")

    if Lead:
        total_leads = db.session.query(func.count(Lead.id)).scalar() or 0

        # Leads por estado
        estados_rows = (
            db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
        )
        leads_por_estado = {status or "sin_estado": int(qty or 0) for status, qty in estados_rows}

        # Leads por unidad de negocio
        leads_por_unidad = []
        if hasattr(Lead, "business_unit_id"):
            unidad_rows = (
                db.session.query(Lead.business_unit_id, func.count(Lead.id))
                .group_by(Lead.business_unit_id)
                .all()
            )
            for bu_id, qty in unidad_rows:
                label = f"Unidad {bu_id}" if bu_id is not None else "Sin unidad"
                leads_por_unidad.append([label, int(qty or 0)])

        # Leads por origen
        origen_rows = db.session.query(Lead.source, func.count(Lead.id)).group_by(Lead.source).all()
        leads_por_origen = [[source or "Sin origen", int(qty or 0)] for source, qty in origen_rows]

    else:
        # Si ni siquiera existe Lead, devolvemos todo en cero
        total_leads = 0
        leads_por_estado = {}
        leads_por_unidad = []
        leads_por_origen = []

    # Conversión (ganado / total)
    ganados = leads_por_estado.get("ganado", 0)
    conversion = round((ganados / total_leads) * 100, 2) if total_leads else 0.0

    return jsonify(
        {
            "total_leads": int(total_leads),
            "leads_por_estado": leads_por_estado,
            "conversion": float(conversion),
            "leads_por_unidad": leads_por_unidad,
            "leads_por_origen": leads_por_origen,
        }
    )


# -----------------------------------------------------------------------------
#  /api/panel-ejecutivo
#  Panel Ejecutivo Global (equivalente a panel_ejecutivo.html)
# -----------------------------------------------------------------------------
@api.get("/panel-ejecutivo")
def api_panel_ejecutivo():
    Product = get_model("Product")
    Location = get_model("Location")
    Lead = get_model("Lead")
    Stock = get_model("Stock")

    # Totales
    if Lead:
        total_leads = db.session.query(func.count(Lead.id)).scalar() or 0
    else:
        total_leads = 0

    if Product:
        total_products = db.session.query(func.count(Product.id)).scalar() or 0
    else:
        total_products = 0

    if Location:
        total_locations = db.session.query(func.count(Location.id)).scalar() or 0
    else:
        total_locations = 0

    # Leads por estado
    leads_por_estado = {}
    if Lead:
        estados_rows = (
            db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
        )
        leads_por_estado = {status or "sin_estado": int(qty or 0) for status, qty in estados_rows}

    ganados = leads_por_estado.get("ganado", 0)
    conversion = round((ganados / total_leads) * 100, 2) if total_leads else 0.0

    # Stock por unidad de negocio
    stock_por_unidad = []
    if Product and Stock and hasattr(Product, "business_unit_id"):
        stock_unidad_rows = (
            db.session.query(Product.business_unit_id, func.sum(Stock.quantity))
            .join(Stock, Stock.product_id == Product.id)
            .group_by(Product.business_unit_id)
            .all()
        )
        for bu_id, qty in stock_unidad_rows:
            label = f"Unidad {bu_id}" if bu_id is not None else "Sin unidad"
            stock_por_unidad.append([label, int(qty or 0)])

    # Productos con stock bajo (ej: menos de 10 unidades)
    stock_bajo = []
    if Product and Stock:
        stock_bajo_rows = (
            db.session.query(Product.name, func.sum(Stock.quantity))
            .join(Stock, Stock.product_id == Product.id)
            .group_by(Product.id)
            .having(func.sum(Stock.quantity) < 10)
            .all()
        )
        stock_bajo = [[name, int(qty or 0)] for name, qty in stock_bajo_rows]

    return jsonify(
        {
            "total_leads": int(total_leads),
            "total_products": int(total_products),
            "total_locations": int(total_locations),
            "conversion": float(conversion),
            "leads_por_estado": leads_por_estado,
            "stock_por_unidad": stock_por_unidad,
            "stock_bajo": stock_bajo,
        }
    )
