from .. import db


class Goal(db.Model):
    __tablename__ = "goals"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True)
    description = db.Column(db.String(250), nullable=False)
    period = db.Column(db.String(20), index=True)  # e.g. '2025-Q4'
    target_value = db.Column(db.Float, nullable=False)
    current_value = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(40), default="en progreso", index=True)

    employee = db.relationship("Employee", back_populates="goals")