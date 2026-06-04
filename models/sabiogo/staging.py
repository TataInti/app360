"""Modelos de staging para tablas stg_sabiogo_ventas y stg_sabiogo_compras."""

from .. import db
from ..time_utils import now_local
from sqlalchemy import CheckConstraint, Index


def _marcar_duplicados_para_descarte(session, model_class):
    """Marca únicamente filas que deben descartarse por duplicidad.

    Reglas:
    - Cross-carga: toda fila pendiente cuya firma ya exista en procesado.
    - Intra-lote: si hay varias pendientes con la misma firma, se conserva la
      primera y se marcan las restantes.
    """
    from sqlalchemy import func, select, tuple_

    firma_cols = (
        model_class.nro_comprob,
        model_class.tipo,
        model_class.fecha,
        model_class.codigo,
        model_class.subtot,
    )

    firmas_existentes_sq = session.query(
        model_class.nro_comprob.label('nro_comprob'),
        model_class.tipo.label('tipo'),
        model_class.fecha.label('fecha'),
        model_class.codigo.label('codigo'),
        model_class.subtot.label('subtot'),
    ).filter(
        model_class.estado == 'procesado'
    ).group_by(
        *firma_cols,
    ).subquery()

    cross_ids_sq = session.query(model_class.id.label('id')).filter(
        model_class.estado == 'pendiente',
        tuple_(*firma_cols).in_(
            select(
                firmas_existentes_sq.c.nro_comprob,
                firmas_existentes_sq.c.tipo,
                firmas_existentes_sq.c.fecha,
                firmas_existentes_sq.c.codigo,
                firmas_existentes_sq.c.subtot,
            )
        ),
    ).subquery()

    cross_count = session.query(model_class).filter(
        model_class.id.in_(select(cross_ids_sq.c.id))
    ).update({'estado': 'duplicado'}, synchronize_session=False)

    pendientes_ranked_sq = session.query(
        model_class.id.label('id'),
        func.row_number().over(
            partition_by=firma_cols,
            order_by=model_class.id.asc(),
        ).label('rn'),
    ).filter(
        model_class.estado == 'pendiente'
    ).subquery()

    intra_count = session.query(model_class).filter(
        model_class.id.in_(
            select(pendientes_ranked_sq.c.id).where(pendientes_ranked_sq.c.rn > 1)
        )
    ).update({'estado': 'duplicado'}, synchronize_session=False)

    return int(cross_count or 0) + int(intra_count or 0)


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
        Se marcan sólo las filas que deben descartarse.
        
        Returns:
            int: Número de registros marcados como duplicados
        """
        return _marcar_duplicados_para_descarte(session, cls)


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
        Se marcan sólo las filas que deben descartarse.
        
        Returns:
            int: Número de registros marcados como duplicados
        """
        return _marcar_duplicados_para_descarte(session, cls)
