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

    # Relaciones
    usuario = db.relationship("User")
    movimientos = db.relationship("MovimientoCaja", backref="arqueo", cascade="all, delete-orphan")

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