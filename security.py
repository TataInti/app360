from functools import wraps
from datetime import datetime, timedelta, timezone
import hmac
import logging
import jwt

from flask import (
    flash,
    redirect,
    session,
    url_for,
    request,
    jsonify,
    current_app,
    has_request_context,
)

# Security Logger
security_logger = logging.getLogger('security')


def secrets_match(received, configured):
    if not received or not configured:
        return False
    return hmac.compare_digest(str(received), str(configured))

ACCESS_MAP = {
    "admin": ["all"],  # Administrador con acceso total
    "manager": ["all"],
    "gerente": ["all"],  # Alias para manager
    "sales": ["crm", "ventas", "dashboard_comercial", "comercial", "objetivos"],
    "purchases": ["compras", "dashboard", "gastos"],
    "hr": ["rrhh", "adelantos", "ausentismo", "dotacion", "empleados"],
    "operations": ["compras", "stock", "locations", "products", "dashboard"],
    "finance": ["tesoreria", "arqueos", "movimientos", "gastos", "bi", "panel"],
    "caja": ["tesoreria", "arqueos", "movimientos", "gastos"],
    "director": ["tesoreria", "arqueos", "movimientos", "gastos", "bi", "panel",
                 "dashboard", "rrhh", "adelantos", "compras"],
    "direccion": ["dashboard", "dashboard_comercial", "panel", "bi"],
}

MANAGED_MODULES = {
    "dashboard": "Panel Tesorería",
    "dashboard_comercial": "Panel Ventas",
    "panel": "Panel Ejecutivo",
    "bi": "Panel Rentabilidad",
    "products": "Productos",
    "locations": "Ubicaciones",
    "stock": "Stock",
    "crm": "CRM / Ventas",
    "compras": "Compras",
    "rrhh": "RRHH",
    "tesoreria": "Tesorería",
    "gastos": "Gastos",
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
    "objetivos": "/comercial/objetivos",
    "stock": "/stock",
    "locations": "/locations",
    "products": "/products",
    "comercial": "/comercial",
    "gastos": "/gastos",
    "tesoreria": "/tesoreria",
    "arqueos": "/tesoreria/arqueos",
    "movimientos": "/tesoreria/movimientos",
    "bi": "/bi",
    "admin": "/admin",
}

# Pantalla de destino para un usuario que no tiene ningún módulo permitido.
SIN_ACCESO_ROUTE = "/sin-acceso"


# =============================================================================
# Security Event Logging
# =============================================================================
def log_security_event(event_type, message, user=None, ip=None, extra=None):
    """Log security-related events"""
    request_ip = request.remote_addr if has_request_context() else None
    user_agent = request.headers.get('User-Agent', 'unknown') if has_request_context() else 'unknown'

    log_data = {
        'event_type': event_type,
        'message': message,
        'user': user or session.get('user', 'anonymous'),
        'ip': ip or request_ip or 'unknown',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'user_agent': user_agent,
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


def jwt_o_sesion(modulo):
    """Acepta un JWT de acceso válido o una sesión web con el módulo indicado.

    Para los GET de api_rest que también consumen pantallas: el navegador los
    llama con la cookie de sesión y sin token. Si llega un Bearer, debe ser
    válido (no cae a la sesión). Sin credencial responde 401; con sesión sin
    el módulo, 403.
    """
    def decorator(f):
        con_jwt = jwt_required(f)

        @wraps(f)
        def decorated(*args, **kwargs):
            tiene_bearer = request.headers.get('Authorization', '').startswith('Bearer ')
            if tiene_bearer or not session.get('user'):
                return con_jwt(*args, **kwargs)
            if not module_allowed(modulo):
                log_access_denied(session.get('user'), modulo)
                return jsonify({'error': 'Sin acceso al módulo'}), 403
            request.current_user = {
                'user_id': session.get('user_id'),
                'username': session.get('user'),
                'role': session.get('role'),
            }
            return f(*args, **kwargs)
        return decorated
    return decorator


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
def get_user_module_access(module, user_id, role):
    """Return 'edit', 'view', or 'none' for a user+module combo."""
    allowed = ACCESS_MAP.get(role, [])
    if "all" in allowed:
        return "edit"
    if module in allowed:
        return "edit"
    # Check individual permission
    from models.core.user_permission import UserModulePermission
    perm = UserModulePermission.query.filter_by(
        user_id=user_id, module=module
    ).first()
    if perm:
        return perm.access_level
    return "none"


def module_allowed(module, role=None, user_id=None):
    if not module:
        return True
    if role is None:
        role = session.get("role")
    if user_id is None:
        user_id = session.get("user_id")
    if not role:
        return False
    allowed = ACCESS_MAP.get(role, [])
    if "all" in allowed:
        return True
    if module in allowed:
        return True
    # Check individual permission if user_id available
    if user_id:
        return get_user_module_access(module, user_id, role) != "none"
    return False


def protect_blueprint(bp, module):
    @bp.before_request
    def guard():
        from flask import current_app

        # Sincronización servidor-a-servidor: API key en header como alternativa a sesión
        _sync_key = current_app.config.get('SABIOGO_SYNC_API_KEY')
        sync_endpoints = {
            'sabiogo.sabiogo_db_sync',
            'sabiogo.sabiogo_db_sync_daily',
            'sabiogo.sabiogo_db_sync_finalize',
            'sabiogo.sabiogo_db_sync_status',
        }
        if request.endpoint in sync_endpoints:
            if not _sync_key:
                return jsonify({'error': 'SABIOGO_SYNC_API_KEY no configurado'}), 503
            if secrets_match(request.headers.get('X-Sync-Key'), _sync_key):
                return
            return jsonify({'error': 'Unauthorized'}), 401

        if module_allowed(module):
            # Enforce read-only for 'view' level on mutating methods
            user_id = session.get("user_id")
            role = session.get("role")
            if user_id and role and request.method in ("POST", "PUT", "DELETE", "PATCH"):
                access = get_user_module_access(module, user_id, role)
                if access == "view":
                    log_access_denied(session.get("user"), module)
                    flash("Tu acceso a esta sección es solo lectura.", "warning")
                    return redirect(request.referrer or url_for("auth.login")), 403
            return  # access granted
        if session.get("user"):
            # Usuario logueado pero sin acceso, redirigir a ruta permitida
            log_access_denied(session.get("user"), module)
            route = first_allowed_route(session.get("role"))
            if route == request.path:
                # La pantalla de destino también niega el acceso: no redirigir a sí misma
                route = SIN_ACCESO_ROUTE
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
    """Primera pantalla a la que puede entrar un usuario con este rol.

    Nunca devuelve "/": es la pantalla de login, y el login redirigía a sí
    misma para roles sin módulos. Sin pantalla posible, devuelve SIN_ACCESO_ROUTE.
    """
    allowed = ACCESS_MAP.get(role, [])
    if "all" in allowed:
        return MODULE_ROUTES.get("dashboard", "/dashboard")
    for module in allowed:
        if module in MODULE_ROUTES:
            return MODULE_ROUTES[module]
    # Sin módulos por rol: primer permiso individual sobre un módulo administrable
    for module in MANAGED_MODULES:
        if module in MODULE_ROUTES and module_allowed(module, role):
            return MODULE_ROUTES[module]
    return SIN_ACCESO_ROUTE

