"""Modelos para importación por batch de archivos SabioGo (sin API)."""

from .. import db
from ..time_utils import now_local


class LogSabiogoBatch(db.Model):
    """Registro de auditoría para importación batch (manifiesto + estado)."""

    __tablename__ = "logs_sabiogo_batch"

    id = db.Column(db.Integer, primary_key=True)

    batch_id = db.Column(db.String(120), nullable=False, unique=True, index=True)
    fecha_datos = db.Column(db.Date, nullable=True, index=True)

    status = db.Column(db.String(20), nullable=False, default="pending", index=True)

    manifest_path = db.Column(db.String(512), nullable=True)
    manifest_sha256 = db.Column(db.String(64), nullable=True)

    stats_json = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=now_local, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_local, onupdate=now_local, nullable=False)

    def __repr__(self):
        return f"<LogSabiogoBatch batch_id={self.batch_id} status={self.status}>"
