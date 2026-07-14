import os


class Config:
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    _IS_LOCAL = FLASK_ENV.lower() in {"development", "dev", "local"} or DEBUG
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        "postgresql://app360:password@localhost:5432/app360" if _IS_LOCAL else None
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pool_pre_ping evita conexiones SSL/TCP stale tras idle prolongado
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    if SQLALCHEMY_DATABASE_URI and not SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS.update(
            {
                "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 1800)),
                "pool_size": int(os.getenv("DB_POOL_SIZE", 20)),
                "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 40)),
                "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 30)),
            }
        )

    # En local no forzar SERVER_NAME/HTTPS (rompe cookies y routing con host distinto)
    SERVER_NAME = os.getenv("SERVER_NAME") or (
        None if _IS_LOCAL else "vyp.app360.com.ar"
    )
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME") or (
        "http" if _IS_LOCAL else "https"
    )

    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE")
    if SESSION_COOKIE_SECURE is None:
        SESSION_COOKIE_SECURE = not _IS_LOCAL
    else:
        SESSION_COOKIE_SECURE = SESSION_COOKIE_SECURE.lower() == "true"

    REMEMBER_COOKIE_SECURE = os.getenv("REMEMBER_COOKIE_SECURE")
    if REMEMBER_COOKIE_SECURE is None:
        REMEMBER_COOKIE_SECURE = not _IS_LOCAL
    else:
        REMEMBER_COOKIE_SECURE = REMEMBER_COOKIE_SECURE.lower() == "true"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    JSONIFY_PRETTYPRINT_REGULAR = False
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    LOGIN_TITLE = os.getenv("LOGIN_TITLE", "Welcome to APP360")

    # Upload limits (50 MB max)
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 50 * 1024 * 1024))

    # Rate Limiting
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "True").lower() == "true"
    RATELIMIT_STORAGE_URL = os.getenv("REDIS_URL", "memory://")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", RATELIMIT_STORAGE_URL)
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200 per minute")
    RATELIMIT_HEADERS_ENABLED = True
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 900))  # 15 min
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 604800))  # 7 days
    
    # CSRF Protection
    WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "True").lower() == "true"
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # 'json' or 'text'
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
    SECURITY_LOG_FILE = os.getenv("SECURITY_LOG_FILE", "logs/security.log")

    # SabioGo sync: API key para el script de sincronización en Windows Server
    SABIOGO_SYNC_API_KEY = os.getenv("SABIOGO_SYNC_API_KEY")
    SABIOGO_CRON_TOKEN = os.getenv("SABIOGO_CRON_TOKEN")
