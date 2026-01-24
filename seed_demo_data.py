#!/usr/bin/env python3
"""
Script para crear datos demo para todos los módulos de la aplicación.
Ejecutar con: python3 seed_demo_data.py
"""

from datetime import datetime, date, timedelta
import random
from decimal import Decimal

from app import create_app
from models import db
from models.core import User, Product, BusinessUnit, Location
from models.crm import Client, Lead, Campaign, LeadInteraction
from models.sales import Venta, Sale, StockReservation
from models.purchases import PurchaseOrder, PurchaseOrderItem, PurchaseReceipt
from models.hr import Employee, Attendance, Absence, Goal, Headcount, Survey, SurveyResponse
from models.tesoreria import InstrumentoPago, ArqueoCaja, MovimientoCaja
from models.comercial import Promocion, PromocionAplicada, Comision, ComisionDetalle
from models.gastos import CategoriaGasto, Proveedor, Gasto
from models.rrhh import Turno, Asistencia, Adelanto


def create_business_units():
    """Crear unidades de negocio"""
    print("Creando unidades de negocio...")
    units = [
        BusinessUnit(name="Tecnología"),
        BusinessUnit(name="Oficina"),
        BusinessUnit(name="Industrial"),
    ]
    db.session.add_all(units)
    return units


def create_locations():
    """Crear ubicaciones"""
    print("Creando ubicaciones...")
    locations = [
        Location(name="Madrid Centro", address="Calle Mayor 1, Madrid"),
        Location(name="Barcelona", address="La Rambla 15, Barcelona"),
        Location(name="Valencia", address="Plaza Reina 5, Valencia"),
        Location(name="Sevilla", address="Avenida Constitución 10, Sevilla"),
    ]
    db.session.add_all(locations)
    return locations


def create_users():
    """Crear usuarios"""
    print("Creando usuarios...")
    users = [
        User(username="admin", role="admin"),
        User(username="manager", role="manager"),
        User(username="sales", role="sales"),
        User(username="hr", role="hr"),
        User(username="accounting", role="accounting"),
    ]

    for user in users:
        user.set_password("demo123")

    db.session.add_all(users)
    return users


def create_products(business_units):
    """Crear productos"""
    print("Creando productos...")
    products = [
        Product(name="Laptop Dell", sku="LAP001", business_unit=business_units[0], price=Decimal("1200.00"), stock_quantity=50),
        Product(name="Monitor 24'", sku="MON001", business_unit=business_units[0], price=Decimal("300.00"), stock_quantity=30),
        Product(name="Impresora Laser", sku="IMP001", business_unit=business_units[0], price=Decimal("250.00"), stock_quantity=20),
        Product(name="Papel A4", sku="PAP001", business_unit=business_units[1], price=Decimal("5.50"), stock_quantity=500),
        Product(name="Bolígrafos", sku="BOL001", business_unit=business_units[1], price=Decimal("2.30"), stock_quantity=200),
        Product(name="Toner Negro", sku="TON001", business_unit=business_units[1], price=Decimal("45.00"), stock_quantity=25),
        Product(name="Taladro Industrial", sku="TAL001", business_unit=business_units[2], price=Decimal("350.00"), stock_quantity=15),
        Product(name="Guantes Seguridad", sku="GUA001", business_unit=business_units[2], price=Decimal("12.00"), stock_quantity=100),
    ]
    db.session.add_all(products)
    return products


def create_clients():
    """Crear clientes"""
    print("Creando clientes...")
    clients = [
        Client(name="Empresa ABC S.A.", code="CLI001"),
        Client(name="Tech Solutions Ltd.", code="CLI002"),
        Client(name="Industria Valencia S.L.", code="CLI003"),
        Client(name="Oficinas del Sur", code="CLI004"),
        Client(name="Comercial Norte", code="CLI005"),
    ]
    db.session.add_all(clients)
    return clients


def create_employees(locations):
    """Crear empleados"""
    print("Creando empleados...")
    employees = [
        Employee(first_name="María", last_name="García", email="maria.garcia@empresa.com", position="Gerente Ventas", department="Ventas", hire_date=date(2020, 1, 15), salary=Decimal("45000.00"), location=locations[0]),
        Employee(first_name="Carlos", last_name="Rodríguez", email="carlos.rodriguez@empresa.com", position="Técnico", department="Técnico", hire_date=date(2021, 3, 10), salary=Decimal("35000.00"), location=locations[1]),
        Employee(first_name="Ana", last_name="Martínez", email="ana.martinez@empresa.com", position="Contable", department="Finanzas", hire_date=date(2019, 6, 20), salary=Decimal("38000.00"), location=locations[2]),
        Employee(first_name="David", last_name="López", email="david.lopez@empresa.com", position="RRHH", department="Recursos Humanos", hire_date=date(2022, 1, 5), salary=Decimal("32000.00"), location=locations[3]),
        Employee(first_name="Laura", last_name="Sánchez", email="laura.sanchez@empresa.com", position="Marketing", department="Marketing", hire_date=date(2021, 9, 12), salary=Decimal("36000.00"), location=locations[0]),
    ]
    db.session.add_all(employees)
    return employees


def create_leads(business_units, products):
    """Crear leads"""
    print("Creando leads...")
    leads = [
        Lead(name="Juan Pérez", email="juan.perez@email.com", phone="600123456", source="web", status="nuevo", business_unit=business_units[0]),
        Lead(name="María López", email="maria.lopez@email.com", phone="600234567", source="referido", status="contactado", business_unit=business_units[1]),
        Lead(name="Carlos Gómez", email="carlos.gomez@email.com", phone="600345678", source="redes_sociales", status="calificado", business_unit=business_units[2]),
        Lead(name="Ana Ruiz", email="ana.ruiz@email.com", phone="600456789", source="email_marketing", status="propuesta", business_unit=business_units[0]),
        Lead(name="Pedro Martín", email="pedro.martin@email.com", phone="600567890", source="feria", status="ganado", business_unit=business_units[1]),
    ]
    db.session.add_all(leads)
    return leads


def create_ventas(products, clients):
    """Crear ventas"""
    print("Creando ventas...")
    ventas = []
    base_date = date.today() - timedelta(days=60)

    for i in range(50):  # 50 ventas de ejemplo
        sale_date = base_date + timedelta(days=random.randint(0, 60))
        product = random.choice(products)
        client = random.choice(clients)
        cantidad = random.randint(1, 10)
        precio_contrato = product.price * Decimal(str(random.uniform(0.9, 1.1)))
        precio_efectivo = precio_contrato * Decimal(str(random.uniform(0.95, 1.05)))

        venta = Venta(
            fecha=sale_date,
            cliente=client,
            producto=product,
            cantidad=cantidad,
            precio_contrato=precio_contrato,
            precio_efectivo=precio_efectivo
        )
        ventas.append(venta)

    db.session.add_all(ventas)
    return ventas


def create_categorias_gastos():
    """Crear categorías de gastos"""
    print("Creando categorías de gastos...")
    categorias = [
        CategoriaGasto(nombre="Suministros Oficina", descripcion="Material de oficina y papelería"),
        CategoriaGasto(nombre="Viajes", descripcion="Desplazamientos y dietas"),
        CategoriaGasto(nombre="Marketing", descripcion="Publicidad y promoción"),
        CategoriaGasto(nombre="Mantenimiento", descripcion="Reparaciones y mantenimiento"),
        CategoriaGasto(nombre="Servicios", descripcion="Servicios externos"),
    ]
    db.session.add_all(categorias)
    return categorias


def create_proveedores():
    """Crear proveedores"""
    print("Creando proveedores...")
    proveedores = [
        Proveedor(nombre="Papelería Central", telefono="910123456", email="ana@papeleria.com"),
        Proveedor(nombre="Tech Supplies S.A.", telefono="911234567", email="carlos@techsupplies.com"),
        Proveedor(nombre="Industrial Parts Ltd.", telefono="912345678", email="maria@industrialparts.com"),
        Proveedor(nombre="Oficina Plus", telefono="913456789", email="david@oficinaplus.com"),
    ]
    db.session.add_all(proveedores)
    return proveedores


def create_gastos(categorias, proveedores):
    """Crear gastos"""
    print("Creando gastos...")
    gastos = []
    base_date = date.today() - timedelta(days=60)

    for i in range(30):  # 30 gastos de ejemplo
        gasto_date = base_date + timedelta(days=random.randint(0, 60))
        categoria = random.choice(categorias)
        proveedor = random.choice(proveedores)
        monto = Decimal(str(random.uniform(50, 2000)))

        gasto = Gasto(
            fecha=gasto_date,
            categoria=categoria,
            proveedor=proveedor,
            descripcion=f"Gasto de {categoria.nombre}",
            monto=monto
        )
        gastos.append(gasto)

    db.session.add_all(gastos)
    return gastos


def create_turnos():
    """Crear turnos"""
    print("Creando turnos...")
    turnos = [
        Turno(nombre="Mañana", descripcion="Turno de mañana", hora_inicio="08:00", hora_fin="16:00", dias_semana="1,2,3,4,5"),
        Turno(nombre="Tarde", descripcion="Turno de tarde", hora_inicio="16:00", hora_fin="00:00", dias_semana="1,2,3,4,5"),
        Turno(nombre="Noche", descripcion="Turno de noche", hora_inicio="00:00", hora_fin="08:00", dias_semana="1,2,3,4,5,6,7"),
    ]
    db.session.add_all(turnos)
    return turnos


def create_asistencias(employees, turnos):
    """Crear asistencias"""
    print("Creando asistencias...")
    asistencias = []
    base_date = date.today() - timedelta(days=30)

    for i in range(150):  # 150 registros de asistencia
        asistencia_date = base_date + timedelta(days=random.randint(0, 30))
        employee = random.choice(employees)
        turno = random.choice(turnos)

        # Simular asistencia aleatoria
        presente = random.choice([True, True, True, False])  # 75% de asistencia

        if presente:
            hora_entrada = datetime.combine(asistencia_date, datetime.strptime("08:00", "%H:%M").time()) + timedelta(minutes=random.randint(-30, 30))
            hora_salida = datetime.combine(asistencia_date, datetime.strptime("16:00", "%H:%M").time()) + timedelta(minutes=random.randint(-30, 30))
            horas_trabajadas = Decimal("8.0")
            estado = "presente"
        else:
            hora_entrada = None
            hora_salida = None
            horas_trabajadas = Decimal("0.0")
            estado = "ausente"

        asistencia = Asistencia(
            empleado_id=employee.id,
            turno_id=turno.id,
            fecha=asistencia_date,
            hora_entrada=hora_entrada,
            hora_salida=hora_salida,
            horas_trabajadas=horas_trabajadas,
            estado=estado
        )
        asistencias.append(asistencia)

    db.session.add_all(asistencias)
    return asistencias


def main():
    """Función principal para crear todos los datos demo"""
    print("🚀 Iniciando creación de datos demo...")

    app = create_app()
    with app.app_context():
        try:
            # Crear datos en orden de dependencias
            business_units = create_business_units()
            locations = create_locations()
            users = create_users()
            products = create_products(business_units)
            clients = create_clients()
            employees = create_employees(locations)
            leads = create_leads(business_units, products)
            ventas = create_ventas(products, clients)

            categorias_gastos = create_categorias_gastos()
            proveedores = create_proveedores()
            gastos = create_gastos(categorias_gastos, proveedores)

            turnos = create_turnos()

            # Commit intermedio para asignar IDs a empleados y turnos
            db.session.commit()

            asistencias = create_asistencias(employees, turnos)

            # Commit de todos los cambios
            db.session.commit()

            print("✅ ¡Datos demo creados exitosamente!")
            print(f"   - {len(business_units)} unidades de negocio")
            print(f"   - {len(locations)} ubicaciones")
            print(f"   - {len(users)} usuarios")
            print(f"   - {len(products)} productos")
            print(f"   - {len(clients)} clientes")
            print(f"   - {len(employees)} empleados")
            print(f"   - {len(leads)} leads")
            print(f"   - {len(ventas)} ventas")
            print(f"   - {len(categorias_gastos)} categorías de gastos")
            print(f"   - {len(proveedores)} proveedores")
            print(f"   - {len(gastos)} gastos")
            print(f"   - {len(turnos)} turnos")
            print(f"   - {len(asistencias)} registros de asistencia")

            print("\n🔐 Credenciales de acceso:")
            print("   Usuario: admin, Contraseña: demo123")
            print("   Usuario: manager, Contraseña: demo123")
            print("   Usuario: sales, Contraseña: demo123")
            print("   Usuario: hr, Contraseña: demo123")
            print("   Usuario: accounting, Contraseña: demo123")

        except Exception as e:
            print(f"❌ Error creando datos demo: {e}")
            db.session.rollback()
            raise


if __name__ == "__main__":
    main()