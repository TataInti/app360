from .. import db


class Location(db.Model):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)  # Sucursal 1, Nave Central, etc.
    address = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    zip_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), default='México')
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(140), nullable=True)
    manager_name = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    type = db.Column(db.String(50))  # sucursal, nave