from .. import db
from ..time_utils import now_local


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    id = db.Column(db.Integer, primary_key=True)
    supplier = db.Column(db.String(200), nullable=True)  # Nombre del proveedor
    supplier_id = db.Column(db.Integer, nullable=True)  # ID opcional para proveedor existente
    status = db.Column(db.String(50), default="borrador", index=True)
    notes = db.Column(db.Text, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)
    comprobante_numero = db.Column(db.String(100), nullable=True)
    monto_total = db.Column(db.Numeric(12, 2), nullable=True)
    instrumento_id = db.Column(db.Integer, db.ForeignKey("instrumentos_pago.id"), nullable=True, index=True)
    tesoreria_movimiento_id = db.Column(db.Integer, db.ForeignKey("movimientos_caja.id"), nullable=True)
    
    # Fechas
    created_at = db.Column(db.DateTime, default=now_local, index=True)
    order_date = db.Column(db.Date, nullable=True, index=True)
    expected_delivery_date = db.Column(db.Date, nullable=True, index=True)

    # Relaciones
    location = db.relationship("Location")
    instrumento = db.relationship("InstrumentoPago")
    tesoreria_movimiento = db.relationship("MovimientoCaja")
    items = db.relationship("PurchaseOrderItem", backref="order", cascade="all, delete-orphan")
    receipts = db.relationship("PurchaseReceipt", backref="order", cascade="all, delete-orphan")