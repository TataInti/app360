from decimal import Decimal

from . import db
from .time_utils import now_local


class Promocion(db.Model):
    __tablename__ = "promociones"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    tipo = db.Column(db.String(50), nullable=False)  # descuento, combo, liquidacion
    valor = db.Column(db.Numeric(10, 2), nullable=False)  # porcentaje o monto fijo
    activo = db.Column(db.Boolean, default=True)

    # Fechas de vigencia
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)

    # Condiciones
    producto_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)  # null = todos los productos
    cliente_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)  # null = todos los clientes
    cantidad_minima = db.Column(db.Integer, default=1)  # cantidad mínima para aplicar
    monto_minimo = db.Column(db.Numeric(12, 2), default=0)  # monto mínimo para aplicar

    # Relaciones
    producto = db.relationship("Product")
    cliente = db.relationship("Client")
    aplicaciones = db.relationship("PromocionAplicada", backref="promocion", cascade="all, delete-orphan")

    # Índices
    __table_args__ = (
        db.Index('idx_promocion_activa', 'activo', 'fecha_inicio', 'fecha_fin'),
    )


class PromocionAplicada(db.Model):
    __tablename__ = "promociones_aplicadas"
    id = db.Column(db.Integer, primary_key=True)
    promocion_id = db.Column(db.Integer, db.ForeignKey("promociones.id"), nullable=False)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False)

    # Detalles de aplicación
    descuento_aplicado = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_aplicacion = db.Column(db.DateTime, default=now_local)

    # Relaciones
    venta = db.relationship("Venta")

    # Índices
    __table_args__ = (
        db.Index('idx_promocion_venta', 'promocion_id', 'venta_id'),
    )


class Comision(db.Model):
    __tablename__ = "comisiones"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    periodo = db.Column(db.String(20), nullable=False)  # YYYY-MM o YYYY-MM-DD
    tipo_periodo = db.Column(db.String(10), nullable=False)  # mensual, semanal, diario

    # Cálculos
    ventas_total = db.Column(db.Numeric(12, 2), default=0)
    comision_total = db.Column(db.Numeric(12, 2), default=0)
    porcentaje_promedio = db.Column(db.Numeric(5, 2), default=0)

    # Estado
    pagada = db.Column(db.Boolean, default=False)
    fecha_pago = db.Column(db.DateTime, nullable=True)
    observaciones = db.Column(db.Text)

    # Relaciones
    usuario = db.relationship("User")

    # Índices
    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'periodo', name='unique_comision_usuario_periodo'),
        db.Index('idx_comision_periodo', 'periodo'),
        db.Index('idx_comision_pagada', 'pagada'),
    )


class ComisionDetalle(db.Model):
    __tablename__ = "comisiones_detalle"
    id = db.Column(db.Integer, primary_key=True)
    comision_id = db.Column(db.Integer, db.ForeignKey("comisiones.id"), nullable=False)

    # Referencia a la venta
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False)

    # Cálculo de comisión
    monto_venta = db.Column(db.Numeric(12, 2), nullable=False)
    porcentaje_comision = db.Column(db.Numeric(5, 2), nullable=False)
    monto_comision = db.Column(db.Numeric(12, 2), nullable=False)

    # Relaciones
    comision = db.relationship("Comision", backref="detalles")
    venta = db.relationship("Venta")

    # Índices
    __table_args__ = (
        db.Index('idx_detalle_comision', 'comision_id'),
        db.Index('idx_detalle_venta', 'venta_id'),
    )


class ComercialVendedor(db.Model):
    """Identidad comercial independiente del legajo de RRHH."""

    __tablename__ = "comercial_vendedores"

    id = db.Column(db.Integer, primary_key=True)
    nombre_visible = db.Column(db.String(200), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())

    aliases = db.relationship(
        "ComercialVendedorAlias",
        back_populates="vendedor",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "nombre_visible",
            name="uq_comercial_vendedores_nombre_visible",
        ),
    )


class ComercialVendedorAlias(db.Model):
    """Nombre de origen exacto más su clave para comparación normalizada."""

    __tablename__ = "comercial_vendedor_aliases"

    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(
        db.Integer,
        db.ForeignKey("comercial_vendedores.id", ondelete="CASCADE"),
        nullable=False,
    )
    nombre_origen = db.Column(db.String(200), nullable=False)
    nombre_normalizado = db.Column(db.String(200), nullable=False)

    vendedor = db.relationship("ComercialVendedor", back_populates="aliases")

    __table_args__ = (
        db.UniqueConstraint(
            "nombre_origen",
            name="uq_comercial_vendedor_aliases_nombre_origen",
        ),
        db.UniqueConstraint(
            "nombre_normalizado",
            name="uq_comercial_vendedor_aliases_nombre_normalizado",
        ),
    )


class ComercialObjetivo(db.Model):
    """Meta comercial mensual, independiente de los objetivos de RRHH."""

    __tablename__ = "comercial_objetivos"

    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(
        db.Integer,
        db.ForeignKey("comercial_vendedores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    empresa = db.Column(db.String(10), nullable=False)
    mes = db.Column(db.String(7), nullable=False)
    medida = db.Column(db.String(10), nullable=False)
    meta = db.Column(db.Numeric(18, 4), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=now_local)
    actualizado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=now_local,
        onupdate=now_local,
    )
    creado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actualizado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    vendedor = db.relationship("ComercialVendedor")

    __table_args__ = (
        db.UniqueConstraint(
            "vendedor_id",
            "empresa",
            "mes",
            "medida",
            name="uq_comercial_objetivo_vendedor_empresa_mes_medida",
        ),
        db.CheckConstraint(
            "empresa IN ('CARNES', 'LACTEOS')",
            name="ck_comercial_objetivo_empresa",
        ),
        db.CheckConstraint(
            "medida IN ('importe', 'cajas', 'kilos')",
            name="ck_comercial_objetivo_medida",
        ),
        db.CheckConstraint("meta > 0", name="ck_comercial_objetivo_meta_positiva"),
        db.CheckConstraint(
            "length(mes) = 7 AND substr(mes, 5, 1) = '-'",
            name="ck_comercial_objetivo_mes_formato",
        ),
        db.Index(
            "ix_comercial_objetivos_mes_empresa_medida",
            "mes",
            "empresa",
            "medida",
        ),
    )
