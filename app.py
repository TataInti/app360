from flask import Flask, session, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
from pythonjsonlogger import json as jsonlogger
import logging
from logging.handlers import RotatingFileHandler
import os
from dotenv import load_dotenv

# Load environment variables from .env file without overriding the process
# environment. In production, the process manager or shell must remain the
# source of truth.
load_dotenv()

from config import Config
from models import db
from security import guardia_api_admin_sin_sesion, module_allowed, revalidar_sesion_web
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
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        required.append("DATABASE_URL")
    missing = [key for key in required if not app.config.get(key)]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Missing required config: {missing_list}")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Cache-busting de estáticos: la versión se calcula una vez al arrancar a
    # partir del mtime de los archivos propios. Evita que el navegador siga
    # sirviendo CSS/JS viejos después de un deploy o de un cambio local.
    def _compute_asset_version():
        import hashlib
        import pathlib
        static_dir = pathlib.Path(app.static_folder)
        digest = hashlib.sha1()
        for pattern in ("css/*.css", "js/*.js"):
            for path in sorted(static_dir.glob(pattern)):
                try:
                    digest.update(path.name.encode())
                    digest.update(str(int(path.stat().st_mtime)).encode())
                except OSError:
                    continue
        return digest.hexdigest()[:10]

    _asset_version = _compute_asset_version()

    @app.template_global()
    def asset(filename):
        """URL de un estático con query de versión para invalidar caché."""
        from flask import url_for
        return f"{url_for('static', filename=filename)}?v={_asset_version}"

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
    
    # Guardia de sesión de /api/admin/* antes del CSRF (C3, R4b): sin sesión, 401 JSON uniforme.
    app.before_request(guardia_api_admin_sin_sesion)

    # Initialize CSRF Protection
    if app.config.get('WTF_CSRF_ENABLED', True):
        csrf.init_app(app)
        app.logger.info("CSRF protection enabled")

    # Revalidación de la sesión web en cada request (R-04). Se registra antes de los
    # blueprints: sus guardias de módulo leen el rol ya alineado con la base.
    app.before_request(revalidar_sesion_web)

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
        username = session.get("user")
        role = session.get("role")

        def can_access(module):
            return module_allowed(module, role, session.get("user_id"))

        sabiogo_sync_alert = None
        if role == "gerente" or username == "gerente":
            try:
                from services.sabiogo_sync_monitor import get_sabiogo_sync_alert
                sabiogo_sync_alert = get_sabiogo_sync_alert()
            except Exception:
                db.session.rollback()
                app.logger.error(
                    "No se pudo calcular la alerta de sincronización SabioGo",
                    exc_info=True,
                )

        return {
            "current_user": username,
            "current_role": role,
            "can_access": can_access,
            "sabiogo_sync_alert": sabiogo_sync_alert,
            "asset_version": _asset_version,
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

    from blueprints.admin_usuarios import admin_usuarios_bp

    app.register_blueprint(admin_usuarios_bp)

    # login.html no extiende base.html; responder sin contenido evita su favicon.ico implícito.
    @app.route("/favicon.ico", methods=["GET"])
    def favicon_vacio():
        return "", 204

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
