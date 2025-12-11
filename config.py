import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///silva360.db"  # temporal; luego lo cambiamos a PostgreSQL
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERVER_NAME = os.getenv("SERVER_NAME", "silva360.actioconsultores.com")
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    JSONIFY_PRETTYPRINT_REGULAR = False
