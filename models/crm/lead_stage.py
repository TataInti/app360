from .. import db


class LeadStage(db.Model):
    __tablename__ = "lead_stages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    position = db.Column(db.Integer, nullable=False, default=0, index=True)
    activo = db.Column(db.Boolean, default=True, nullable=False, index=True)
