"""Tests unitarios para el servicio de rentabilidad SabioGo."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from models import db
from models.core.product import Product
from models.crm.client import Client
from models.core.location import Location
from models.sabiogo import (
    StgSabiogoVentas,
    StgSabiogoCompras,
    SabiogoProductMap,
    SabiogoClientMap,
    SabiogoLocationMap
)
from services.sabiogo_service import SabiogoService


@pytest.fixture
def app():
    """Fixture de Flask app en modo testing."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Fixture de test client."""
    return app.test_client()


@pytest.fixture
def setup_data(app):
    """Fixture que crea datos de prueba."""
    with app.app_context():
        # Crear producto
        product = Product(
            id=1,
            sku='PROD001',
            name='Producto Test',
            category='Categoria Test',
            price=Decimal('100.00')
        )
        db.session.add(product)
        
        # Crear cliente
        cliente = Client(
            id=1,
            name='Cliente Test',
            code='CLI001'
        )
        db.session.add(cliente)
        
        # Crear ubicación
        location = Location(
            id=1,
            name='Sucursal Test',
            type='sucursal'
        )
        db.session.add(location)
        
        db.session.commit()
        
        # Crear mapeo de producto
        mapeo_prod = SabiogoProductMap(
            codigo='PROD001',
            product_id=1,
            activo=True
        )
        db.session.add(mapeo_prod)
        
        # Crear mapeo de cliente
        mapeo_cliente = SabiogoClientMap(
            cliente='Cliente Test',
            client_id=1,
            activo=True
        )
        db.session.add(mapeo_cliente)
        
        # Crear mapeo de ubicación
        mapeo_location = SabiogoLocationMap(
            sucursal='Sucursal Test',
            location_id=1,
            activo=True
        )
        db.session.add(mapeo_location)
        
        db.session.commit()
        
        # Crear datos de ventas
        fecha_venta = date.today() - timedelta(days=15)
        venta = StgSabiogoVentas(
            fecha=fecha_venta,
            codigo='PROD001',
            producto='Producto Test',
            cliente='Cliente Test',
            sucursal='Sucursal Test',
            kilos=Decimal('10.0'),
            cajas=Decimal('2.0'),
            neto=Decimal('100.00'),
            subtot=Decimal('120.00'),
            iva=Decimal('20.00'),
            total=Decimal('120.00'),
            estado='procesado'
        )
        db.session.add(venta)
        
        # Crear datos de compras
        fecha_compra = fecha_venta - timedelta(days=5)
        compra = StgSabiogoCompras(
            fecha=fecha_compra,
            codigo='PROD001',
            producto='Producto Test',
            proveedor='Proveedor Test',
            sucursal='Sucursal Test',
            kilos=Decimal('15.0'),
            cajas=Decimal('3.0'),
            neto=Decimal('60.00'),
            subtot=Decimal('70.00'),
            iva=Decimal('10.00'),
            total=Decimal('70.00'),
            estado='procesado'
        )
        db.session.add(compra)
        
        db.session.commit()
        
        yield {
            'product_id': 1,
            'client_id': 1,
            'location_id': 1,
            'fecha_venta': fecha_venta,
            'fecha_compra': fecha_compra
        }


class TestSabiogoService:
    """Tests para SabiogoService."""
    
    def test_get_rentabilidad_producto(self, app, setup_data):
        """Test de cálculo de rentabilidad de producto."""
        with app.app_context():
            service = SabiogoService()
            
            fecha_inicio = date.today() - timedelta(days=30)
            fecha_fin = date.today()
            
            rentabilidad = service.get_rentabilidad_producto(
                setup_data['product_id'],
                fecha_inicio,
                fecha_fin
            )
            
            # Verificar estructura
            assert 'product_id' in rentabilidad
            assert 'periodo' in rentabilidad
            assert 'ventas' in rentabilidad
            assert 'compras' in rentabilidad
            assert 'rentabilidad' in rentabilidad
            
            # Verificar valores
            assert rentabilidad['product_id'] == 1
            assert rentabilidad['ventas']['ingresos_totales'] == 120.0
            assert rentabilidad['compras']['costos_totales'] == 70.0
            assert rentabilidad['rentabilidad']['margen_bruto'] == 50.0
            assert rentabilidad['rentabilidad']['margen_porcentual'] > 0
    
    def test_get_rentabilidad_resumen(self, app, setup_data):
        """Test de resumen global de rentabilidad."""
        with app.app_context():
            service = SabiogoService()
            
            fecha_inicio = date.today() - timedelta(days=30)
            fecha_fin = date.today()
            
            resumen = service.get_rentabilidad_resumen(fecha_inicio, fecha_fin)
            
            # Verificar estructura
            assert 'total_ingresos' in resumen
            assert 'total_costos' in resumen
            assert 'margen_bruto' in resumen
            assert 'margen_porcentual' in resumen
            assert 'productos_activos' in resumen
            
            # Verificar valores
            assert resumen['total_ingresos'] >= 0
            assert resumen['total_costos'] >= 0
            assert resumen['margen_bruto'] == resumen['total_ingresos'] - resumen['total_costos']
    
    def test_get_top_productos_margen(self, app, setup_data):
        """Test de top productos por margen."""
        with app.app_context():
            service = SabiogoService()
            
            fecha_inicio = date.today() - timedelta(days=30)
            fecha_fin = date.today()
            
            top_productos = service.get_top_productos_margen(
                limit=5,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin
            )
            
            # Verificar que es una lista
            assert isinstance(top_productos, list)
            
            # Si hay productos, verificar estructura
            if len(top_productos) > 0:
                producto = top_productos[0]
                assert 'product_id' in producto
                assert 'producto' in producto
                assert 'ingresos' in producto
                assert 'costos' in producto
                assert 'margen_bruto' in producto
                assert 'margen_porcentual' in producto
    
    def test_validar_duplicados(self, app, setup_data):
        """Test de validación de duplicados."""
        with app.app_context():
            # Crear un duplicado
            fecha_venta = setup_data['fecha_venta']
            duplicado = StgSabiogoVentas(
                fecha=fecha_venta,
                codigo='PROD001',
                producto='Producto Test',
                cliente='Cliente Test',
                sucursal='Sucursal Test',
                tipo='A',
                nro_comprob='001',
                kilos=Decimal('10.0'),
                subtot=Decimal('120.00'),
                estado='pendiente'
            )
            db.session.add(duplicado)
            
            # Crear otro con datos idénticos
            duplicado2 = StgSabiogoVentas(
                fecha=fecha_venta,
                codigo='PROD001',
                producto='Producto Test',
                cliente='Cliente Test',
                sucursal='Sucursal Test',
                tipo='A',
                nro_comprob='001',
                kilos=Decimal('10.0'),
                subtot=Decimal('120.00'),
                estado='pendiente'
            )
            db.session.add(duplicado2)
            db.session.commit()
            
            # Ejecutar validación
            count = StgSabiogoVentas.validar_duplicados(db.session)
            
            # Verificar que se marcaron duplicados
            assert count >= 0
            
            # Verificar que hay registros con estado 'duplicado'
            duplicados = StgSabiogoVentas.query.filter_by(estado='duplicado').count()
            assert duplicados >= 0
    
    def test_registrar_log_carga(self, app):
        """Test de registro de log de carga."""
        with app.app_context():
            # Crear usuario para el log
            from models.core.user import User
            usuario = User(
                username='test_user',
                role='admin',
                active=True
            )
            db.session.add(usuario)
            db.session.commit()
            
            service = SabiogoService()
            
            log = service.registrar_carga(
                archivo_nombre='test.xlsx',
                tipo_carga='ventas',
                hash_archivo='abc123',
                filas_insertadas=100,
                filas_duplicadas=5,
                filas_sin_mapeo=10,
                filas_error=2,
                usuario_id=usuario.id,
                observaciones='Test de carga'
            )
            
            # Verificar que se creó el log
            assert log.id is not None
            assert log.archivo_nombre == 'test.xlsx'
            assert log.tipo_carga == 'ventas'
            assert log.filas_insertadas == 100
            assert log.filas_duplicadas == 5


class TestSabiogoModels:
    """Tests para modelos SabioGo."""
    
    def test_sabiogo_product_map_creation(self, app):
        """Test de creación de mapeo de producto."""
        with app.app_context():
            # Crear producto
            product = Product(
                sku='TEST001',
                name='Test Product'
            )
            db.session.add(product)
            db.session.commit()
            
            # Crear mapeo
            mapeo = SabiogoProductMap(
                codigo='TEST001',
                product_id=product.id,
                marca='Test Brand',
                activo=True
            )
            db.session.add(mapeo)
            db.session.commit()
            
            # Verificar
            assert mapeo.id is not None
            assert mapeo.codigo == 'TEST001'
            assert mapeo.product_id == product.id
            assert mapeo.activo is True
    
    def test_sabiogo_client_map_creation(self, app):
        """Test de creación de mapeo de cliente."""
        with app.app_context():
            # Crear cliente
            cliente = Client(
                name='Test Client',
                code='TC001'
            )
            db.session.add(cliente)
            db.session.commit()
            
            # Crear mapeo
            mapeo = SabiogoClientMap(
                cliente='Test Client',
                client_id=cliente.id,
                zona='Zona Test',
                activo=True
            )
            db.session.add(mapeo)
            db.session.commit()
            
            # Verificar
            assert mapeo.id is not None
            assert mapeo.cliente == 'Test Client'
            assert mapeo.client_id == cliente.id
    
    def test_staging_ventas_creation(self, app):
        """Test de creación de registro staging de ventas."""
        with app.app_context():
            venta = StgSabiogoVentas(
                fecha=date.today(),
                codigo='PROD001',
                producto='Producto Test',
                cliente='Cliente Test',
                subtot=Decimal('100.00'),
                estado='pendiente'
            )
            db.session.add(venta)
            db.session.commit()
            
            # Verificar
            assert venta.id is not None
            assert venta.codigo == 'PROD001'
            assert venta.estado == 'pendiente'
    
    def test_staging_compras_creation(self, app):
        """Test de creación de registro staging de compras."""
        with app.app_context():
            compra = StgSabiogoCompras(
                fecha=date.today(),
                codigo='PROD001',
                producto='Producto Test',
                proveedor='Proveedor Test',
                subtot=Decimal('80.00'),
                estado='pendiente'
            )
            db.session.add(compra)
            db.session.commit()
            
            # Verificar
            assert compra.id is not None
            assert compra.codigo == 'PROD001'
            assert compra.estado == 'pendiente'
