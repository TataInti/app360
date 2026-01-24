from datetime import datetime
from decimal import Decimal

from . import db


class Turno(db.Model):
    """Turnos de trabajo"""
    __tablename__ = 'turnos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    dias_semana = db.Column(db.String(20))  # Ej: "1,2,3,4,5" (lunes a viernes)
    activo = db.Column(db.Boolean, default=True)

    # Relaciones
    asistencias = db.relationship("Asistencia", back_populates="turno")

    def __repr__(self):
        return f'<Turno {self.nombre}>'


class Asistencia(db.Model):
    """Registro de asistencia por turnos"""
    __tablename__ = 'asistencia'

    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    turno_id = db.Column(db.Integer, db.ForeignKey('turnos.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    hora_entrada = db.Column(db.DateTime)
    hora_salida = db.Column(db.DateTime)
    horas_trabajadas = db.Column(db.Numeric(4, 2))
    estado = db.Column(db.String(20), default='presente')  # presente, ausente, llegada_tarde, salida_temprana
    notas = db.Column(db.Text)

    # Relaciones
    empleado = db.relationship("Employee", backref="asistencias_turnos")
    turno = db.relationship("Turno", back_populates="asistencias")

    def __repr__(self):
        return f'<Asistencia {self.empleado.name} - {self.fecha}>'


class Adelanto(db.Model):
    """Adelantos de sueldo"""
    __tablename__ = 'adelantos'

    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    aprobado = db.Column(db.Boolean, default=False)
    fecha_aprobacion = db.Column(db.DateTime)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    pagado = db.Column(db.Boolean, default=False)
    fecha_pago = db.Column(db.DateTime)

    # Relaciones
    empleado = db.relationship("Employee", backref="adelantos")
    aprobado_por = db.relationship("User", backref="adelantos_aprobados")

    def __repr__(self):
        return f'<Adelanto {self.empleado.name} - ${self.monto}>'