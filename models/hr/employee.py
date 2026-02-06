from .. import db


class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(140), nullable=True, index=True)
    phone = db.Column(db.String(20), nullable=True)
    position = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(120), nullable=True, index=True)
    hire_date = db.Column(db.Date, nullable=True)
    salary = db.Column(db.Numeric(10, 2), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)

    # Property for backward compatibility
    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"
    
    # Alias full_name = name para compatibilidad con templates y queries
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    location = db.relationship("Location")
    attendances = db.relationship("Attendance", back_populates="employee")
    goals = db.relationship("Goal", back_populates="employee")
    survey_responses = db.relationship("SurveyResponse", back_populates="employee")