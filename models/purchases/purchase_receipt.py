from .. import db
from ..time_utils import now_local


class PurchaseReceipt(db.Model):
    __tablename__ = "purchase_receipts"
    id = db.Column(db.Integer, primary_key=True)
    # La columna real se llama purchase_order_id (base de producción y cadena de
    # migraciones). El atributo conserva el nombre order_id para no cambiar el código.
    order_id = db.Column(
        "purchase_order_id", db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False, index=True)
    quantity_received = db.Column(db.Integer, nullable=False)
    received_at = db.Column(db.DateTime, default=now_local, index=True)

    product = db.relationship("Product")
    location = db.relationship("Location")