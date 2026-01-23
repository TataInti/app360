from functools import wraps

from flask import flash, redirect, session, url_for

ACCESS_MAP = {
    "manager": ["all"],
    "sales": ["crm", "ventas", "dashboard_comercial"],
    "purchases": ["compras", "dashboard"],
    "hr": ["rrhh", "asistencia", "objetivos", "clima"],
    "operations": ["compras", "stock", "locations", "products", "dashboard"],
}

MODULE_ROUTES = {
    "dashboard": "/dashboard",
    "dashboard_comercial": "/dashboard-comercial",
    "panel": "/panel-ejecutivo",
    "crm": "/leads",
    "ventas": "/ventas",
    "compras": "/compras",
    "rrhh": "/rrhh",
    "asistencia": "/rrhh/asistencia",
    "objetivos": "/rrhh/objetivos",
    "clima": "/rrhh/clima",
    "stock": "/stock",
    "locations": "/locations",
    "products": "/products",
}


def module_allowed(module):
    if not module:
        return True
    role = session.get("role")
    if not role:
        return False
    allowed = ACCESS_MAP.get(role, [])
    if "all" in allowed:
        return True
    return module in allowed


def protect_blueprint(bp, module):
    @bp.before_request
    def guard():
        if module_allowed(module):
            return  # access granted
        flash("You do not have access to this module.", "warning")
        return redirect(url_for("auth.login"))


def require_module(module):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if module_allowed(module):
                return f(*args, **kwargs)
            flash("You do not have access to this view.", "warning")
            return redirect(url_for("auth.login"))

        return wrapper

    return decorator


def first_allowed_route(role):
    allowed = ACCESS_MAP.get(role, [])
    if not allowed:
        return "/dashboard"
    if "all" in allowed:
        return MODULE_ROUTES.get("dashboard", "/dashboard")
    for module in allowed:
        if module in MODULE_ROUTES:
            return MODULE_ROUTES[module]
    return "/dashboard"
