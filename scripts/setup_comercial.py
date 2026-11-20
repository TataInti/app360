import argparse
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Agregar la carpeta padre al sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app import create_app
from claves_seguras import confirmar, generar_clave
from config import Config
from models import (
    Attendance,
    BusinessUnit,
    Campaign,
    Employee,
    Goal,
    Lead,
    LeadDemo,
    LeadInteraction,
    Location,
    Product,
    Quotation,
    Sale,
    StockReservation,
    Survey,
    SurveyResponse,
    User,
    db,
)
from security import ACCESS_MAP


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


def seed_rrhh_data(locations):
    emp = get_or_create(
        Employee,
        filters={"email": "maria.comercial@silva360.ar"},
        defaults={
            "first_name": "María",
            "last_name": "Gerente Comercial",
            "position": "Gerente Comercial",
            "department": "Comercial",
            "location_id": locations[0].id,
            "is_active": True,
        },
    )

    get_or_create(
        Attendance,
        filters={"employee_id": emp.id, "date": datetime.utcnow().date()},
        defaults={
            "check_in": datetime.utcnow() - timedelta(hours=2),
            "check_out": datetime.utcnow() - timedelta(hours=1),
        },
    )

    get_or_create(
        Goal,
        filters={"employee_id": emp.id, "description": "Cerrar 3 ventas premium"},
        defaults={
            "period": "2025-Q4",
            "target_value": 3,
            "current_value": 1,
            "status": "en progreso",
        },
    )

    survey = get_or_create(
        Survey,
        filters={"name": "Clima Trimestral"},
        defaults={
            "start_date": datetime.utcnow().date() - timedelta(days=10),
            "end_date": datetime.utcnow().date() + timedelta(days=20),
            "location_id": locations[0].id,
        },
    )

    get_or_create(
        SurveyResponse,
        filters={"survey_id": survey.id, "employee_id": emp.id},
        defaults={
            "score": 8,
            "comments": "El equipo comercial se siente alineado.",
        },
    )

    db.session.commit()


def seed_users(reset_claves=False, forzar_roles=False):
    """Crea cuentas demo sin cambiar roles ni claves existentes por defecto.

    Cuenta nueva: rol preset y clave aleatoria (ADMIN_USERNAME toma ADMIN_PASSWORD).
    Cuenta existente: su rol solo cambia con forzar_roles y su clave solo con reset_claves.
    """
    # Los roles comercial, compras, rrhh y operaciones no existen en ACCESS_MAP.
    # Se dejan tal como están hasta decidir el mapeo (decisión de producto P-8).
    cuentas = [
        (Config.ADMIN_USERNAME, "gerente"),
        ("jefe_comercial", "comercial"),
        ("jefe_compras", "compras"),
        ("jefe_rrhh", "rrhh"),
        ("jefe_operaciones", "operaciones"),
    ]

    resumen = []
    for username, role in cuentas:
        user = User.query.filter_by(username=username).first()
        clave_generada = None
        if user is None:
            user = User(username=username, role=role, active=True)
            if username == Config.ADMIN_USERNAME and Config.ADMIN_PASSWORD:
                user.set_password(Config.ADMIN_PASSWORD)
                accion = "creado (clave de ADMIN_PASSWORD)"
            else:
                clave_generada = generar_clave()
                user.set_password(clave_generada)
                accion = "creado"
            db.session.add(user)
        else:
            if forzar_roles:
                user.role = role
            rol_conservado = user.role != role
            if reset_claves:
                clave_generada = generar_clave()
                user.set_password(clave_generada)
                accion = "clave regenerada"
            else:
                accion = "existe, clave sin cambios"
            if rol_conservado:
                accion += ", rol conservado"
            elif forzar_roles:
                accion += ", rol preset aplicado"
        resumen.append(
            {"usuario": username, "rol": user.role, "accion": accion, "clave": clave_generada}
        )

    db.session.commit()
    return resumen


def imprimir_resumen_usuarios(resumen, mostrar_claves=False):
    """Imprime las cuentas. Las claves generadas solo se muestran con mostrar_claves."""
    print("\n--- Cuentas de demo ---")
    for fila in resumen:
        print(f"  {fila['usuario']} (rol: {fila['rol']}): {fila['accion']}")
        if fila["clave"]:
            if mostrar_claves:
                print(f"      clave: {fila['clave']}  (se muestra una sola vez; no se guarda)")
            else:
                print("      clave generada, no mostrada (usar --mostrar-claves para verla una vez)")

    sin_mapeo = [fila["usuario"] for fila in resumen if fila["rol"] not in ACCESS_MAP]
    if sin_mapeo:
        print(
            "ADVERTENCIA: estas cuentas usan roles que no existen en ACCESS_MAP (security.py) "
            f"y no tienen módulos: {', '.join(sin_mapeo)}. Se dejan así; el mapeo a roles "
            "reales es una decisión de producto pendiente (P-8)."
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Carga la base comercial de demo.")
    parser.add_argument(
        "--mostrar-claves",
        action="store_true",
        help="Muestra una vez las claves generadas para cuentas nuevas o regeneradas.",
    )
    parser.add_argument(
        "--reset-claves",
        action="store_true",
        help="Regenera las claves de cuentas existentes. Pide confirmación.",
    )
    parser.add_argument(
        "--forzar-roles",
        action="store_true",
        help="Aplica los roles preset a las cuentas existentes (apagado por defecto).",
    )
    args = parser.parse_args(argv)

    reset = args.reset_claves
    if reset and not confirmar("Se regenerarán las claves de las cuentas de demo existentes."):
        print("Sin confirmación: no se regeneran claves.")
        reset = False

    app = create_app()
    with app.app_context():
        db.create_all()
        units, locations, products, campaign = seed_business_data()
        seed_demo_lead(units, locations, products, campaign)
        seed_rrhh_data(locations)
        resumen = seed_users(reset_claves=reset, forzar_roles=args.forzar_roles)
        print("Base comercial sembrada con unidades, productos, campaña y lead demo.")
        imprimir_resumen_usuarios(resumen, mostrar_claves=args.mostrar_claves)


if __name__ == "__main__":
    main()
