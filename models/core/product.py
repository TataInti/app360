from datetime import datetime

from .. import db


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(80), unique=True, nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=True)
    category = db.Column(db.String(120), nullable=True)
    stock_quantity = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=0)
    business_unit_id = db.Column(db.Integer, db.ForeignKey("business_units.id"), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    business_unit = db.relationship("BusinessUnit", backref="products")
    location = db.relationship("Location", backref="products")