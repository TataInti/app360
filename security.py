from functools import wraps
from datetime import datetime, timedelta, timezone
import logging
import jwt

from flask import flash, redirect, session, url_for, request, jsonify, current_app

# Security Logger
security_logger = logging.getLogger('security')

ACCESS_MAP = {
    "admin": ["all"],  # Administrador con acceso total
    "manager": ["all"],
    "gerente": ["all"],  # Alias para manager
    "sales": ["crm", "ventas", "dashboard_comercial", "comercial", "objetivos"],
    "purchases": ["compras", "dashboard", "gastos"],
    "hr": ["rrhh", "adelantos", "ausentismo", "dotacion", "empleados"],
    "operations": ["compras", "stock", "locations", "products", "dashboard"],
    "finance": ["tesoreria", "arqueos", "movimientos", "gastos", "bi", "panel"],
}

MODULE_ROUTES = {
    "dashboard": "/dashboard",
    "dashboard_comercial": "/dashboard-comercial",
    "panel": "/panel-ejecutivo",
    "crm": "/leads",
    "ventas": "/ventas",
    "compras": "/compras",
    "rrhh": "/rrhh",
    "empleados": "/rrhh/empleados",
    "dotacion": "/rrhh/dotacion",
    "adelantos": "/rrhh/adelantos",
    "ausentismo": "/rrhh/ausentismo",
    "objetivos": "/rrhh/objetivos",
    "stock": "/stock",
    "locations": "/locations",
    "products": "/products",
    "comercial": "/comercial",
    "gastos": "/gastos",
    "tesoreria": "/tesoreria",
    "arqueos": "/tesoreria/arqueos",
    "movimientos": "/tesoreria/movimientos",
    "bi": "/bi",
}


# =============================================================================
# Security Event Logging
# =============================================================================
def log_security_event(event_type, message, user=None, ip=None, extra=None):
    """Log security-related events"""
    log_data = {
        'event_type': event_type,
        'message': message,
        'user': user or session.get('user', 'anonymous'),
        'ip': ip or request.remote_addr if request else 'unknown',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'user_agent': request.headers.get('User-Agent', 'unknown') if request else 'unknown',
    }
    if extra:
        log_data.update(extra)
    
    security_logger.info(log_data)


def log_login_attempt(username, success, ip=None):
    """Log login attempts"""
    event_type = 'LOGIN_SUCCESS' if success else 'LOGIN_FAILED'
    log_security_event(
        event_type=event_type,
        message=f"Login attempt for user '{username}'",
        user=username,
        ip=ip,
        extra={'success': success}
    )


def log_access_denied(user, module, ip=None):
    """Log access denied events"""
    log_security_event(
        event_type='ACCESS_DENIED',
        message=f"Access denied to module '{module}'",
        user=user,
        ip=ip,
        extra={'module': module}
    )


# =============================================================================
# JWT Token Management
# =============================================================================
def generate_access_token(user_id, username, role):
    """Generate a JWT access token"""
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'type': 'access',
        'exp': datetime.now(timezone.utc) + timedelta(seconds=current_app.config['JWT_ACCESS_TOKEN_EXPIRES']),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def generate_refresh_token(user_id, username):
    """Generate a JWT refresh token"""
    payload = {
        'user_id': user_id,
        'username': username,
        'type': 'refresh',
        'exp': datetime.now(timezone.utc) + timedelta(seconds=current_app.config['JWT_REFRESH_TOKEN_EXPIRES']),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def decode_token(token):
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def jwt_required(f):
    """Decorator to require a valid JWT token for API endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            log_security_event('JWT_MISSING', 'JWT token missing in request')
            return jsonify({'error': 'Token is missing'}), 401
        
        payload = decode_token(token)
        if not payload:
            log_security_event('JWT_INVALID', 'Invalid or expired JWT token')
            return jsonify({'error': 'Token is invalid or expired'}), 401
        
        if payload.get('type') != 'access':
            return jsonify({'error': 'Invalid token type'}), 401
        
        # Add user info to request context
        request.current_user = {
            'user_id': payload.get('user_id'),
            'username': payload.get('username'),
            'role': payload.get('role'),
        }
        
        return f(*args, **kwargs)
    return decorated


def jwt_optional(f):
    """Decorator that allows both authenticated and unauthenticated access"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if token:
            payload = decode_token(token)
            if payload and payload.get('type') == 'access':
                request.current_user = {
                    'user_id': payload.get('user_id'),
                    'username': payload.get('username'),
                    'role': payload.get('role'),
                }
            else:
                request.current_user = None
        else:
            request.current_user = None
        
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# Module Access Control
# =============================================================================
def module_allowed(module, role=None):
    if not module:
        return True
    if role is None:
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
        # Skip protection in testing mode
        from flask import current_app
        if current_app.config.get('TESTING'):
            return
            
        if module_allowed(module):
            return  # access granted
        if session.get("user"):
            # Usuario logueado pero sin acceso, redirigir a ruta permitida
            log_access_denied(session.get("user"), module)
            route = first_allowed_route(session.get("role"))
            flash("No tienes acceso a esta sección.", "warning")
            return redirect(route)
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("auth.login"))


def require_module(module):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if module_allowed(module):
                return f(*args, **kwargs)
            log_access_denied(session.get("user", "anonymous"), module)
            flash("You do not have access to this view.", "warning")
            return redirect(url_for("auth.login"))

        return wrapper

    return decorator


def first_allowed_route(role):
    allowed = ACCESS_MAP.get(role, [])
    if not allowed:
        # Si no hay módulos permitidos, devolver dashboard si tiene acceso, sino nada
        if module_allowed("dashboard", role):
            return MODULE_ROUTES.get("dashboard", "/dashboard")
        return "/"  # O alguna página de error
    if "all" in allowed:
        return MODULE_ROUTES.get("dashboard", "/dashboard")
    for module in allowed:
        if module in MODULE_ROUTES:
            return MODULE_ROUTES[module]
    return "/dashboard"
