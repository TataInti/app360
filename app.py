from flask import Flask, session, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
from pythonjsonlogger import json as jsonlogger
import logging
from logging.handlers import RotatingFileHandler
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from config import Config
from models import db
from security import module_allowed
from exceptions import AppException

# Initialize extensions
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri="memory://",
)
csrf = CSRFProtect()
migrate = Migrate()


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
    app.logger.addHandler(app_handler)
    app.logger.setLevel(getattr(logging, app.config.get('LOG_LEVEL', 'INFO')))
    
    # Configure security logger
    security_logger = logging.getLogger('security')
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.INFO)
    
    # Also log to console in development
    if app.config.get('DEBUG'):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)
        security_logger.addHandler(console_handler)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Setup centralized logging
    setup_logging(app)
    app.logger.info("Application starting...")

    # Initialize Rate Limiter
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter.init_app(app)
        app.logger.info("Rate limiting enabled")
    
    # Initialize CSRF Protection
    if app.config.get('WTF_CSRF_ENABLED', True):
        csrf.init_app(app)
        app.logger.info("CSRF protection enabled")

    # Enable CORS for all routes
    CORS(app, origins=app.config["CORS_ORIGINS"])

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
    
    # Apply rate limiting to login endpoint
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter.limit("5 per minute")(api_rest)

    from blueprints.auth import auth_bp

    app.register_blueprint(auth_bp)
    # Apply rate limiting to login routes
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter.limit("10 per minute")(auth_bp)

    @app.context_processor
    def inject_user_context():
        return {
            "current_user": session.get("user"),
            "current_role": session.get("role"),
            "can_access": module_allowed,
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
        app.logger.error(f"Internal error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    debug_mode = os.getenv("DEBUG", "False").lower() == "true"
    # En producción, usar gunicorn en lugar de app.run()
    # Nunca usar debug=True o host='0.0.0.0' en producción
    app.run(debug=debug_mode, host='127.0.0.1', port=5001)
