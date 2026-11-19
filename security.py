from functools import wraps
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import jwt

from flask import (
    flash,
    g,
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
# Sesión web: revalidación en cada request (R-04)
# =============================================================================
# Clave de sesión con la huella HMAC del password_hash vigente al iniciar sesión.
SESION_HUELLA_CLAVE = "sesion_huella"

# Endpoints que no exigen sesión y no pasan por la revalidación. Coinciden con las
# excepciones de tests/test_acceso_anonimo.py. auth.login valida una sesión previa
# dentro de su vista, para que una sesión vencida no impida iniciar sesión.
ENDPOINTS_SIN_REVALIDACION = frozenset({
    "auth.login",
    "static",
    "api_rest.health_check",
    "api_rest.login",
    "api_rest.refresh_token",
    "sabiogo.sabiogo_db_sync",
    "sabiogo.sabiogo_db_sync_daily",
    "sabiogo.sabiogo_db_sync_finalize",
    "sabiogo.sabiogo_db_sync_status",
})


def huella_sesion(usuario):
    """HMAC-SHA256 del password_hash vigente, con SECRET_KEY como clave.

    Cambiar la clave de un usuario, o la SECRET_KEY, cambia la huella y cierra las
    sesiones previas. El hash nunca entra en la sesión. Sin hash no hay huella: esa
    cuenta no puede tener sesión.
    """
    if not usuario.password_hash:
        return None
    clave = current_app.secret_key
    if isinstance(clave, str):
        clave = clave.encode("utf-8")
    return hmac.new(clave, usuario.password_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def datos_de_sesion_web(usuario):
    """Claves que identifican la sesión web de un usuario. El login usa solo esta función."""
    return {
        "user": usuario.username,
        "user_id": usuario.id,
        "role": usuario.role,
        SESION_HUELLA_CLAVE: huella_sesion(usuario),
    }


def _usuario_por_pk(user_id):
    """Usuario por clave primaria, o None. Una consulta por llamada.

    populate_existing fuerza la lectura de la base: una desactivación hecha fuera de
    la sesión ORM no queda oculta por el identity map.
    """
    from models import db
    from models.core.user import User

    if user_id is None:
        return None
    try:
        clave = int(user_id)
    except (TypeError, ValueError):
        return None
    return db.session.get(User, clave, populate_existing=True)


def usuario_vigente(user_id):
    """Usuario activo por clave primaria, o None (inexistente o inactivo). Una consulta."""
    usuario = _usuario_por_pk(user_id)
    if usuario is None or usuario.active is not True:
        return None
    return usuario


def hay_sesion_web():
    """True si la sesión trae alguna clave de identidad, aunque esté incompleta."""
    return any(clave in session for clave in ("user", "user_id", "role", SESION_HUELLA_CLAVE))


def _usuario_de_sesion_o_motivo():
    """(usuario, None) si la sesión es válida; (None, motivo) si no lo es."""
    huella_guardada = session.get(SESION_HUELLA_CLAVE)
    if not huella_guardada:
        return None, "sin_huella"
    usuario = _usuario_por_pk(session.get("user_id"))
    if usuario is None:
        return None, "usuario_inexistente"
    if usuario.active is not True:
        return None, "usuario_inactivo"
    huella_actual = huella_sesion(usuario)
    if not huella_actual or not hmac.compare_digest(huella_actual, str(huella_guardada)):
        return None, "huella_no_coincide"
    return usuario, None


def sesion_web_vigente():
    """Valida la sesión web contra la base: una consulta por PK por request (cacheada en g).

    Si no es válida, limpia la sesión completa y devuelve False. Si es válida, alinea
    session["user"] y session["role"] con la base: un cambio de rol surte efecto en
    este mismo request, antes de que las guardias de módulo lean el rol.
    """
    if "usuario_sesion" in g:
        return g.usuario_sesion is not None
    usuario, motivo = _usuario_de_sesion_o_motivo()
    g.usuario_sesion = usuario
    if usuario is None:
        log_security_event(
            "SESSION_REVOKED",
            f"Sesión web invalidada: {motivo}",
            user=session.get("user"),
            extra={"motivo": motivo},
        )
        session.clear()
        return False
    if session.get("user") != usuario.username:
        session["user"] = usuario.username
    if session.get("role") != usuario.role:
        session["role"] = usuario.role
    return True


def revalidar_sesion_web():
    """before_request de la aplicación: corta una sesión revocada antes de las guardias de blueprint.

    Sin claves de sesión no hay consulta. Las rutas de ENDPOINTS_SIN_REVALIDACION
    no pasan por aquí. Una sesión no válida responde 401 JSON en /api/ y redirige al
    login en el resto.
    """
    g.pop("usuario_sesion", None)
    if request.endpoint in ENDPOINTS_SIN_REVALIDACION or not hay_sesion_web():
        return None
    if sesion_web_vigente():
        return None
    if "/api/" in request.path:
        return jsonify({"error": "Sesión requerida"}), 401
    flash("Tu sesión ya no es válida. Inicia sesión nuevamente.", "warning")
    return redirect(url_for("auth.login"))


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

        # Revocación inmediata (R-04): el usuario del token debe existir y estar activo.
        # jwt_o_sesion y jwt_modulo pasan por esta misma comprobación.
        usuario = usuario_vigente(payload.get('user_id'))
        if usuario is None:
            log_security_event('JWT_REVOKED', 'Usuario inexistente o inactivo', user=payload.get('username'))
            return jsonify({'error': 'Token is invalid or expired'}), 401
        
        # El rol vigente se lee de la base; el claim del token puede haber quedado desactualizado.
        request.current_user = {
            'user_id': payload.get('user_id'),
            'username': payload.get('username'),
            'role': usuario.role,
        }
        
        return f(*args, **kwargs)
    return decorated


def jwt_o_sesion(modulo):
    """Acepta un JWT de acceso válido o una sesión web con el módulo indicado.

    Para los GET de api_rest que también consumen pantallas: el navegador los
    llama con la cookie de sesión y sin token. Si llega un Bearer, debe ser
    válido y tener el módulo (jwt_modulo; no cae a la sesión). Sin credencial
    responde 401; con sesión o Bearer sin el módulo, 403.
    """
    def decorator(f):
        con_jwt = jwt_modulo(modulo, 'view')(f)

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


# Métodos que modifican datos: exigen edición del módulo.
METODOS_ESCRITURA = ('POST', 'PUT', 'PATCH', 'DELETE')


def jwt_modulo(modulo, nivel='view'):
    """JWT válido, acceso al módulo y, en escrituras, edición del módulo.

    Pensado para las escrituras de api_rest. Sin token o con token inválido responde
    401 (jwt_required). Con token válido pero sin el módulo, o sin edición en una
    escritura, responde 403 JSON. El id sale del token y el rol vigente de la base;
    no usa la sesión web.

    nivel='view': en lecturas basta con acceso de solo lectura o de edición.
    nivel='edit': exige edición también en lecturas.
    En POST, PUT, PATCH y DELETE siempre se exige edición, como protect_blueprint.
    """
    if nivel not in ('view', 'edit'):
        raise ValueError(f"nivel de acceso inválido: {nivel!r}")

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            usuario = request.current_user
            role = usuario.get('role')
            user_id = usuario.get('user_id')
            if not role or user_id is None:
                log_access_denied(usuario.get('username'), modulo)
                return jsonify({'error': 'Sin acceso al módulo'}), 403
            if not module_allowed(modulo, role=role, user_id=user_id):
                log_access_denied(usuario.get('username'), modulo)
                return jsonify({'error': 'Sin acceso al módulo'}), 403
            requiere_edicion = nivel == 'edit' or request.method in METODOS_ESCRITURA
            if requiere_edicion and get_user_module_access(modulo, user_id, role) != 'edit':
                log_access_denied(usuario.get('username'), modulo)
                return jsonify({'error': 'Sin permiso de edición en el módulo'}), 403
            return f(*args, **kwargs)
        return jwt_required(decorated)
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


def es_ruta_api():
    """Las rutas /api/ responden JSON (401 o 403). Las pantallas HTML siguen redirigiendo."""
    return "/api/" in request.path


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
                    if es_ruta_api():
                        return jsonify({'error': 'Sin permiso de edición en el módulo'}), 403
                    flash("Tu acceso a esta sección es solo lectura.", "warning")
                    return redirect(request.referrer or url_for("auth.login")), 403
            return  # access granted
        if session.get("user"):
            # Usuario logueado pero sin acceso, redirigir a ruta permitida
            log_access_denied(session.get("user"), module)
            if es_ruta_api():
                return jsonify({'error': 'Sin acceso al módulo'}), 403
            route = first_allowed_route(session.get("role"))
            if route == request.path:
                # La pantalla de destino también niega el acceso: no redirigir a sí misma
                route = SIN_ACCESO_ROUTE
            flash("No tienes acceso a esta sección.", "warning")
            return redirect(route)
        if es_ruta_api():
            return jsonify({'error': 'Sesión requerida'}), 401
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

