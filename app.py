from flask import Flask, session
from config import Config
from models import db
from werkzeug.middleware.proxy_fix import ProxyFix
from security import module_allowed

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    from api import api
    app.register_blueprint(api)

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

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    return app
