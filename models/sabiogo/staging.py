"""Modelos de staging para tablas stg_sabiogo_ventas y stg_sabiogo_compras."""

from .. import db
from ..time_utils import now_local
from sqlalchemy import CheckConstraint, Index


class StgSabiogoVentas(db.Model):
    """Modelo para staging de ventas importadas desde SabioGo."""
    
    __tablename__ = 'stg_sabiogo_ventas'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Campos importados desde XLS
    rubro = db.Column(db.String(100), nullable=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    codigo = db.Column(db.String(50), nullable=False, index=True)
    producto = db.Column(db.String(200), nullable=True)
    cliente = db.Column(db.String(200), nullable=True, index=True)
    vendedor = db.Column(db.String(100), nullable=True, index=True)
    sucursal = db.Column(db.String(100), nullable=True, index=True)
    deposito = db.Column(db.String(100), nullable=True)
    uninegocio = db.Column(db.String(100), nullable=True)
    zona = db.Column(db.String(100), nullable=True)
    localidad = db.Column(db.String(100), nullable=True)
    condicion_iva = db.Column(db.String(50), nullable=True)
    forma_pago = db.Column(db.String(50), nullable=True)
    tipo = db.Column(db.String(50), nullable=True)
    nro_comprob = db.Column(db.String(50), nullable=True)
    
    # Cantidades
    kilos = db.Column(db.Numeric(12, 3), default=0)
    cajas = db.Column(db.Numeric(12, 2), default=0)
    
    # Importes
    neto = db.Column(db.Numeric(12, 2), default=0)
    subtot = db.Column(db.Numeric(12, 2), default=0)
    iva = db.Column(db.Numeric(12, 2), default=0)
    percep_iva = db.Column(db.Numeric(12, 2), default=0)
    iibb = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    
    # Información adicional
    marca = db.Column(db.String(100), nullable=True)
    modelo = db.Column(db.String(100), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    senia = db.Column(db.Numeric(12, 2), default=0)
    
    # Metadatos de importación
    fuente_archivo = db.Column(db.String(255), nullable=True)
    fecha_import = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    hash_archivo = db.Column(db.String(64), nullable=True, index=True)
    estado = db.Column(db.String(20), default='pendiente', nullable=False, index=True)
    observaciones = db.Column(db.Text, nullable=True)
    
    __table_args__ = (
        Index('idx_stg_ventas_fecha_codigo', 'fecha', 'codigo'),
        Index('idx_stg_ventas_cliente_fecha', 'cliente', 'fecha'),
        CheckConstraint("estado IN ('pendiente', 'procesado', 'duplicado', 'error')", name='chk_ventas_estado'),
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
        
        session.commit()
        return count


class StgSabiogoCompras(db.Model):
    """Modelo para staging de compras importadas desde SabioGo."""
    
    __tablename__ = 'stg_sabiogo_compras'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Campos importados desde XLS
    rubro = db.Column(db.String(100), nullable=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    codigo = db.Column(db.String(50), nullable=False, index=True)
    producto = db.Column(db.String(200), nullable=True)
    proveedor = db.Column(db.String(200), nullable=True, index=True)
    sucursal = db.Column(db.String(100), nullable=True, index=True)
    deposito = db.Column(db.String(100), nullable=True)
    uninegocio = db.Column(db.String(100), nullable=True)
    condicion_iva = db.Column(db.String(50), nullable=True)
    forma_pago = db.Column(db.String(50), nullable=True)
    tipo = db.Column(db.String(50), nullable=True)
    nro_comprob = db.Column(db.String(50), nullable=True)
    
    # Cantidades
    kilos = db.Column(db.Numeric(12, 3), default=0)
    cajas = db.Column(db.Numeric(12, 2), default=0)
    
    # Importes
    neto = db.Column(db.Numeric(12, 2), default=0)
    subtot = db.Column(db.Numeric(12, 2), default=0)
    iva = db.Column(db.Numeric(12, 2), default=0)
    percep_iva = db.Column(db.Numeric(12, 2), default=0)
    iibb = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    
    # Información adicional
    marca = db.Column(db.String(100), nullable=True)
    modelo = db.Column(db.String(100), nullable=True)
    
    # Metadatos de importación
    fuente_archivo = db.Column(db.String(255), nullable=True)
    fecha_import = db.Column(db.DateTime, default=now_local, nullable=False, index=True)
    hash_archivo = db.Column(db.String(64), nullable=True, index=True)
    estado = db.Column(db.String(20), default='pendiente', nullable=False, index=True)
    observaciones = db.Column(db.Text, nullable=True)
    
    __table_args__ = (
        Index('idx_stg_compras_fecha_codigo', 'fecha', 'codigo'),
        Index('idx_stg_compras_proveedor_fecha', 'proveedor', 'fecha'),
        CheckConstraint("estado IN ('pendiente', 'procesado', 'duplicado', 'error')", name='chk_compras_estado'),
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
        
        session.commit()
        return count
