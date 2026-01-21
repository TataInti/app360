import os
import random
import sys
from datetime import datetime, timedelta

# Agregar la carpeta padre al sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app import create_app
from models import (
    Attendance,
    BusinessUnit,
    Employee,
    Goal,
    Lead,
    LeadDemo,
    LeadInteraction,
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    Quotation,
    Sale,
    StockLevel,
    StockReservation,
    Survey,
    SurveyResponse,
    db,
)

# Agregar la carpeta padre al sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)


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


def seed_business_entities():
    units = [
        get_or_create(BusinessUnit, filters={"name": "Autos"}),
        get_or_create(BusinessUnit, filters={"name": "Motos"}),
    ]

    locations = [
        get_or_create(Location, filters={"name": "Sucursal Centro"}, defaults={"type": "sucursal"}),
        get_or_create(Location, filters={"name": "Nave Norte"}, defaults={"type": "nave"}),
    ]

    products = [
        get_or_create(
            Product,
            filters={"sku": "AUTO-101"},
            defaults={
                "name": "Sedán Silva E",
                "business_unit_id": units[0].id,
                "category": "Autos Premium",
            },
        ),
        get_or_create(
            Product,
            filters={"sku": "MOTO-201"},
            defaults={
                "name": "Motociclita Silva R",
                "business_unit_id": units[1].id,
                "category": "Motos",
            },
        ),
    ]

    db.session.commit()
    return units, locations, products


def seed_leads(units, locations, products):
    lead_templates = [
        {
            "email": "alejandro@silva360.com",
            "name": "Alejandro Pérez",
            "stage": "contactado",
            "status": "contactado",
            "owner": "María Gerente Comercial",
            "source": "LinkedIn",
            "product": products[0],
            "location": locations[0],
        },
        {
            "email": "veronica@silva360.com",
            "name": "Verónica Luna",
            "stage": "cotizacion",
            "status": "propuesta",
            "owner": "Luis Comercial",
            "source": "Showroom",
            "product": products[1],
            "location": locations[1],
        },
        {
            "email": "mora@silva360.com",
            "name": "Mora Sosa",
            "stage": "ganado",
            "status": "ganado",
            "owner": "María Gerente Comercial",
            "source": "Formulario web",
            "product": products[0],
            "location": locations[0],
        },
    ]

    for template in lead_templates:
        lead = get_or_create(
            Lead,
            filters={"email": template["email"]},
            defaults={
                "name": template["name"],
                "phone": "11-4000-000{}".format(random.randint(0, 9)),
                "source": template["source"],
                "status": template["status"],
                "stage": template["stage"],
                "owner_name": template["owner"],
                "business_unit_id": template["product"].business_unit_id,
                "product_id": template["product"].id,
                "location_id": template["location"].id,
                "last_contacted_at": datetime.utcnow() - timedelta(days=random.randint(1, 5)),
            },
        )

        get_or_create(
            LeadInteraction,
            filters={"lead_id": lead.id, "type": "email", "owner_name": lead.owner_name},
            defaults={
                "contact_date": datetime.utcnow() - timedelta(days=1),
                "channel": "Email",
                "notes": "Seguimiento de interés en promociones.",
            },
        )

        get_or_create(
            LeadDemo,
            filters={"lead_id": lead.id},
            defaults={
                "product_id": template["product"].id,
                "location_id": template["location"].id,
                "scheduled_at": datetime.utcnow() + timedelta(days=2),
                "responsible": template["owner"],
            },
        )

        get_or_create(
            Quotation,
            filters={"lead_id": lead.id, "product_id": template["product"].id},
            defaults={
                "amount": 1500000 + random.randint(0, 50000),
                "currency": "ARS",
                "status": "propuesta",
            },
        )

        if template["stage"] in ("ganado", "cotizacion"):
            sale = get_or_create(
                Sale,
                filters={"lead_id": lead.id},
                defaults={
                    "product_id": template["product"].id,
                    "location_id": template["location"].id,
                    "quantity": random.randint(1, 2),
                    "unit_price": 1500000,
                    "status": "reserva",
                    "scheduled_delivery": datetime.utcnow() + timedelta(days=10),
                },
            )
            get_or_create(
                StockReservation,
                filters={"sale_id": sale.id, "product_id": sale.product_id},
                defaults={"location_id": sale.location_id, "quantity": sale.quantity},
            )

    db.session.commit()


def seed_purchases(locations, products):
    for idx in range(1, 4):
        po = get_or_create(
            PurchaseOrder,
            filters={"id": idx},
            defaults={
                "supplier": f"Proveedor {idx}",
                "location_id": locations[idx % len(locations)].id,
                "status": random.choice(["borrador", "enviada", "recibida"]),
                "notes": "Pedido automático para demo.",
            },
        )
        with db.session.no_autoflush:
            for product in products:
                get_or_create(
                    PurchaseOrderItem,
                    filters={"order_id": po.id, "product_id": product.id},
                    defaults={"quantity": random.randint(2, 6)},
                )

    db.session.commit()


def seed_logistics(locations, products):
    orders = PurchaseOrder.query.all()
    for order in orders:
        for item in order.items:
            receipt = PurchaseReceipt(
                purchase_order_id=order.id,
                product_id=item.product_id,
                location_id=order.location_id,
                quantity_received=item.quantity,
                received_at=datetime.utcnow() - timedelta(days=random.randint(0, 5)),
            )
            db.session.add(receipt)
            stock = StockLevel.query.filter_by(
                product_id=item.product_id,
                location_id=order.location_id,
            ).first()
            if not stock:
                stock = StockLevel(
                    product_id=item.product_id,
                    location_id=order.location_id,
                    quantity=0,
                )
                db.session.add(stock)
            stock.quantity += item.quantity

    db.session.commit()


def seed_rrhh():
    loc = Location.query.first()
    for i in range(3):
        emp = get_or_create(
            Employee,
            filters={"email": f"usuario{i}@silva360.com"},
            defaults={
                "full_name": f"Empleado {i}",
                "role": "Consultor",
                "location_id": loc.id if loc else None,
                "active": True,
            },
        )
        get_or_create(
            Attendance,
            filters={"employee_id": emp.id, "date": datetime.utcnow().date()},
            defaults={
                "check_in": datetime.utcnow() - timedelta(hours=8),
                "check_out": datetime.utcnow() - timedelta(hours=1),
            },
        )
        get_or_create(
            Goal,
            filters={"employee_id": emp.id, "description": "Meta desfase"},
            defaults={
                "period": "2025-Q4",
                "target_value": 5,
                "current_value": i,
                "status": "en progreso",
            },
        )
    survey = get_or_create(Survey, filters={"name": "Pulse Silva"})
    for emp in Employee.query.limit(3):
        get_or_create(
            SurveyResponse,
            filters={"survey_id": survey.id, "employee_id": emp.id},
            defaults={"score": random.randint(6, 10)},
        )

    db.session.commit()


def main():
    app = create_app()
    with app.app_context():
        units, locations, products = seed_business_entities()
        seed_leads(units, locations, products)
        seed_purchases(locations, products)
        seed_logistics(locations, products)
        seed_rrhh()
        print("Demo data generada.")


if __name__ == "__main__":
    main()
