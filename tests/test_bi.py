import pytest
import json
from models import db, User, Venta, Lead, Employee, Asistencia
from models.core import Product, Location, BusinessUnit
from models.crm import Client
from datetime import datetime, date


class TestBIModule:
    def test_dashboard_kpis(self, client, init_database, auth_headers):
        """Test dashboard KPIs endpoint"""
        # Create required related entities first
        location = Location(name="Test Location")
        db.session.add(location)
        db.session.flush()
        
        bu = BusinessUnit(name="Test BU")
        db.session.add(bu)
        db.session.flush()
        
        product = Product(name="Test Product", sku="SKU001", business_unit_id=bu.id)
        db.session.add(product)
        db.session.flush()
        
        cliente = Client(name="Test Client", code="CLI001")
        db.session.add(cliente)
        db.session.flush()
        
        # Create some test data
        venta = Venta(
            fecha=date.today(),
            producto_id=product.id,
            cantidad=10,
            precio_contrato=100.0,
            precio_efectivo=100.0,
            cliente_id=cliente.id
        )
        db.session.add(venta)

        empleado = Employee(
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            hire_date=date.today(),
            salary=50000.0,
            location_id=location.id
        )
        db.session.add(empleado)

        lead = Lead(
            name="Test Lead",
            email="lead@example.com",
            phone="123456789",
            source="web",
            status="nuevo",
            business_unit_id=bu.id,
            location_id=location.id
        )
        db.session.add(lead)

        db.session.commit()

        # Test the dashboard endpoint
        response = client.get('/api/bi/dashboard', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'kpis' in data
        assert 'ventas_totales' in data['kpis']
        assert 'empleados_activos' in data['kpis']
        assert 'total_leads' in data['kpis']

    def test_ranking_products(self, client, init_database, auth_headers):
        """Test product ranking endpoint"""
        # Create required related entities first
        bu = BusinessUnit(name="Test BU")
        db.session.add(bu)
        db.session.flush()
        
        product1 = Product(name="Product 1", sku="SKU001", business_unit_id=bu.id)
        product2 = Product(name="Product 2", sku="SKU002", business_unit_id=bu.id)
        cliente = Client(name="Test Client", code="CLI001")
        db.session.add_all([product1, product2, cliente])
        db.session.flush()
        
        # Create test sales data
        venta1 = Venta(
            fecha=date.today(),
            producto_id=product1.id,
            cantidad=5,
            precio_contrato=200.0,
            precio_efectivo=200.0,
            cliente_id=cliente.id
        )
        venta2 = Venta(
            fecha=date.today(),
            producto_id=product2.id,
            cantidad=3,
            precio_contrato=150.0,
            precio_efectivo=150.0,
            cliente_id=cliente.id
        )
        db.session.add(venta1)
        db.session.add(venta2)
        db.session.commit()

        # Test the ranking endpoint - correct URL with query param
        response = client.get('/api/bi/ranking?tipo=productos', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'ranking' in data
        assert isinstance(data['ranking'], list)

    def test_ranking_locations(self, client, init_database, auth_headers):
        """Test location ranking endpoint"""
        # Create required related entities first
        bu = BusinessUnit(name="Test BU")
        db.session.add(bu)
        db.session.flush()
        
        product = Product(name="Test Product", sku="SKU001", business_unit_id=bu.id)
        cliente1 = Client(name="Client 1", code="CLI001")
        cliente2 = Client(name="Client 2", code="CLI002")
        db.session.add_all([product, cliente1, cliente2])
        db.session.flush()
        
        # Create test sales data for different clients
        venta1 = Venta(
            fecha=date.today(),
            producto_id=product.id,
            cantidad=5,
            precio_contrato=200.0,
            precio_efectivo=200.0,
            cliente_id=cliente1.id
        )
        venta2 = Venta(
            fecha=date.today(),
            producto_id=product.id,
            cantidad=3,
            precio_contrato=200.0,
            precio_efectivo=200.0,
            cliente_id=cliente2.id
        )
        db.session.add(venta1)
        db.session.add(venta2)
        db.session.commit()

        # Test the ranking endpoint - correct URL with query param
        response = client.get('/api/bi/ranking?tipo=ubicaciones', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'ranking' in data
        assert isinstance(data['ranking'], list)

    def test_daily_summary(self, client, init_database, auth_headers):
        """Test daily summary report endpoint"""
        # Create required related entities first
        bu = BusinessUnit(name="Test BU")
        db.session.add(bu)
        db.session.flush()
        
        product = Product(name="Test Product", sku="SKU001", business_unit_id=bu.id)
        cliente = Client(name="Test Client", code="CLI001")
        db.session.add_all([product, cliente])
        db.session.flush()
        
        # Create test data for today
        today = date.today()
        venta = Venta(
            fecha=today,
            producto_id=product.id,
            cantidad=10,
            precio_contrato=100.0,
            precio_efectivo=100.0,
            cliente_id=cliente.id
        )
        db.session.add(venta)
        db.session.commit()

        # Test the daily summary endpoint
        response = client.get(f'/api/reportes/resumen-diario?fecha={today.isoformat()}', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'fecha' in data
        assert 'resumen' in data
        # Check the correct field names based on actual API response
        assert 'numero_ventas_dia' in data['resumen']

    def test_export_excel(self, client, init_database, auth_headers):
        """Test Excel export endpoint"""
        # Create required related entities first
        bu = BusinessUnit(name="Test BU")
        db.session.add(bu)
        db.session.flush()
        
        product = Product(name="Test Product", sku="SKU001", business_unit_id=bu.id)
        cliente = Client(name="Test Client", code="CLI001")
        db.session.add_all([product, cliente])
        db.session.flush()
        
        # Create test sales data
        venta = Venta(
            fecha=date.today(),
            producto_id=product.id,
            cantidad=10,
            precio_contrato=100.0,
            precio_efectivo=100.0,
            cliente_id=cliente.id
        )
        db.session.add(venta)
        db.session.commit()

        # Test the export endpoint with correct tipo parameter
        response = client.get('/api/bi/exportar?tipo=ventas_resumen&fecha_desde=2024-01-01&fecha_hasta=2027-12-31', headers=auth_headers)
        assert response.status_code == 200
        assert response.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
