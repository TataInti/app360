from . import db
from .time_utils import now_local, today_local_date


# Tabla de asociación M2M: portadores permitidos por instrumento
instrumento_portador = db.Table(
    'instrumento_portador',
    db.Column('instrumento_id', db.Integer,
              db.ForeignKey('instrumentos_pago.id', ondelete='CASCADE'), primary_key=True),
    db.Column('portador_id', db.Integer,
              db.ForeignKey('portador_instrumento.id', ondelete='CASCADE'), primary_key=True),
)


class InstrumentoPago(db.Model):
    __tablename__ = "instrumentos_pago"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)  # efectivo, cheque, tarjeta, etc.
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    requiere_portador = db.Column(db.Boolean, default=False, server_default="0")

    # Relaciones
    movimientos = db.relationship("MovimientoCaja", backref="instrumento", cascade="all, delete-orphan")
    portadores_permitidos = db.relationship(
        "PortadorInstrumento",
        secondary="instrumento_portador",
        backref=db.backref("instrumentos", lazy="dynamic"),
        lazy="select",
    )


class PortadorInstrumento(db.Model):
    """Tercero externo que porta un instrumento (ej: persona que trae un cheque)"""
    __tablename__ = "portador_instrumento"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    documento = db.Column(db.String(30))
    telefono = db.Column(db.String(50))
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now_local)

    movimientos = db.relationship("MovimientoCaja", backref="portador")

    def __repr__(self):
        return f'<PortadorInstrumento {self.nombre}>'


class ArqueoCaja(db.Model):
    __tablename__ = "arqueos_caja"
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=today_local_date)
    turno = db.Column(db.String(20), nullable=False)  # mañana, tarde, noche
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Saldos
    saldo_inicial = db.Column(db.Numeric(12, 2), default=0)
    ingresos_total = db.Column(db.Numeric(12, 2), default=0)
    egresos_total = db.Column(db.Numeric(12, 2), default=0)
    saldo_final = db.Column(db.Numeric(12, 2), default=0)

    # Control
    diferencia = db.Column(db.Numeric(12, 2), default=0)  # saldo_final - (saldo_inicial + ingresos - egresos)
    observaciones = db.Column(db.Text)
    
    # Auditoría de ediciones
    editado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    fecha_edicion = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)

    # Relaciones
    usuario = db.relationship("User", foreign_keys=[usuario_id])
    editado_por = db.relationship("User", foreign_keys=[editado_por_id])
    movimientos = db.relationship("MovimientoCaja", backref="arqueo", cascade="all, delete-orphan")
    logs = db.relationship("LogArqueo", backref="arqueo", cascade="all, delete-orphan", order_by="LogArqueo.fecha_edicion.desc()")

    __table_args__ = (
        db.UniqueConstraint('fecha', 'turno', name='unique_arqueo_fecha_turno'),
    )


class MovimientoCaja(db.Model):
    __tablename__ = "movimientos_caja"
    id = db.Column(db.Integer, primary_key=True)
    fecha_hora = db.Column(db.DateTime, nullable=False, default=now_local)

    # ``NULL`` conserva los movimientos históricos globales. Las nuevas altas
    # se validan en los módulos operativos con los códigos de models.empresa.
    empresa = db.Column(db.String(10), nullable=True)

    tipo = db.Column(db.String(10), nullable=False)  # 'ingreso' o 'egreso'
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)

    # Estado: activo | pendiente_anulacion | anulado
    estado = db.Column(db.String(25), nullable=False, default="activo", server_default="activo")

    # Anulación
    motivo_anulacion = db.Column(db.Text, nullable=True)
    anulado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    autorizado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    fecha_anulacion = db.Column(db.DateTime, nullable=True)

    # Relaciones
    instrumento_id = db.Column(db.Integer, db.ForeignKey("instrumentos_pago.id"), nullable=False)
    arqueo_id = db.Column(db.Integer, db.ForeignKey("arqueos_caja.id"), nullable=True)  # Puede ser null si no está arqueado
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    categoria_gasto_id = db.Column(db.Integer, db.ForeignKey("categoria_gasto.id"), nullable=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedor.id"), nullable=True)
    portador_id = db.Column(db.Integer, db.ForeignKey("portador_instrumento.id"), nullable=True)

    # Datos adicionales
    referencia = db.Column(db.String(100))  # Número de cheque, transacción, etc.
    cliente_proveedor = db.Column(db.String(200))  # Nombre del cliente/proveedor

    # Relaciones
    usuario = db.relationship("User", foreign_keys=[usuario_id])
    anulado_por = db.relationship("User", foreign_keys=[anulado_por_id])
    autorizado_por = db.relationship("User", foreign_keys=[autorizado_por_id])
    categoria_gasto = db.relationship("CategoriaGasto", foreign_keys=[categoria_gasto_id])
    proveedor = db.relationship("Proveedor", foreign_keys=[proveedor_id])

    # Índices
    __table_args__ = (
        db.CheckConstraint(
            "empresa IS NULL OR empresa IN ('CARNES', 'LACTEOS')",
            name="chk_movimientos_caja_empresa",
        ),
        db.Index('idx_movimiento_fecha', 'fecha_hora'),
        db.Index('idx_movimiento_empresa_fecha', 'empresa', 'fecha_hora'),
        db.Index('idx_movimiento_tipo', 'tipo'),
        db.Index('idx_movimiento_instrumento', 'instrumento_id'),
        db.Index('idx_movimiento_estado', 'estado'),
    )


class LogArqueo(db.Model):
    """Log de ediciones realizadas a arqueos de caja"""
    __tablename__ = "logs_arqueo"
    
    id = db.Column(db.Integer, primary_key=True)
    arqueo_id = db.Column(db.Integer, db.ForeignKey("arqueos_caja.id"), nullable=False)
    fecha_edicion = db.Column(db.DateTime, default=now_local, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    # Estado anterior y nuevo (JSON)
    campos_anteriores = db.Column(db.JSON, nullable=False)
    campos_nuevos = db.Column(db.JSON, nullable=False)
    justificacion = db.Column(db.Text, nullable=False)
    
    # Relaciones
    usuario = db.relationship("User")
    
    def __repr__(self):
        return f'<LogArqueo arqueo_id={self.arqueo_id} fecha={self.fecha_edicion}>'


class ArqueoDetalle(db.Model):
    """Detalle por instrumento de un arqueo de caja"""
    __tablename__ = "arqueo_detalle"

    id = db.Column(db.Integer, primary_key=True)
    arqueo_id = db.Column(db.Integer, db.ForeignKey("arqueos_caja.id"), nullable=False)
    instrumento_id = db.Column(db.Integer, db.ForeignKey("instrumentos_pago.id"), nullable=False)
    conteo_real = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    saldo_calculado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diferencia = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Relaciones
    arqueo = db.relationship("ArqueoCaja", backref=db.backref("detalles", cascade="all, delete-orphan"))
    instrumento = db.relationship("InstrumentoPago")

    __table_args__ = (
        db.UniqueConstraint('arqueo_id', 'instrumento_id', name='unique_arqueo_instrumento'),
    )

    def __repr__(self):
        return f'<ArqueoDetalle arqueo={self.arqueo_id} inst={self.instrumento_id}>'


class CuentaCorrienteFriar(db.Model):
    """Cuenta corriente con proveedor Friar"""
    __tablename__ = "cuenta_corriente_friar"
    
    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedor.id"), nullable=False)
    saldo_inicial = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    observaciones = db.Column(db.Text)
    
    # Auditoría de ediciones
    editado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    fecha_edicion = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)
    
    # Relaciones
    proveedor = db.relationship("Proveedor", foreign_keys=[proveedor_id])
    editado_por = db.relationship("User", foreign_keys=[editado_por_id])
    pagos = db.relationship("PagoFriar", backref="cuenta", cascade="all, delete-orphan")
    liquidaciones = db.relationship("LiquidacionFriar", backref="cuenta", cascade="all, delete-orphan")
    logs = db.relationship("LogCuentaCorrienteFriar", backref="cuenta", cascade="all, delete-orphan", order_by="LogCuentaCorrienteFriar.fecha_edicion.desc()")
    
    def __repr__(self):
        return f'<CuentaCorrienteFriar proveedor_id={self.proveedor_id}>'


class LiquidacionFriar(db.Model):
    """Liquidaciones recibidas de Friar (aumentan la deuda)"""
    __tablename__ = "liquidaciones_friar"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_corriente_id = db.Column(db.Integer, db.ForeignKey("cuenta_corriente_friar.id"), nullable=False)
    fecha = db.Column(db.DateTime, default=now_local, nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    tipo = db.Column(db.String(50), nullable=False, default="consignado")  # consignado, no_consignado, ajuste
    descripcion = db.Column(db.String(200), nullable=False)
    referencia = db.Column(db.String(100))  # Nro liquidación Friar
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now_local, nullable=False)

    # Relaciones
    usuario = db.relationship("User")

    __table_args__ = (
        db.Index('idx_liquidacion_friar_fecha', 'fecha'),
        db.Index('idx_liquidacion_friar_cuenta', 'cuenta_corriente_id'),
    )

    def __repr__(self):
        return f'<LiquidacionFriar monto={self.monto} tipo={self.tipo}>'


class PagoFriar(db.Model):
    """Pagos realizados a proveedor Friar"""
    __tablename__ = "pagos_friar"
    
    id = db.Column(db.Integer, primary_key=True)
    cuenta_corriente_id = db.Column(db.Integer, db.ForeignKey("cuenta_corriente_friar.id"), nullable=False)
    fecha = db.Column(db.DateTime, default=now_local, nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    instrumento_id = db.Column(db.Integer, db.ForeignKey("instrumentos_pago.id"), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    referencia = db.Column(db.String(100))  # Número de comprobante, cheque, etc.
    
    # Relaciones
    instrumento = db.relationship("InstrumentoPago")
    usuario = db.relationship("User")
    
    # Índices
    __table_args__ = (
        db.Index('idx_pago_friar_fecha', 'fecha'),
        db.Index('idx_pago_friar_cuenta', 'cuenta_corriente_id'),
    )
    
    def __repr__(self):
        return f'<PagoFriar monto={self.monto} fecha={self.fecha}>'


class LogCuentaCorrienteFriar(db.Model):
    """Log de ediciones realizadas a cuenta corriente Friar"""
    __tablename__ = "logs_cuenta_corriente_friar"
    
    id = db.Column(db.Integer, primary_key=True)
    cuenta_corriente_id = db.Column(db.Integer, db.ForeignKey("cuenta_corriente_friar.id"), nullable=False)
    fecha_edicion = db.Column(db.DateTime, default=now_local, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    # Estado anterior y nuevo (JSON)
    campos_anteriores = db.Column(db.JSON, nullable=False)
    campos_nuevos = db.Column(db.JSON, nullable=False)
    justificacion = db.Column(db.Text, nullable=False)
    
    # Relaciones
    usuario = db.relationship("User")
    
    def __repr__(self):
        return f'<LogCuentaCorrienteFriar cuenta_id={self.cuenta_corriente_id} fecha={self.fecha_edicion}>'
