from .. import db


class UserModulePermission(db.Model):
    __tablename__ = "user_module_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    module = db.Column(db.String(50), nullable=False)
    access_level = db.Column(db.String(10), nullable=False)  # 'view' or 'edit'

    __table_args__ = (
        db.UniqueConstraint("user_id", "module", name="uq_user_module_perm"),
    )
