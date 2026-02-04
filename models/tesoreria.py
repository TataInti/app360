from datetime import datetime

from . import db


class InstrumentoPago(db.Model):
    __tablename__ = "instrumentos_pago"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)  # efectivo, cheque, tarjeta, etc.
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)

    # Relaciones
    movimientos = db.relationship("MovimientoCaja", backref="instrumento", cascade="all, delete-orphan")


class DestinoArqueo(db.Model):
    """Catálogo de destinos para arqueos de caja (donde va el dinero)"""
    __tablename__ = "destinos_arqueo"
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    
    # Relaciones
    arqueos = db.relationship("ArqueoCaja", backref="destino")
    
    def __repr__(self):
        return f'<DestinoArqueo {self.nombre}>'


class ArqueoCaja(db.Model):
    __tablename__ = "arqueos_caja"
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
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
    
    # Destino del arqueo (opcional)
    destino_id = db.Column(db.Integer, db.ForeignKey("destinos_arqueo.id"), nullable=True)
    
    # Auditoría de ediciones
    editado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    fecha_edicion = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

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
    fecha_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tipo = db.Column(db.String(10), nullable=False)  # 'ingreso' o 'egreso'
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)

    # Relaciones
    instrumento_id = db.Column(db.Integer, db.ForeignKey("instrumentos_pago.id"), nullable=False)
    arqueo_id = db.Column(db.Integer, db.ForeignKey("arqueos_caja.id"), nullable=True)  # Puede ser null si no está arqueado
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Datos adicionales
    referencia = db.Column(db.String(100))  # Número de cheque, transacción, etc.
    cliente_proveedor = db.Column(db.String(200))  # Nombre del cliente/proveedor

    # Relaciones
    usuario = db.relationship("User")

    # Índices
    __table_args__ = (
        db.Index('idx_movimiento_fecha', 'fecha_hora'),
        db.Index('idx_movimiento_tipo', 'tipo'),
        db.Index('idx_movimiento_instrumento', 'instrumento_id'),
    )


class LogArqueo(db.Model):
    """Log de ediciones realizadas a arqueos de caja"""
    __tablename__ = "logs_arqueo"
    
    id = db.Column(db.Integer, primary_key=True)
    arqueo_id = db.Column(db.Integer, db.ForeignKey("arqueos_caja.id"), nullable=False)
    fecha_edicion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    # Estado anterior y nuevo (JSON)
    campos_anteriores = db.Column(db.JSON, nullable=False)
    campos_nuevos = db.Column(db.JSON, nullable=False)
    justificacion = db.Column(db.Text, nullable=False)
    
    # Relaciones
    usuario = db.relationship("User")
    
    def __repr__(self):
        return f'<LogArqueo arqueo_id={self.arqueo_id} fecha={self.fecha_edicion}>'
