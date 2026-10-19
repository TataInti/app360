from decimal import Decimal

from . import db
from .time_utils import now_local


TOLERANCIA_TARDANZA_MIN = 15  # minutos de gracia antes de marcar llegada tarde


class Turno(db.Model):
    """Turnos de trabajo"""
    __tablename__ = 'turnos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)

    # Relaciones
    asistencias = db.relationship("Asistencia", back_populates="turno")
    dias = db.relationship("TurnoDia", back_populates="turno", cascade="all, delete-orphan",
                           order_by="TurnoDia.dia_semana")

    def __repr__(self):
        return f'<Turno {self.nombre}>'


class TurnoDia(db.Model):
    """Configuración de horario por día de la semana para un turno"""
    __tablename__ = 'turno_dias'
    __table_args__ = (
        db.UniqueConstraint('turno_id', 'dia_semana', name='uq_turno_dia'),
    )

    id = db.Column(db.Integer, primary_key=True)
    turno_id = db.Column(db.Integer, db.ForeignKey('turnos.id'), nullable=False)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=lunes .. 6=domingo
    activo = db.Column(db.Boolean, default=True)  # ¿se trabaja este día?
    es_cortado = db.Column(db.Boolean, default=False)  # jornada cortada (2 bloques)
    hora_inicio_1 = db.Column(db.Time)
    hora_fin_1 = db.Column(db.Time)
    hora_inicio_2 = db.Column(db.Time)  # solo si es_cortado
    hora_fin_2 = db.Column(db.Time)    # solo si es_cortado

    turno = db.relationship("Turno", back_populates="dias")

    def __repr__(self):
        dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        nombre_dia = dias[self.dia_semana] if 0 <= self.dia_semana <= 6 else '?'
        return f'<TurnoDia {self.turno_id} {nombre_dia}>'


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
    motivo = db.Column(db.Text)
    justificado = db.Column(db.Boolean, default=False)
    minutos_tarde = db.Column(db.Integer)

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

    # Snapshot de la empresa del empleado al crear el adelanto. No se vuelve a
    # calcular desde Employee para preservar la lectura de períodos pasados.
    empresa = db.Column(db.String(10), nullable=True)
    
    # Tipo: 'adelanto_efectivo', 'adelanto_mercaderia', 'prestamo'
    tipo = db.Column(db.String(30), nullable=False, default='adelanto_efectivo')
    
    # Común para todos
    fecha_solicitud = db.Column(db.DateTime, default=now_local)
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

    __table_args__ = (
        db.CheckConstraint(
            "empresa IS NULL OR empresa IN ('CARNES', 'LACTEOS')",
            name="chk_adelantos_empresa",
        ),
        db.Index('idx_adelantos_empresa_fecha_pago', 'empresa', 'fecha_pago'),
    )

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

    # Snapshot de empresa al liquidar; evita que un traslado de empleado
    # reescriba analíticamente los pagos ya emitidos.
    empresa = db.Column(db.String(10), nullable=True)
    
    # Montos
    sueldo_base = db.Column(db.Numeric(10, 2), nullable=False)
    descuento_adelanto_efectivo = db.Column(db.Numeric(10, 2), default=0)
    descuento_adelanto_mercaderia = db.Column(db.Numeric(10, 2), default=0)
    descuento_cuota_prestamo = db.Column(db.Numeric(10, 2), default=0)
    otros_descuentos = db.Column(db.Numeric(10, 2), default=0)
    sueldo_neto = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Auditoría
    fecha_liquidacion = db.Column(db.DateTime, default=now_local)
    liquidado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    observaciones = db.Column(db.Text)
    
    # Relaciones
    empleado = db.relationship("Employee", backref="liquidaciones")
    liquidado_por = db.relationship("User", backref="liquidaciones_realizadas")

    __table_args__ = (
        db.CheckConstraint(
            "empresa IS NULL OR empresa IN ('CARNES', 'LACTEOS')",
            name="chk_liquidaciones_sueldo_empresa",
        ),
        db.Index(
            'idx_liquidaciones_sueldo_empresa_fecha',
            'empresa',
            'fecha_liquidacion',
        ),
    )
    
    def __repr__(self):
        return f'<LiquidacionSueldo {self.empleado.name} - {self.periodo}>'


class FichadaReloj(db.Model):
    """Fichada cruda importada del reloj biométrico (inmutable)"""
    __tablename__ = 'fichadas_reloj'
    __table_args__ = (
        db.UniqueConstraint('clock_id_original', 'fecha_hora', name='uq_fichada_clock_fechahora'),
        db.Index('ix_fichada_empleado_fecha', 'empleado_id', 'fecha'),
        db.Index('ix_fichadas_clock_id', 'clock_id_original'),
    )

    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    clock_id_original = db.Column(db.String(50), nullable=False)
    nombre_reloj = db.Column(db.String(150))
    fecha = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    fecha_hora = db.Column(db.DateTime, nullable=False)
    archivo_origen = db.Column(db.String(255))
    lote_importacion = db.Column(db.String(40), nullable=False, index=True)

    empleado = db.relationship("Employee", backref="fichadas_reloj")

    def __repr__(self):
        return f'<FichadaReloj {self.empleado_id} {self.fecha_hora}>'


class ResumenAsistenciaDiaria(db.Model):
    """Resumen diario calculado al cruzar fichadas con turnos"""
    __tablename__ = 'resumen_asistencia_diaria'
    __table_args__ = (
        db.UniqueConstraint('empleado_id', 'fecha', name='uq_resumen_empleado_fecha'),
        db.Index('ix_resumen_empleado_fecha', 'empleado_id', 'fecha'),
    )

    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    turno_id = db.Column(db.Integer, db.ForeignKey('turnos.id'), nullable=True)

    fichadas_count = db.Column(db.Integer, default=0)
    fichadas_esperadas = db.Column(db.Integer, default=2)  # 2=corrido, 4=cortado

    hora_entrada_1 = db.Column(db.Time)
    hora_salida_1 = db.Column(db.Time)
    hora_entrada_2 = db.Column(db.Time)
    hora_salida_2 = db.Column(db.Time)

    minutos_tarde_total = db.Column(db.Integer, default=0)
    es_falta = db.Column(db.Boolean, default=False)
    es_tarde = db.Column(db.Boolean, default=False)
    fichada_faltante = db.Column(db.Boolean, default=False)
    justificado = db.Column(db.Boolean, default=False)
    notas = db.Column(db.Text)
    lote_importacion = db.Column(db.String(40), index=True)

    empleado = db.relationship("Employee", backref="resumenes_asistencia")
    turno = db.relationship("Turno")

    def __repr__(self):
        return f'<ResumenAsistenciaDiaria {self.empleado_id} {self.fecha}>'
