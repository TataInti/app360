from .. import db


class Headcount(db.Model):
    __tablename__ = "rrhh_headcount"
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # formato 'YYYY-MM'
    headcount = db.Column(db.Integer, nullable=False)

    location = db.relationship("Location")