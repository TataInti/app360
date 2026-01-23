from datetime import datetime

from .. import db


class LeadInteraction(db.Model):
    __tablename__ = "lead_interactions"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    contact_date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(60))
    channel = db.Column(db.String(60))
    owner_name = db.Column(db.String(120))
    notes = db.Column(db.Text)

    lead = db.relationship("Lead", backref=db.backref("interactions", order_by=contact_date.desc()))