from .. import db
from ..time_utils import now_local


class Venta(db.Model):
    __tablename__ = "ventas"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=now_local)

    # Datos importados del CSV
    fecha = db.Column(db.Date, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_contrato = db.Column(db.Numeric(12, 2), nullable=False)  # Precio vendido por contrato
    precio_efectivo = db.Column(db.Numeric(12, 2), nullable=False)  # Precio real cobrado

    # Relaciones
    cliente = db.relationship("Client", back_populates="sales")
    producto = db.relationship("Product")

    # Índices para optimización
    __table_args__ = (
        db.Index('idx_venta_fecha', 'fecha'),
        db.Index('idx_venta_cliente', 'cliente_id'),
        db.Index('idx_venta_producto', 'producto_id'),
    )