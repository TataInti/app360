from . import db
from .time_utils import now_local, today_local_date


class InstrumentoPago(db.Model):
    __tablename__ = "instrumentos_pago"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)  # efectivo, cheque, tarjeta, etc.
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)

    # Relaciones
    movimientos = db.relationship("MovimientoCaja", backref="instrumento", cascade="all, delete-orphan")


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
    destino_id = db.Column(db.Integer, nullable=True)  # ID del origen o destino del movimiento (sin FK)

    # Datos adicionales
    referencia = db.Column(db.String(100))  # Número de cheque, transacción, etc.
    cliente_proveedor = db.Column(db.String(200))  # Nombre del cliente/proveedor

    # Relaciones
    usuario = db.relationship("User", foreign_keys=[usuario_id])
    anulado_por = db.relationship("User", foreign_keys=[anulado_por_id])
    autorizado_por = db.relationship("User", foreign_keys=[autorizado_por_id])

    # Índices
    __table_args__ = (
        db.Index('idx_movimiento_fecha', 'fecha_hora'),
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
    logs = db.relationship("LogCuentaCorrienteFriar", backref="cuenta", cascade="all, delete-orphan", order_by="LogCuentaCorrienteFriar.fecha_edicion.desc()")
    
    def __repr__(self):
        return f'<CuentaCorrienteFriar proveedor_id={self.proveedor_id}>'


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
