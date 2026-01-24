from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from . import db


class CategoriaGasto(db.Model):
    """Categorías de gastos"""
    __tablename__ = 'categoria_gasto'

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text)
    activo = Column(db.Boolean, default=True)

    # Relaciones
    gastos = relationship("Gasto", back_populates="categoria")

    def __repr__(self):
        return f'<CategoriaGasto {self.nombre}>'


class Proveedor(db.Model):
    """Proveedores de servicios y productos"""
    __tablename__ = 'proveedor'

    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    cuit = Column(String(20), unique=True)
    email = Column(String(120))
    telefono = Column(String(50))
    direccion = Column(Text)
    activo = Column(db.Boolean, default=True)

    # Relaciones
    gastos = relationship("Gasto", back_populates="proveedor")

    def __repr__(self):
        return f'<Proveedor {self.nombre}>'


class Gasto(db.Model):
    """Registro de gastos"""
    __tablename__ = 'gasto'

    id = Column(Integer, primary_key=True)
    fecha = Column(Date, nullable=False, default=datetime.utcnow().date)
    descripcion = Column(String(300), nullable=False)
    monto = Column(Numeric(12, 2), nullable=False)
    categoria_id = Column(Integer, ForeignKey('categoria_gasto.id'), nullable=False)
    proveedor_id = Column(Integer, ForeignKey('proveedor.id'), nullable=False)

    # Información adicional
    numero_factura = Column(String(50))
    fecha_vencimiento = Column(Date)
    pagado = Column(db.Boolean, default=False)
    fecha_pago = Column(DateTime)

    # Usuario que registró el gasto
    usuario_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    categoria = relationship("CategoriaGasto", back_populates="gastos")
    proveedor = relationship("Proveedor", back_populates="gastos")
    usuario = relationship("User")

    def __repr__(self):
        return f'<Gasto {self.descripcion} - ${self.monto}>'