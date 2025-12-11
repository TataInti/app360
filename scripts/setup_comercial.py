import os
import sys

# Agregar la carpeta padre (/var/www/silva360) al sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from decimal import Decimal
from datetime import datetime, timedelta

from app import create_app
from models import (
    db,
    BusinessUnit,
    Location,
    Product,
    Campaign,
    Lead,
    LeadInteraction,
    LeadDemo,
    Quotation,
    Sale,
    StockReservation,
)


def get_or_create(model, filters=None, defaults=None):
    filters = filters or {}
    defaults = defaults or {}
    instance = model.query.filter_by(**filters).first()
    if instance:
        return instance

    params = {**filters, **defaults}
    instance = model(**params)
    db.session.add(instance)
    db.session.flush()
    return instance


def seed_business_data():
    units = [
        get_or_create(BusinessUnit, filters={"name": "Autos"}),
        get_or_create(BusinessUnit, filters={"name": "Motos"}),
        get_or_create(BusinessUnit, filters={"name": "Construcción"}),
    ]

    locations = [
        get_or_create(Location, filters={"name": "Sucursal Centro"}, defaults={"type": "sucursal"}),
        get_or_create(Location, filters={"name": "Nave Central"}, defaults={"type": "nave"}),
    ]

    products = [
        get_or_create(
            Product,
            filters={"sku": "AUTO-001"},
            defaults={
                "name": "Sedán Silva 360",
                "business_unit_id": units[0].id,
                "category": "Autos",
            },
        ),
        get_or_create(
            Product,
            filters={"sku": "MOTO-002"},
            defaults={
                "name": "Motocross Silva X",
                "business_unit_id": units[1].id,
                "category": "Motos",
            },
        ),
    ]

    campaign = get_or_create(
        Campaign,
        filters={"name": "Campaña Verano"},
        defaults={
            "channel": "Meta Ads",
            "cost_estimate": Decimal("450000"),
            "start_date": datetime.utcnow().date(),
            "end_date": (datetime.utcnow() + timedelta(days=30)).date(),
            "active": True,
        },
    )

    db.session.commit()
    return units, locations, products, campaign


def seed_demo_lead(units, locations, products, campaign):
    lead = get_or_create(
        Lead,
        filters={"email": "piloto@silva360.ar"},
        defaults={
            "name": "Lead Piloto",
            "phone": "11-5555-1234",
            "source": "Formulario web",
            "status": "contactado",
            "stage": "demo",
            "owner_name": "María Gerente Comercial",
            "last_contacted_at": datetime.utcnow(),
            "business_unit_id": units[0].id,
            "product_id": products[0].id,
            "location_id": locations[0].id,
            "campaign_id": campaign.id,
        },
    )

    get_or_create(
        LeadInteraction,
        filters={"lead_id": lead.id, "type": "Llamada", "owner_name": "María Gerente Comercial"},
        defaults={
            "contact_date": datetime.utcnow() - timedelta(days=1),
            "channel": "Teléfono",
            "notes": "Lead interesado en los sedanes de verano.",
        },
    )

    get_or_create(
        LeadDemo,
        filters={"lead_id": lead.id, "responsible": "María Gerente Comercial"},
        defaults={
            "product_id": products[0].id,
            "location_id": locations[0].id,
            "scheduled_at": datetime.utcnow() + timedelta(days=2),
            "status": "programado",
            "notes": "Test drive en sucursal centro.",
        },
    )

    get_or_create(
        Quotation,
        filters={"lead_id": lead.id, "product_id": products[0].id},
        defaults={
            "amount": Decimal("2120000"),
            "currency": "ARS",
            "status": "borrador",
            "notes": "Cotización inicial enviada por email.",
        },
    )

    db.session.commit()

    get_or_create(
        Sale,
        filters={"lead_id": lead.id, "product_id": products[0].id},
        defaults={
            "location_id": locations[0].id,
            "quantity": 1,
            "unit_price": Decimal("1980000"),
            "currency": "ARS",
            "status": "reserva",
            "scheduled_delivery": datetime.utcnow() + timedelta(days=7),
        },
    )

    sale = Sale.query.filter_by(lead_id=lead.id).first()
    if sale:
        get_or_create(
            StockReservation,
            filters={
                "sale_id": sale.id,
                "product_id": products[0].id,
                "location_id": locations[0].id,
            },
            defaults={"quantity": sale.quantity},
        )

        db.session.commit()


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        units, locations, products, campaign = seed_business_data()
        seed_demo_lead(units, locations, products, campaign)
        print("Base comercial sembrada con unidades, productos, campaña y lead demo.")


if __name__ == "__main__":
    main()
