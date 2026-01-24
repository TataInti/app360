from app import create_app
from models import db, CategoriaGasto, Proveedor

def seed_categorias_gastos():
    """Crear categorías de gastos iniciales"""
    categorias = [
        {"nombre": "Logística", "descripcion": "Transporte, fletes y distribución"},
        {"nombre": "Energía", "descripcion": "Electricidad, gas, combustibles"},
        {"nombre": "Servicios", "descripcion": "Internet, telefonía, limpieza, seguridad"},
        {"nombre": "Mantenimiento", "descripcion": "Reparaciones, equipos, instalaciones"},
        {"nombre": "Impuestos", "descripcion": "Tributos, tasas, contribuciones"},
        {"nombre": "Marketing", "descripcion": "Publicidad, promoción, eventos"},
        {"nombre": "Oficina", "descripcion": "Suministros, papelería, software"},
        {"nombre": "Otros", "descripcion": "Gastos varios no categorizados"}
    ]

    for cat_data in categorias:
        categoria = CategoriaGasto.query.filter_by(nombre=cat_data["nombre"]).first()
        if not categoria:
            categoria = CategoriaGasto(**cat_data)
            db.session.add(categoria)

    db.session.commit()
    print("Categorías de gastos creadas")


def seed_proveedores_ejemplo():
    """Crear proveedores de ejemplo"""
    proveedores = [
        {"nombre": "EDESUR S.A.", "cuit": "30-12345678-9", "email": "facturacion@edesur.com.ar", "telefono": "0800-123-4567"},
        {"nombre": "Telecom Argentina", "cuit": "30-87654321-0", "email": "facturas@telecom.com.ar", "telefono": "0800-333-0000"},
        {"nombre": "Transportes Rápidos SRL", "cuit": "30-11111111-1", "email": "admin@transportesrapidos.com.ar", "telefono": "11-4444-5555"},
        {"nombre": "AFIP", "cuit": "30-99999999-9", "email": "info@afip.gob.ar", "telefono": "0800-345-3456"},
        {"nombre": "Municipalidad de Buenos Aires", "cuit": "30-88888888-8", "email": "tributos@buenosaires.gob.ar", "telefono": "147"}
    ]

    for prov_data in proveedores:
        proveedor = Proveedor.query.filter_by(cuit=prov_data["cuit"]).first()
        if not proveedor:
            proveedor = Proveedor(**prov_data)
            db.session.add(proveedor)

    db.session.commit()
    print("Proveedores de ejemplo creados")


def main():
    app = create_app()
    with app.app_context():
        # No crear tablas, asumir que ya existen
        # db.create_all()
        seed_categorias_gastos()
        seed_proveedores_ejemplo()
        print("Módulo de gastos inicializado con categorías y proveedores de ejemplo.")


if __name__ == "__main__":
    main()