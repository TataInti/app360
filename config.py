import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///silva360.db"  # temporal; luego lo cambiamos a PostgreSQL
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
