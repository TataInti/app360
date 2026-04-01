from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from . import db
from .time_utils import now_local, today_local_date


class CategoriaGasto(db.Model):
    """Categorías de gastos"""
    __tablename__ = 'categoria_gasto'

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text)
    activo = Column(db.Boolean, default=True)

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

    def __repr__(self):
        return f'<Proveedor {self.nombre}>'