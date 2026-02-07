from .. import db
from ..time_utils import now_local


class StockReservation(db.Model):
    __tablename__ = "stock_reservations"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=now_local)
    status = db.Column(db.String(40), default="activa")

    product = db.relationship("Product")
    location = db.relationship("Location")