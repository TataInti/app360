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
    """Adelantos de sueldo y préstamos a empleados"""
    __tablename__ = 'adelantos'

    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    
    # Tipo: 'adelanto_efectivo', 'adelanto_mercaderia', 'prestamo'
    tipo = db.Column(db.String(30), nullable=False, default='adelanto_efectivo')
    
    # Común para todos
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    concepto = db.Column(db.Text, nullable=False)  # antes: motivo
    
    # Para adelantos: mes al que aplica (formato YYYY-MM)
    mes_aplicacion = db.Column(db.String(7))  # ej: "2026-02"
    
    # Para préstamos
    cantidad_cuotas = db.Column(db.Integer)  # número de cuotas
    interes_porcentaje = db.Column(db.Numeric(5, 2))  # % de interés
    cuotas_pagadas = db.Column(db.Integer, default=0)  # cuotas ya descontadas
    
    # Estados
    aprobado = db.Column(db.Boolean, default=False)
    fecha_aprobacion = db.Column(db.DateTime)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    pagado = db.Column(db.Boolean, default=False)  # para adelantos: si fue entregado
    fecha_pago = db.Column(db.DateTime)
    liquidado = db.Column(db.Boolean, default=False)  # si fue descontado del sueldo
    fecha_liquidacion = db.Column(db.DateTime)

    # Relaciones
    empleado = db.relationship("Employee", backref="adelantos")
    aprobado_por = db.relationship("User", backref="adelantos_aprobados")

    def __repr__(self):
        return f'<Adelanto {self.tipo} - {self.empleado.name} - ${self.monto}>'
    
    def calcular_monto_cuota(self):
        """Calcula el monto de cada cuota para préstamos con interés"""
        if self.tipo != 'prestamo' or not self.cantidad_cuotas:
            return self.monto
        
        # Monto total con interés
        monto_total = float(self.monto) * (1 + float(self.interes_porcentaje or 0) / 100)
        return Decimal(str(monto_total / self.cantidad_cuotas))
    
    def saldo_pendiente(self):
        """Retorna el saldo pendiente de un préstamo"""
        if self.tipo != 'prestamo':
            return Decimal('0') if self.liquidado else self.monto
        
        cuota = self.calcular_monto_cuota()
        cuotas_restantes = (self.cantidad_cuotas or 0) - (self.cuotas_pagadas or 0)
        return cuota * cuotas_restantes


class LiquidacionSueldo(db.Model):
    """Liquidación mensual de sueldos"""
    __tablename__ = 'liquidaciones_sueldo'
    
    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    periodo = db.Column(db.String(7), nullable=False)  # YYYY-MM
    
    # Montos
    sueldo_base = db.Column(db.Numeric(10, 2), nullable=False)
    descuento_adelanto_efectivo = db.Column(db.Numeric(10, 2), default=0)
    descuento_adelanto_mercaderia = db.Column(db.Numeric(10, 2), default=0)
    descuento_cuota_prestamo = db.Column(db.Numeric(10, 2), default=0)
    otros_descuentos = db.Column(db.Numeric(10, 2), default=0)
    sueldo_neto = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Auditoría
    fecha_liquidacion = db.Column(db.DateTime, default=datetime.utcnow)
    liquidado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    observaciones = db.Column(db.Text)
    
    # Relaciones
    empleado = db.relationship("Employee", backref="liquidaciones")
    liquidado_por = db.relationship("User", backref="liquidaciones_realizadas")
    
    def __repr__(self):
        return f'<LiquidacionSueldo {self.empleado.name} - {self.periodo}>'