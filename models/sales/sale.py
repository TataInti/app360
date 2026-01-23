from datetime import datetime

from .. import db


class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="ARS")
    status = db.Column(db.String(40), default="reserva")
    scheduled_delivery = db.Column(db.DateTime, nullable=True)

    lead = db.relationship("Lead", backref="sales")
    product = db.relationship("Product")
    location = db.relationship("Location")

    reservations = db.relationship("StockReservation", backref="sale", cascade="all, delete-orphan")