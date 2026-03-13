"""Modelos de staging para tablas stg_sabiogo_ventas y stg_sabiogo_compras."""

from .. import db
from ..time_utils import now_local
from sqlalchemy import CheckConstraint, Index


class StgSabiogoVentas(db.Model):
    """Modelo para staging de ventas importadas desde SabioGo."""
    
    __tablename__ = 'stg_sabiogo_ventas'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Campos importados desde XLS (alineado al esquema real en Postgres)
    rubro = db.Column(db.String(100), nullable=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    subrubro = db.Column(db.String(100), nullable=True)
    # Origen lógico del archivo/datos (CARNES/LACTEOS/LEGACY)
    origen = db.Column(db.String(20), nullable=True, index=True)
    codigo = db.Column(db.String(50), nullable=False, index=True)
    # Código tal como vino del archivo (antes de normalizar)
    codigo_raw = db.Column(db.String(80), nullable=True)
    modelo = db.Column(db.String(100), nullable=True)
    producto = db.Column(db.String(200), nullable=True)
    marca = db.Column(db.String(100), nullable=True)
    comprobante = db.Column(db.String(100), nullable=True)
    nro_comprob = db.Column(db.String(50), nullable=True)
    cliente = db.Column(db.String(200), nullable=True, index=True)
    condicion_iva = db.Column(db.String(50), nullable=True)
    vendedor = db.Column(db.String(100), nullable=True, index=True)
    deposito = db.Column(db.String(100), nullable=True)
    uninegocio = db.Column(db.String(100), nullable=True)
    forma_pago = db.Column(db.String(50), nullable=True)
    localidad = db.Column(db.String(100), nullable=True)
    zona = db.Column(db.String(100), nullable=True)
    sucursal = db.Column(db.String(100), nullable=True, index=True)
    tipo = db.Column(db.String(50), nullable=True)
    
    # Cantidades
    kilos = db.Column(db.Float, default=0)
    cajas = db.Column(db.Float, default=0)
    
    # Importes
    dtos = db.Column(db.Float, default=0)
    neto = db.Column(db.Float, default=0)
    subtot = db.Column(db.Float, default=0)
    iva = db.Column(db.Float, default=0)
    moniva = db.Column(db.Float, default=0)
    numlispre = db.Column(db.Integer, nullable=True)
    lisprec = db.Column(db.Text, nullable=True)
    
    # Metadatos de importación
    fuente_archivo = db.Column(db.String(255), nullable=True)
    fecha_import = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    hash_archivo = db.Column(db.String(64), nullable=True, index=True)
    estado = db.Column(db.String(20), default='pendiente', nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=now_local, nullable=True)
    updated_at = db.Column(db.DateTime, default=now_local, nullable=True)
    
    __table_args__ = (
        Index('idx_stg_ventas_fecha_codigo', 'fecha', 'codigo'),
        Index('idx_stg_ventas_origen_fecha_codigo', 'origen', 'fecha', 'codigo'),
        Index('idx_stg_ventas_cliente_fecha', 'cliente', 'fecha'),
        CheckConstraint("estado IN ('pendiente', 'procesado', 'duplicado', 'error', 'cargado')", name='chk_ventas_estado'),
    )
    
    @classmethod
    def validar_duplicados(cls, session):
        """
        Detecta y marca registros duplicados basándose en campos clave.
        
        Returns:
            int: Número de registros marcados como duplicados
        """
        from sqlalchemy import func, and_
        
        # Subquery para identificar duplicados
        duplicados_sq = session.query(
            cls.nro_comprob,
            cls.tipo,
            cls.fecha,
            cls.codigo,
            cls.subtot,
            func.count().label('count')
        ).filter(
            cls.estado == 'pendiente'
        ).group_by(
            cls.nro_comprob,
            cls.tipo,
            cls.fecha,
            cls.codigo,
            cls.subtot
        ).having(
            func.count() > 1
        ).subquery()
        
        # Marcar duplicados
        count = session.query(cls).filter(
            and_(
                cls.estado == 'pendiente',
                cls.nro_comprob == duplicados_sq.c.nro_comprob,
                cls.tipo == duplicados_sq.c.tipo,
                cls.fecha == duplicados_sq.c.fecha,
                cls.codigo == duplicados_sq.c.codigo,
                cls.subtot == duplicados_sq.c.subtot
            )
        ).update({'estado': 'duplicado'}, synchronize_session=False)
        
        return count


class StgSabiogoCompras(db.Model):
    """Modelo para staging de compras importadas desde SabioGo."""
    
    __tablename__ = 'stg_sabiogo_compras'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Campos importados desde XLS (mismo layout que ventas en staging real)
    rubro = db.Column(db.String(100), nullable=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    subrubro = db.Column(db.String(100), nullable=True)
    # Origen lógico del archivo/datos (CARNES/LACTEOS/LEGACY)
    origen = db.Column(db.String(20), nullable=True, index=True)
    codigo = db.Column(db.String(50), nullable=False, index=True)
    # Código tal como vino del archivo (antes de normalizar)
    codigo_raw = db.Column(db.String(80), nullable=True)
    modelo = db.Column(db.String(100), nullable=True)
    producto = db.Column(db.String(200), nullable=True)
    marca = db.Column(db.String(100), nullable=True)
    comprobante = db.Column(db.String(100), nullable=True)
    nro_comprob = db.Column(db.String(50), nullable=True)
    cliente = db.Column(db.String(200), nullable=True, index=True)
    condicion_iva = db.Column(db.String(50), nullable=True)
    vendedor = db.Column(db.String(100), nullable=True, index=True)
    deposito = db.Column(db.String(100), nullable=True)
    uninegocio = db.Column(db.String(100), nullable=True)
    forma_pago = db.Column(db.String(50), nullable=True)
    localidad = db.Column(db.String(100), nullable=True)
    zona = db.Column(db.String(100), nullable=True)
    sucursal = db.Column(db.String(100), nullable=True, index=True)
    tipo = db.Column(db.String(50), nullable=True)
    
    # Cantidades
    kilos = db.Column(db.Float, default=0)
    cajas = db.Column(db.Float, default=0)
    
    # Importes
    dtos = db.Column(db.Float, default=0)
    neto = db.Column(db.Float, default=0)
    subtot = db.Column(db.Float, default=0)
    iva = db.Column(db.Float, default=0)
    moniva = db.Column(db.Float, default=0)
    numlispre = db.Column(db.Integer, nullable=True)
    lisprec = db.Column(db.Text, nullable=True)
    
    # Metadatos de importación
    fuente_archivo = db.Column(db.String(255), nullable=True)
    fecha_import = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    hash_archivo = db.Column(db.String(64), nullable=True, index=True)
    estado = db.Column(db.String(20), default='pendiente', nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=now_local, nullable=True)
    updated_at = db.Column(db.DateTime, default=now_local, nullable=True)
    
    __table_args__ = (
        Index('idx_stg_compras_fecha_codigo', 'fecha', 'codigo'),
        Index('idx_stg_compras_origen_fecha_codigo', 'origen', 'fecha', 'codigo'),
        Index('idx_stg_compras_cliente_fecha', 'cliente', 'fecha'),
        CheckConstraint("estado IN ('pendiente', 'procesado', 'duplicado', 'error', 'cargado')", name='chk_compras_estado'),
    )
    
    @classmethod
    def validar_duplicados(cls, session):
        """
        Detecta y marca registros duplicados basándose en campos clave.
        
        Returns:
            int: Número de registros marcados como duplicados
        """
        from sqlalchemy import func, and_
        
        # Subquery para identificar duplicados
        duplicados_sq = session.query(
            cls.nro_comprob,
            cls.tipo,
            cls.fecha,
            cls.codigo,
            cls.subtot,
            func.count().label('count')
        ).filter(
            cls.estado == 'pendiente'
        ).group_by(
            cls.nro_comprob,
            cls.tipo,
            cls.fecha,
            cls.codigo,
            cls.subtot
        ).having(
            func.count() > 1
        ).subquery()
        
        # Marcar duplicados
        count = session.query(cls).filter(
            and_(
                cls.estado == 'pendiente',
                cls.nro_comprob == duplicados_sq.c.nro_comprob,
                cls.tipo == duplicados_sq.c.tipo,
                cls.fecha == duplicados_sq.c.fecha,
                cls.codigo == duplicados_sq.c.codigo,
                cls.subtot == duplicados_sq.c.subtot
            )
        ).update({'estado': 'duplicado'}, synchronize_session=False)
        
        return count
