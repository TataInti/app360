from datetime import datetime

from .. import db


class Client(db.Model):
    __tablename__ = "clients"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=True)  # Código del cliente en ERP
    email = db.Column(db.String(120))
    phone = db.Column(db.String(50))

    # Relaciones
    sales = db.relationship("Venta", back_populates="cliente")