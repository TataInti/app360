from .. import db


class Attendance(db.Model):
    __tablename__ = "rrhh_attendance"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    notes = db.Column(db.String(255), nullable=True)

    employee = db.relationship("Employee", back_populates="attendances")