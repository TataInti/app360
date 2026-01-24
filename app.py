from flask import Flask, session, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from config import Config
from models import db
from security import module_allowed
from exceptions import AppException

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Configure logging
    logging.basicConfig(level=logging.INFO)
    app.logger.setLevel(logging.INFO)

    # Enable CORS for all routes
    CORS(app, origins=app.config["CORS_ORIGINS"])

    db.init_app(app)

    from api import api

    app.register_blueprint(api)

    from api_rest import api_rest

    app.register_blueprint(api_rest)

    from blueprints.auth import auth_bp

    app.register_blueprint(auth_bp)

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

    from blueprints.comercial import comercial_bp

    app.register_blueprint(comercial_bp)

    from blueprints.gastos import gastos_bp

    app.register_blueprint(gastos_bp)

    from blueprints.bi import bi_bp

    app.register_blueprint(bi_bp)

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
    app.run(debug=debug_mode, host='127.0.0.1', port=5001)
