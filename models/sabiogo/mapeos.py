"""Modelos de mapeo entre códigos SabioGo y entidades del sistema."""

from .. import db
from ..time_utils import now_local
from sqlalchemy import UniqueConstraint, Index


class SabiogoProductMap(db.Model):
    """Mapeo entre códigos de producto SabioGo y productos del sistema."""
    
    __tablename__ = 'sabiogo_product_map'
    
    id = db.Column(db.Integer, primary_key=True)
    # Origen lógico del catálogo (CARNES/LACTEOS/LEGACY)
    origen = db.Column(db.String(20), nullable=True, index=True)
    codigo = db.Column(db.String(50), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    
    # Información adicional del producto SabioGo
    marca = db.Column(db.String(100), nullable=True)
    modelo = db.Column(db.String(100), nullable=True)
    producto_descripcion = db.Column(db.String(200), nullable=True)
    
    # Control
    activo = db.Column(db.Boolean, default=True, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local)
    observaciones = db.Column(db.Text, nullable=True)
    
    # Relación con producto
    product = db.relationship('Product', backref='sabiogo_maps', lazy='select')
    
    __table_args__ = (
        UniqueConstraint('origen', 'codigo', name='uq_sabiogo_product_map_origen_codigo'),
        Index('idx_sabiogo_product_active', 'activo', 'product_id'),
    )
    
    def __repr__(self):
        return f'<SabiogoProductMap origen={self.origen} codigo={self.codigo} product_id={self.product_id}>'


class SabiogoClientMap(db.Model):
    """Mapeo entre clientes SabioGo y clientes del sistema."""
    
    __tablename__ = 'sabiogo_client_map'
    
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(200), nullable=False, index=True)
    condicion_iva = db.Column(db.String(50), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True, index=True)
    
    # Información adicional del cliente SabioGo
    zona = db.Column(db.String(100), nullable=True)
    localidad = db.Column(db.String(100), nullable=True)
    
    # Control
    activo = db.Column(db.Boolean, default=True, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local)
    observaciones = db.Column(db.Text, nullable=True)
    
    # Relación con cliente
    client = db.relationship('Client', backref='sabiogo_maps', lazy='select')
    
    __table_args__ = (
        Index('idx_sabiogo_client_composite', 'cliente', 'condicion_iva'),
        Index('idx_sabiogo_client_active', 'activo', 'client_id'),
    )
    
    def __repr__(self):
        return f'<SabiogoClientMap cliente={self.cliente} client_id={self.client_id}>'


class SabiogoLocationMap(db.Model):
    """Mapeo entre sucursales/depósitos SabioGo y ubicaciones del sistema."""
    
    __tablename__ = 'sabiogo_location_map'
    
    id = db.Column(db.Integer, primary_key=True)
    sucursal = db.Column(db.String(100), nullable=False)
    deposito = db.Column(db.String(100), nullable=True)
    uninegocio = db.Column(db.String(100), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True, index=True)
    
    # Información adicional
    canal = db.Column(db.String(50), nullable=True)  # mayorista, minorista, export, etc.
    
    # Control
    activo = db.Column(db.Boolean, default=True, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local)
    observaciones = db.Column(db.Text, nullable=True)
    
    # Relación con ubicación
    location = db.relationship('Location', backref='sabiogo_maps', lazy='select')
    
    __table_args__ = (
        UniqueConstraint('sucursal', 'deposito', name='uq_sabiogo_location'),
        Index('idx_sabiogo_location_active', 'activo', 'location_id'),
    )
    
    def __repr__(self):
        return f'<SabiogoLocationMap sucursal={self.sucursal} location_id={self.location_id}>'


class LogSabiogoCarga(db.Model):
    """Registro de auditoría para cargas de datos SabioGo."""
    
    __tablename__ = 'logs_sabiogo_carga'
    
    id = db.Column(db.Integer, primary_key=True)
    fecha_carga = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    archivo_nombre = db.Column(db.String(255), nullable=False)
    tipo_carga = db.Column(db.String(20), nullable=False)  # 'ventas' o 'compras'
    hash_archivo = db.Column(db.String(64), nullable=True)
    
    # Estadísticas de la carga
    filas_insertadas = db.Column(db.Integer, default=0)
    filas_duplicadas = db.Column(db.Integer, default=0)
    filas_sin_mapeo = db.Column(db.Integer, default=0)
    filas_error = db.Column(db.Integer, default=0)
    
    # Usuario y observaciones
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    
    # Relación
    usuario = db.relationship('User', backref='sabiogo_cargas', lazy='select')
    
    __table_args__ = (
        Index('idx_sabiogo_log_tipo_fecha', 'tipo_carga', 'fecha_carga'),
    )
    
    def __repr__(self):
        return f'<LogSabiogoCarga {self.tipo_carga} {self.archivo_nombre}>'
