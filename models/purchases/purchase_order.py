from datetime import datetime

from .. import db


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    id = db.Column(db.Integer, primary_key=True)
    supplier = db.Column(db.String(200), nullable=True)  # Nombre del proveedor
    supplier_id = db.Column(db.Integer, nullable=True)  # ID opcional para futuro FK
    status = db.Column(db.String(50), default="borrador", index=True)
    notes = db.Column(db.Text, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)
    
    # Fechas
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    order_date = db.Column(db.Date, nullable=True, index=True)
    expected_delivery_date = db.Column(db.Date, nullable=True, index=True)

    # Relaciones
    location = db.relationship("Location")
    items = db.relationship("PurchaseOrderItem", backref="order", cascade="all, delete-orphan")
    receipts = db.relationship("PurchaseReceipt", backref="order", cascade="all, delete-orphan")