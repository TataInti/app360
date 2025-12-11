from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class BusinessUnit(db.Model):
    __tablename__ = "business_units"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)   # Autos, Motos, etc.

class Location(db.Model):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)   # Sucursal 1, Nave Central, etc.
    type = db.Column(db.String(50))                    # sucursal, nave

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    business_unit_id = db.Column(db.Integer, db.ForeignKey("business_units.id"), nullable=False)
    category = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    business_unit = db.relationship("BusinessUnit", backref="products")

class StockLevel(db.Model):
    __tablename__ = "stock_levels"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    quantity = db.Column(db.Integer, default=0)

    product = db.relationship("Product", backref="stock")
    location = db.relationship("Location")

class Lead(db.Model):
    __tablename__ = "leads"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))

    source = db.Column(db.String(50))  # Meta, Google, Orgánico, referido, etc.
    status = db.Column(db.String(50), default="nuevo")  
    # Estados: nuevo, contactado, propuesta, ganado, perdido

    business_unit_id = db.Column(db.Integer, db.ForeignKey("business_units.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)

    business_unit = db.relationship("BusinessUnit")
    product = db.relationship("Product")
    location = db.relationship("Location")

# ======================
# MÓDULO COMPRAS
# ======================

class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.Column(db.String(200), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    status = db.Column(db.String(50), default="borrador")  # borrador, enviada, recibida, cerrada
    notes = db.Column(db.Text, nullable=True)

    location = db.relationship("Location")
    items = db.relationship(
        "PurchaseOrderItem",
        backref="order",
        cascade="all, delete-orphan"
    )


class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")


# ======================
# MÓDULO RRHH
# ======================

class Headcount(db.Model):
    __tablename__ = "rrhh_headcount"
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # formato 'YYYY-MM'
    headcount = db.Column(db.Integer, nullable=False)

    location = db.relationship("Location")


class Absence(db.Model):
    __tablename__ = "rrhh_absence"
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # formato 'YYYY-MM'
    days_lost = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(255), nullable=True)

    location = db.relationship("Location")
