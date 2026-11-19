from sqlalchemy import false
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    # Sin default: el rol es una decisión explícita. El antiguo default \"manager\"
    # (administración total) hacía que un alta sin rol recibiera acceso completo.
    role = db.Column(db.String(40), nullable=False)
    active = db.Column(db.Boolean, default=True)
    # Clave temporal obligatoria y datos de acceso (C1 de usuarios, migración
    # 20261119_usuarios_c1_clave). Con default seguro: no cambian el estado de los usuarios
    # existentes.
    must_change_password = db.Column(
        db.Boolean, nullable=False, default=False, server_default=false()
    )
    password_changed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    # Administración de usuarios (C2, migración 20261119_usuarios_c2_admin): versión de token para
    # los JWT, vencimiento de la clave temporal (D1) y fecha de desactivación.
    token_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    temp_password_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    deactivated_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs):
        if not kwargs.get("role"):
            raise ValueError("El usuario requiere un rol explícito (role); no hay rol por defecto.")
        super().__init__(**kwargs)

    @validates("role")
    def _validar_rol(self, key, valor):
        if not valor:
            raise ValueError("El rol del usuario no puede estar vacío.")
        return valor

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
