from .. import db


class Absence(db.Model):
    __tablename__ = "rrhh_absence"
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # formato 'YYYY-MM'
    days_lost = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(255), nullable=True)

    location = db.relationship("Location")