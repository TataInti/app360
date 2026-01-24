import pytest
import json
from models import db, User, Venta, Lead, Employee, Asistencia
from datetime import datetime, date


class TestBIModule:
    def test_dashboard_kpis(self, client, init_database, auth_headers):
        """Test dashboard KPIs endpoint"""
        # Create some test data
        venta = Venta(
            fecha=datetime.now(),
            producto_id=1,
            cantidad=10,
            precio_unitario=100.0,
            total=1000.0,
            cliente_id=1,
            location_id=1
        )
        db.session.add(venta)

        empleado = Employee(
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            hire_date=date.today(),
            salary=50000.0,
            location_id=1
        )
        db.session.add(empleado)

        lead = Lead(
            nombre="Test Lead",
            email="lead@example.com",
            telefono="123456789",
            fuente="web",
            estado="nuevo",
            location_id=1
        )
        db.session.add(lead)

        db.session.commit()

        # Test the dashboard endpoint
        response = client.get('/api/bi/dashboard', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'kpis' in data
        assert 'ventas_total' in data['kpis']
        assert 'empleados_total' in data['kpis']
        assert 'leads_total' in data['kpis']

    def test_ranking_products(self, client, init_database, auth_headers):
        """Test product ranking endpoint"""
        # Create test sales data
        venta1 = Venta(
            fecha=datetime.now(),
            producto_id=1,
            cantidad=5,
            precio_unitario=200.0,
            total=1000.0,
            cliente_id=1,
            location_id=1
        )
        venta2 = Venta(
            fecha=datetime.now(),
            producto_id=2,
            cantidad=3,
            precio_unitario=150.0,
            total=450.0,
            cliente_id=1,
            location_id=1
        )
        db.session.add(venta1)
        db.session.add(venta2)
        db.session.commit()

        # Test the ranking endpoint
        response = client.get('/api/bi/ranking/productos', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'ranking' in data
        assert isinstance(data['ranking'], list)

    def test_ranking_locations(self, client, init_database, auth_headers):
        """Test location ranking endpoint"""
        # Create test sales data for different locations
        venta1 = Venta(
            fecha=datetime.now(),
            producto_id=1,
            cantidad=5,
            precio_unitario=200.0,
            total=1000.0,
            cliente_id=1,
            location_id=1
        )
        venta2 = Venta(
            fecha=datetime.now(),
            producto_id=1,
            cantidad=3,
            precio_unitario=200.0,
            total=600.0,
            cliente_id=1,
            location_id=2
        )
        db.session.add(venta1)
        db.session.add(venta2)
        db.session.commit()

        # Test the ranking endpoint
        response = client.get('/api/bi/ranking/locations', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'ranking' in data
        assert isinstance(data['ranking'], list)

    def test_daily_summary(self, client, init_database, auth_headers):
        """Test daily summary report endpoint"""
        # Create test data for today
        today = date.today()
        venta = Venta(
            fecha=datetime.combine(today, datetime.min.time()),
            producto_id=1,
            cantidad=10,
            precio_unitario=100.0,
            total=1000.0,
            cliente_id=1,
            location_id=1
        )
        db.session.add(venta)
        db.session.commit()

        # Test the daily summary endpoint
        response = client.get(f'/api/reportes/resumen-diario?fecha={today.isoformat()}', headers=auth_headers)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'fecha' in data
        assert 'ventas_total' in data
        assert 'ventas_cantidad' in data

    def test_export_excel(self, client, init_database, auth_headers):
        """Test Excel export endpoint"""
        # Create test sales data
        venta = Venta(
            fecha=datetime.now(),
            producto_id=1,
            cantidad=10,
            precio_unitario=100.0,
            total=1000.0,
            cliente_id=1,
            location_id=1
        )
        db.session.add(venta)
        db.session.commit()

        # Test the export endpoint
        response = client.get('/api/bi/exportar?tipo=ventas&fecha_desde=2024-01-01&fecha_hasta=2024-12-31', headers=auth_headers)
        assert response.status_code == 200
        assert response.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'