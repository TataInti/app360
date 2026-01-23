from datetime import datetime

from .. import db


class Lead(db.Model):
    __tablename__ = "leads"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))

    source = db.Column(db.String(50))  # Meta, Google, Orgánico, referido, etc.
    status = db.Column(db.String(50), default="nuevo")
    # Estados: nuevo, contactado, propuesta, ganado, perdido

    business_unit_id = db.Column(db.Integer, db.ForeignKey("business_units.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)

    stage = db.Column(db.String(40), default="nuevo")
    owner_name = db.Column(db.String(120), nullable=True)
    last_contacted_at = db.Column(db.DateTime, nullable=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=True)

    business_unit = db.relationship("BusinessUnit")
    product = db.relationship("Product")
    location = db.relationship("Location")
    campaign = db.relationship("Campaign", back_populates="leads")