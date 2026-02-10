from .. import db
from ..time_utils import now_local


class LeadStageHistory(db.Model):
    __tablename__ = "lead_stage_history"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, index=True)
    from_stage = db.Column(db.String(80), nullable=True, index=True)
    to_stage = db.Column(db.String(80), nullable=True, index=True)
    comment = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=now_local, index=True)
    created_by = db.Column(db.String(120), nullable=True, index=True)

    lead = db.relationship("Lead", back_populates="stage_history")
