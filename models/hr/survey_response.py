from .. import db
from ..time_utils import now_local


class SurveyResponse(db.Model):
    __tablename__ = "survey_responses"
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("surveys.id"), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    comments = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=now_local, index=True)

    survey = db.relationship("Survey", back_populates="responses")
    employee = db.relationship("Employee", back_populates="survey_responses")