from .. import db


class Survey(db.Model):
    __tablename__ = "surveys"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)

    location = db.relationship("Location")
    responses = db.relationship("SurveyResponse", back_populates="survey")