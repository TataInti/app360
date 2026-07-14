"""Estado de las ejecuciones automáticas de sincronización SabioGo."""

from sqlalchemy import Index

from .. import db
from ..time_utils import now_local


class SabiogoSyncRun(db.Model):
    __tablename__ = 'sabiogo_sync_runs'

    id = db.Column(db.Integer, primary_key=True)
    execution_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    fecha_objetivo = db.Column(db.Date, nullable=False, index=True)
    estado = db.Column(db.String(20), nullable=False, index=True)
    mensaje = db.Column(db.String(500), nullable=True)
    filas_ventas = db.Column(db.Integer, nullable=True)
    filas_compras = db.Column(db.Integer, nullable=True)
    iniciada_en = db.Column(db.DateTime(timezone=True), nullable=False, default=now_local)
    finalizada_en = db.Column(db.DateTime(timezone=True), nullable=True)
    actualizada_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=now_local,
        onupdate=now_local,
    )

    __table_args__ = (
        Index('idx_sabiogo_sync_run_fecha_estado', 'fecha_objetivo', 'estado'),
    )

    def __repr__(self):
        return (
            f'<SabiogoSyncRun execution_id={self.execution_id} '
            f'fecha={self.fecha_objetivo} estado={self.estado}>'
        )