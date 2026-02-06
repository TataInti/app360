from datetime import datetime

from .. import db


class PurchaseReceipt(db.Model):
    __tablename__ = "purchase_receipts"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False, index=True)
    quantity_received = db.Column(db.Integer, nullable=False)
    received_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    product = db.relationship("Product")
    location = db.relationship("Location")