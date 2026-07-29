from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, false
from sqlalchemy.orm import relationship

from . import db
from .time_utils import now_local, today_local_date


class CategoriaGasto(db.Model):
    """Concepto estructural para clasificar movimientos de Tesorería.

    El nombre histórico de la tabla se conserva para no romper claves foráneas.
    En la interfaz y APIs nuevas se expone como "Concepto de Tesorería".
    """
    __tablename__ = 'categoria_gasto'

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text)
    naturaleza = Column(String(10), nullable=True)
    incluye_resultado = Column(db.Boolean, nullable=False, default=False, server_default=false())
    activo = Column(db.Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            "naturaleza IS NULL OR naturaleza IN ('ingreso', 'egreso', 'ambos')",
            name="chk_categoria_gasto_naturaleza",
        ),
    )

    @property
    def efecto_resultado(self):
        if not self.incluye_resultado:
            return "no_participa"
        if self.naturaleza == "ingreso":
            return "suma"
        if self.naturaleza == "egreso":
            return "resta"
        if self.naturaleza == "ambos":
            return "segun_movimiento"
        return "pendiente"

    def acepta_tipo(self, tipo):
        return bool(
            self.naturaleza
            and tipo in ("ingreso", "egreso")
            and (self.naturaleza == "ambos" or self.naturaleza == tipo)
        )

    def __repr__(self):
        return f'<CategoriaGasto {self.nombre}>'


class CategoriaMovimientoAudit(db.Model):
    """Auditoría de cambios que pueden recalcular el resultado histórico."""

    __tablename__ = "categoria_movimiento_audit"

    id = Column(Integer, primary_key=True)
    categoria_id = Column(Integer, ForeignKey("categoria_gasto.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    fecha = Column(DateTime, nullable=False, default=now_local, index=True)
    accion = Column(String(20), nullable=False)
    valores_anteriores = Column(db.JSON, nullable=False, default=dict)
    valores_nuevos = Column(db.JSON, nullable=False, default=dict)

    categoria = relationship("CategoriaGasto")
    usuario = relationship("User")


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
