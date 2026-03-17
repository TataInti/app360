from flask import Flask, session, jsonify, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from pythonjsonlogger import json as jsonlogger
import logging
from logging.handlers import RotatingFileHandler
import os
from dotenv import load_dotenv

# Load environment variables from .env file
# En desarrollo local es común tener variables exportadas en la shell; forzamos override
# para que la app quede alineada a la configuración del proyecto.
load_dotenv(override=True)

from config import Config
from models import db
from security import module_allowed
from exceptions import AppException
from extensions import limiter, csrf, migrate


def setup_logging(app):
    """Configure centralized logging with JSON format"""
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Configure JSON formatter
    class CustomJsonFormatter(jsonlogger.JsonFormatter):
        def add_fields(self, log_record, record, message_dict):
            super().add_fields(log_record, record, message_dict)
            log_record['timestamp'] = record.created
            log_record['level'] = record.levelname
            log_record['logger'] = record.name
    
    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    
    # App log handler
    app_handler = RotatingFileHandler(
        app.config.get('LOG_FILE', 'logs/app.log'),
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    app_handler.setFormatter(formatter)
    app_handler.setLevel(getattr(logging, app.config.get('LOG_LEVEL', 'INFO')))
    
    # Security log handler
    security_handler = RotatingFileHandler(
        app.config.get('SECURITY_LOG_FILE', 'logs/security.log'),
        maxBytes=10485760,
        backupCount=10
    )
    security_handler.setFormatter(formatter)
    security_handler.setLevel(logging.INFO)
    
    # Configure app logger
    if not any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == os.path.abspath(app_handler.baseFilename)
        for handler in app.logger.handlers
    ):
        app.logger.addHandler(app_handler)
    app.logger.setLevel(getattr(logging, app.config.get('LOG_LEVEL', 'INFO')))
    
    # Configure security logger
    security_logger = logging.getLogger('security')
    if not any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == os.path.abspath(security_handler.baseFilename)
        for handler in security_logger.handlers
    ):
        security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.INFO)
    
    # Also log to console in development
    if app.config.get('DEBUG'):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        if console_handler not in app.logger.handlers:
            app.logger.addHandler(console_handler)
        if console_handler not in security_logger.handlers:
            security_logger.addHandler(console_handler)


def validate_config(app):
    required = ["SECRET_KEY", "ADMIN_PASSWORD"]
    missing = [key for key in required if not app.config.get(key)]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Missing required config: {missing_list}")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ajustar engine options según el backend real para evitar incompatibilidades
    # cuando el entorno de tests fuerza SQLite por variable DATABASE_URL.
    db_uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    engine_opts = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
    if db_uri.startswith("sqlite"):
        for key in ("pool_size", "max_overflow", "pool_timeout", "pool_recycle"):
            engine_opts.pop(key, None)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_opts

    # Setup centralized logging
    setup_logging(app)
    app.logger.info("Application starting...")

    # Validate required config after logging is available
    validate_config(app)

    # Initialize Rate Limiter
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter.init_app(app)
        app.logger.info("Rate limiting enabled")
    
    # Initialize CSRF Protection
    if app.config.get('WTF_CSRF_ENABLED', True):
        csrf.init_app(app)
        app.logger.info("CSRF protection enabled")

    # Enable CORS for all routes
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    db.init_app(app)
    migrate.init_app(app, db)

    # Security headers middleware
    @app.after_request
    def add_security_headers(response):
        # Prevenir clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # Prevenir MIME sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Habilitar XSS filter del navegador
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # Referrer policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Content Security Policy básica
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net"
        # Strict Transport Security (solo en HTTPS)
        if app.config.get('PREFERRED_URL_SCHEME') == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    from api import api

    app.register_blueprint(api)
    # Exempt API blueprint from CSRF (uses JWT instead)
    if app.config.get('WTF_CSRF_ENABLED', True):
        csrf.exempt(api)

    from api_rest import api_rest

    app.register_blueprint(api_rest)
    # Exempt REST API from CSRF (uses JWT instead)
    if app.config.get('WTF_CSRF_ENABLED', True):
        csrf.exempt(api_rest)
    
    from blueprints.auth import auth_bp

    app.register_blueprint(auth_bp)
    # Apply rate limiting to login routes
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter.limit("10 per minute")(auth_bp)

    @app.context_processor
    def inject_user_context():
        def can_access(module):
            return module_allowed(module, session.get("role"), session.get("user_id"))
        return {
            "current_user": session.get("user"),
            "current_role": session.get("role"),
            "can_access": can_access,
        }

    from blueprints.products import products_bp

    app.register_blueprint(products_bp)

    from blueprints.locations import locations_bp

    app.register_blueprint(locations_bp)

    from blueprints.stock import stock_bp

    app.register_blueprint(stock_bp)

    from blueprints.dashboard import dashboard_bp

    app.register_blueprint(dashboard_bp)

    from blueprints.crm import crm_bp

    app.register_blueprint(crm_bp)

    from blueprints.dashboard_comercial import dashboard_com_bp

    app.register_blueprint(dashboard_com_bp)

    from blueprints.panel_ejecutivo import panel_bp

    app.register_blueprint(panel_bp)

    from blueprints.compras import compras_bp

    app.register_blueprint(compras_bp)

    from blueprints.rrhh import rrhh_bp

    app.register_blueprint(rrhh_bp)

    from blueprints.ventas import ventas_bp

    app.register_blueprint(ventas_bp)

    from blueprints.tesoreria import tesoreria_bp

    app.register_blueprint(tesoreria_bp)

    from blueprints.cta_cte_friar import cta_cte_friar_bp

    app.register_blueprint(cta_cte_friar_bp)

    from blueprints.comercial import comercial_bp

    app.register_blueprint(comercial_bp)

    from blueprints.gastos import gastos_bp

    app.register_blueprint(gastos_bp)

    from blueprints.bi import bi_bp

    app.register_blueprint(bi_bp)

    from blueprints.sabiogo import sabiogo_bp

    app.register_blueprint(sabiogo_bp)

    from blueprints.admin import admin_bp

    app.register_blueprint(admin_bp)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Register error handlers
    @app.errorhandler(AppException)
    def handle_app_exception(e):
        return jsonify({"error": str(e)}), e.status_code

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def handle_internal_error(e):
        # Mantener rollback, pero también registrar traceback completo
        app.logger.exception("Internal error")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    debug_mode = os.getenv("DEBUG", "False").lower() == "true"
    # En producción, usar gunicorn en lugar de app.run()
    # Nunca usar debug=True o host='0.0.0.0' en producción
    app.run(debug=debug_mode, host='127.0.0.1', port=5001)
