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

    stage = db.Column(db.String(40), default="nuevo")
    owner_name = db.Column(db.String(120), nullable=True)
    last_contacted_at = db.Column(db.DateTime, nullable=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"), nullable=True)

    business_unit = db.relationship("BusinessUnit")
    product = db.relationship("Product")
    location = db.relationship("Location")
    campaign = db.relationship("Campaign", back_populates="leads")


class Campaign(db.Model):
    __tablename__ = "campaigns"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    channel = db.Column(db.String(120))
    cost_estimate = db.Column(db.Numeric(12, 2), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True)

    leads = db.relationship("Lead", back_populates="campaign")


class LeadInteraction(db.Model):
    __tablename__ = "lead_interactions"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    contact_date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(60))
    channel = db.Column(db.String(60))
    owner_name = db.Column(db.String(120))
    notes = db.Column(db.Text)

    lead = db.relationship("Lead", backref=db.backref("interactions", order_by=contact_date.desc()))

class LeadDemo(db.Model):
    __tablename__ = "lead_demos"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    responsible = db.Column(db.String(120))
    status = db.Column(db.String(40), default="programado")
    notes = db.Column(db.Text)

    lead = db.relationship("Lead", backref="demos")
    product = db.relationship("Product")
    location = db.relationship("Location")


class Quotation(db.Model):
    __tablename__ = "quotations"
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="ARS")
    status = db.Column(db.String(40), default="borrador")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    lead = db.relationship("Lead", backref="quotations")
    product = db.relationship("Product")


class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(10), default="ARS")
    status = db.Column(db.String(40), default="reserva")
    scheduled_delivery = db.Column(db.DateTime, nullable=True)

    lead = db.relationship("Lead", backref="sales")
    product = db.relationship("Product")
    location = db.relationship("Location")

    reservations = db.relationship(
        "StockReservation",
        backref="sale",
        cascade="all, delete-orphan"
    )


class StockReservation(db.Model):
    __tablename__ = "stock_reservations"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(40), default="activa")

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
