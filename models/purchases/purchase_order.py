from .. import db
from ..time_utils import now_local


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    id = db.Column(db.Integer, primary_key=True)
    supplier = db.Column(db.String(200), nullable=True)  # Nombre del proveedor
    supplier_id = db.Column(db.Integer, nullable=True)  # ID opcional para proveedor existente
    # ``NULL`` identifica órdenes históricas aún no atribuidas.
    empresa = db.Column(db.String(10), nullable=True)

    # Campos principales (compat con esquema actual en DB)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)

    status = db.Column(db.String(50), default="borrador", index=True)
    notes = db.Column(db.Text, nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)
    comprobante_numero = db.Column(db.String(100), nullable=True)
    monto_total = db.Column(db.Numeric(12, 2), nullable=True)
    instrumento_id = db.Column(db.Integer, db.ForeignKey("instrumentos_pago.id"), nullable=True, index=True)
    tesoreria_movimiento_id = db.Column(db.Integer, db.ForeignKey("movimientos_caja.id"), nullable=True)
    
    # Fechas
    created_at = db.Column(db.DateTime, default=now_local, index=True)
    order_date = db.Column(db.Date, nullable=True, index=True)
    expected_delivery_date = db.Column(db.Date, nullable=True, index=True)

    # Relaciones
    product = db.relationship("Product")
    location = db.relationship("Location")
    instrumento = db.relationship("InstrumentoPago")
    tesoreria_movimiento = db.relationship("MovimientoCaja")
    items = db.relationship("PurchaseOrderItem", backref="order", cascade="all, delete-orphan")
    receipts = db.relationship("PurchaseReceipt", backref="order", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint(
            "empresa IS NULL OR empresa IN ('CARNES', 'LACTEOS')",
            name="chk_purchase_orders_empresa",
        ),
        db.Index(
            "idx_purchase_orders_empresa_order_date",
            "empresa",
            "order_date",
        ),
    )
