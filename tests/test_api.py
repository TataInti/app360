import pytest
import json
import io
from models import db
from models.core import User, Product
from models.crm import Client
from models.sales import Venta


class TestAuthAPI:
    def test_login_success(self, client, init_database):
        # Create test user
        user = User(username="testadmin")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

        # Test login
        response = client.post('/api/login', json={
            'username': 'testadmin',
            'password': 'testpass'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'user' in data

    def test_login_failure(self, client, init_database):
        response = client.post('/api/login', json={
            'username': 'wrong',
            'password': 'wrong'
        })
        assert response.status_code == 401


class TestProductsAPI:
    def test_get_products(self, client, init_database):
        # This would test the actual API endpoint
        # For now, just check the route exists
        response = client.get('/api/products')
        # Assuming the API is implemented
        assert response.status_code in [200, 401]  # 401 if not authenticated


class TestVentasAPI:
    def test_importar_ventas_csv(self, client, init_database):
        # Login first
        user = User(username="testadmin")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

        client.post('/api/login', json={
            'username': 'testadmin',
            'password': 'testpass'
        })

        # Create test product
        product = Product(name="Test Product", sku="TEST001")
        db.session.add(product)
        db.session.commit()

        # Create CSV data
        csv_data = "fecha,cliente,producto,cantidad,precio_contrato,precio_efectivo\n2026-01-20,Cliente Test,TEST001,10,100.50,105.00"
        csv_file = io.BytesIO(csv_data.encode('utf-8'))
        csv_file.name = 'test.csv'

        # Test import
        response = client.post('/api/ventas/importar',
                             data={'file': (csv_file, 'test.csv')},
                             content_type='multipart/form-data')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'importadas' in data
        assert data['importadas'] == 1

        # Verify data was created
        venta = Venta.query.first()
        assert venta is not None
        assert venta.cantidad == 10
        assert venta.precio_efectivo == 105.00

        cliente = Client.query.filter_by(code="Cliente Test").first()
        assert cliente is not None

    def test_listar_ventas(self, client, init_database):
        # Login first
        user = User(username="testadmin")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

        client.post('/api/login', json={
            'username': 'testadmin',
            'password': 'testpass'
        })

        # Create test data
        product = Product(name="Test Product", sku="TEST001")
        cliente = Client(name="Test Client", code="TESTCLIENT")
        db.session.add(product)
        db.session.add(cliente)
        db.session.commit()

        venta = Venta(
            fecha="2026-01-20",
            cliente_id=cliente.id,
            producto_id=product.id,
            cantidad=5,
            precio_contrato=100.00,
            precio_efectivo=105.00
        )
        db.session.add(venta)
        db.session.commit()

        # Test list
        response = client.get('/api/ventas/listar')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'ventas' in data
        assert len(data['ventas']) == 1
        assert data['ventas'][0]['cantidad'] == 5

    def test_exportar_ventas(self, client, init_database):
        # Login first
        user = User(username="testadmin")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

        client.post('/api/login', json={
            'username': 'testadmin',
            'password': 'testpass'
        })

        # Create test data similar to listar
        product = Product(name="Test Product", sku="TEST001")
        cliente = Client(name="Test Client", code="TESTCLIENT")
        db.session.add(product)
        db.session.add(cliente)
        db.session.commit()

        venta = Venta(
            fecha="2026-01-20",
            cliente_id=cliente.id,
            producto_id=product.id,
            cantidad=5,
            precio_contrato=100.00,
            precio_efectivo=105.00
        )
        db.session.add(venta)
        db.session.commit()

        # Test export
        response = client.get('/api/ventas/exportar')
        assert response.status_code == 200
        assert 'text/csv' in response.content_type
        # Verify CSV content contains expected data
        csv_content = response.data.decode('utf-8')
        assert 'Test Client' in csv_content
        assert '5' in csv_content


class TestRRHHAPI:
    def test_turnos_listar(self, client, init_database):
        """Test listar turnos"""
        from models.rrhh import Turno
        from datetime import time

        # Crear turno de prueba
        turno = Turno(
            nombre="Test Turno",
            descripcion="Turno de prueba",
            hora_inicio=time(9, 0),
            hora_fin=time(17, 0),
            dias_semana="1,2,3,4,5"
        )
        db.session.add(turno)
        db.session.commit()

        # Test endpoint (en modo testing no requiere auth)
        response = client.get('/api/rrhh/turnos')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'turnos' in data
        assert len(data['turnos']) > 0
        assert data['turnos'][0]['nombre'] == 'Test Turno'

    def test_turnos_crear(self, client, init_database):
        """Test crear turno"""
        response = client.post('/api/rrhh/turnos', json={
            'nombre': 'Nuevo Turno',
            'hora_inicio': '08:00',
            'hora_fin': '16:00',
            'descripcion': 'Turno de prueba'
        })

        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'turno' in data
        assert data['turno']['nombre'] == 'Nuevo Turno'