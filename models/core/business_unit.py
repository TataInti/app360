from .. import db


class BusinessUnit(db.Model):
    __tablename__ = "business_units"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)  # Autos, Motos, etc.