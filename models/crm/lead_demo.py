from datetime import datetime

from .. import db


class LeadDemo(db.Model):
    __tablename__ = "lead_demos"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    responsible = db.Column(db.String(120))
    status = db.Column(db.String(40), default="programado")
    notes = db.Column(db.Text)

    lead = db.relationship("Lead", backref="demos")
    product = db.relationship("Product")
    location = db.relationship("Location")