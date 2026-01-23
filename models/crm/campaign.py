from .. import db


class Campaign(db.Model):
    __tablename__ = "campaigns"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    channel = db.Column(db.String(120))
    cost_estimate = db.Column(db.Numeric(12, 2), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True)

    leads = db.relationship("Lead", back_populates="campaign")