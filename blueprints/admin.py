"""
Blueprint de Administración de Variables/Catálogos
Solo accesible para usuarios con rol 'admin'
"""
from functools import wraps
from decimal import Decimal
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask import current_app

from models import db
from models.gastos import CategoriaGasto, Proveedor
from models.tesoreria import InstrumentoPago, CuentaCorrienteFriar, PortadorInstrumento
from models.rrhh import Turno
from models.hr.employee import Employee
from models.core import Location, Product, BusinessUnit
from models.crm import LeadStage
from models.core.user import User
from models.core.user_permission import UserModulePermission
from security import ACCESS_MAP, MANAGED_MODULES, get_user_module_access

admin_bp = Blueprint("admin", __name__)


# =============================================================================
# Decorador de verificación de rol admin
# =============================================================================
def admin_required(f):
    """Decorador que verifica que el usuario tenga rol admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # En desarrollo local, permitir bypass para facilitar pruebas.
        env = (current_app.config.get("FLASK_ENV") or "").lower()
        if current_app.config.get("LOCAL_DEV_BYPASS_AUTH") and env in {"development", "dev", "local"}:
            return f(*args, **kwargs)

        if "user" not in session:
            flash("Debe iniciar sesión.", "warning")
            return redirect(url_for("auth.login"))
        if session.get("role") not in ["admin", "manager", "gerente"]:
            flash("Acceso denegado. Se requiere rol de administrador.", "danger")
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)
    return decorated_function


_FULL_ADMIN_ROLES = ("admin", "manager", "gerente")


def admin_or_hr_required(f):
    """Decorador: permite admin/manager/gerente y también hr (con restricciones de módulo)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        env = (current_app.config.get("FLASK_ENV") or "").lower()
        if current_app.config.get("LOCAL_DEV_BYPASS_AUTH") and env in {"development", "dev", "local"}:
            return f(*args, **kwargs)
        if "user" not in session:
            flash("Debe iniciar sesión.", "warning")
            return redirect(url_for("auth.login"))
        if session.get("role") not in (*_FULL_ADMIN_ROLES, "hr"):
            flash("Acceso denegado.", "danger")
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)
    return decorated_function


def _hr_modulo_allowed(modulo):
    """Para rol hr: solo permite módulo rrhh. Retorna respuesta de error o None si OK."""
    role = session.get("role", "")
    if role in _FULL_ADMIN_ROLES:
        return None
    if role == "hr" and modulo == "rrhh":
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "Acceso denegado a este módulo"}), 403
    flash("Acceso denegado. El rol RRHH solo puede administrar el módulo RRHH.", "danger")
    return redirect(url_for("admin.admin_modulo", modulo="rrhh"))


# =============================================================================
# Mapeo de modelos por módulo
# =============================================================================
ADMIN_MODELS = {
    "gastos": {
        "categorias": {
            "model": CategoriaGasto,
            "name": "Categorías de Gasto",
            "fields": ["nombre", "descripcion", "activo"],
            "required": ["nombre"],
        },
        "proveedores": {
            "model": Proveedor,
            "name": "Proveedores",
            "fields": ["nombre", "cuit", "email", "telefono", "direccion", "activo"],
            "required": ["nombre"],
        },
    },
    "tesoreria": {
        "instrumentos": {
            "model": InstrumentoPago,
            "name": "Instrumentos de Pago",
            "fields": ["nombre", "descripcion", "requiere_portador", "activo"],
            "required": ["nombre"],
        },
        "portadores": {
            "model": PortadorInstrumento,
            "name": "Portadores de Instrumento",
            "fields": ["nombre", "documento", "telefono", "notas", "activo"],
            "required": ["nombre"],
        },
        "cuenta_friar": {
            "model": CuentaCorrienteFriar,
            "name": "Cuenta Corriente Friar",
            "fields": ["saldo_inicial", "observaciones"],
            "required": ["saldo_inicial"],
        },
    },
    "rrhh": {
        "empleados": {
            "model": Employee,
            "name": "Empleados",
            "fields": ["first_name", "last_name", "email", "phone", "position", "department", "hire_date", "salary", "location_id", "clock_id", "turno_id", "is_active"],
            "required": ["first_name", "last_name"],
        },
        "turnos": {
            "model": Turno,
            "name": "Turnos",
            "fields": ["nombre", "descripcion", "activo"],
            "required": ["nombre"],
        },
    },
    "stock": {
        "ubicaciones": {
            "model": Location,
            "name": "Ubicaciones",
            "fields": ["name", "address"],
            "required": ["name"],
        },
        "productos": {
            "model": Product,
            "name": "Productos",
            "fields": ["name", "sku", "price", "category"],
            "required": ["name"],
        },
        "unidades": {
            "model": BusinessUnit,
            "name": "Unidades de Negocio",
            "fields": ["name"],
            "required": ["name"],
        },
    },
    "marketing": {
        "pipeline": {
            "model": LeadStage,
            "name": "Etapas del Pipeline",
            "fields": ["name", "position", "activo"],
            "required": ["name", "position"],
        },
    },
}

EMPLOYEE_POSITION_OPTIONS = [
    "vendedor",
    "administracion",
    "gerente",
    "cajero",
    "deposito",
    "jefe ventas",
    "tesoreria",
    "jefe deposito",
    "reparto",
]

EMPLOYEE_FIELD_LABELS = {
    "first_name": "Nombre",
    "last_name": "Apellido",
    "email": "Email",
    "phone": "Telefono",
    "position": "Posicion",
    "department": "Departamento",
    "hire_date": "Fecha ingreso",
    "salary": "Salario",
    "location_id": "Ubicacion",
    "clock_id": "ID Reloj",
    "turno_id": "Turno",
    "is_active": "Estado",
}


# =============================================================================
# Rutas Web
# =============================================================================
@admin_bp.route("/admin")
@admin_or_hr_required
def admin_dashboard():
    """Dashboard principal de administración"""
    if session.get("role") == "hr":
        return redirect(url_for("admin.admin_modulo", modulo="rrhh"))
    stats = {}
    for modulo, entidades in ADMIN_MODELS.items():
        stats[modulo] = {}
        for entidad, config in entidades.items():
            model = config["model"]
            try:
                total = model.query.count()
                # Contar activos si el modelo tiene campo 'activo'
                if hasattr(model, 'activo'):
                    activos = model.query.filter_by(activo=True).count()
                else:
                    activos = total
                stats[modulo][entidad] = {"total": total, "activos": activos, "name": config["name"]}
            except Exception:
                stats[modulo][entidad] = {"total": 0, "activos": 0, "name": config["name"]}
    
    return render_template("admin/admin_dashboard.html", stats=stats, modulos=ADMIN_MODELS)


@admin_bp.route("/admin/<modulo>")
@admin_or_hr_required
def admin_modulo(modulo):
    """Vista de administración para un módulo específico"""
    err = _hr_modulo_allowed(modulo)
    if err:
        return err
    if modulo not in ADMIN_MODELS:
        flash("Módulo no encontrado.", "warning")
        return redirect(url_for("admin.admin_dashboard"))
    
    entidades = ADMIN_MODELS[modulo]
    data = {}
    
    for entidad, config in entidades.items():
        model = config["model"]
        try:
            registros = model.query.all()
            data[entidad] = {
                "registros": registros,
                "name": config["name"],
                "fields": config["fields"],
                "required": config["required"],
            }
        except Exception as e:
            data[entidad] = {
                "registros": [],
                "name": config["name"],
                "fields": config["fields"],
                "required": config["required"],
                "error": str(e),
            }
    
    locations = []
    employee_positions = []
    field_labels = {}
    employee_turnos = []
    if modulo == "rrhh":
        locations = [
            {"id": loc.id, "name": loc.name}
            for loc in Location.query.order_by(Location.name).all()
        ]
        employee_positions = EMPLOYEE_POSITION_OPTIONS
        field_labels = EMPLOYEE_FIELD_LABELS
        employee_turnos = [
            {"id": t.id, "nombre": t.nombre}
            for t in Turno.query.filter_by(activo=True).order_by(Turno.nombre).all()
        ]

    return render_template(
        "admin/admin_modulo.html",
        modulo=modulo,
        entidades=data,
        modulos=ADMIN_MODELS,
        locations=locations,
        employee_positions=employee_positions,
        field_labels=field_labels,
        employee_turnos=employee_turnos,
    )


def coerce_field_value(field, val):
    if val is None:
        return None
    if isinstance(val, str) and val.strip() == "":
        return None

    if field in ("is_active", "activo"):
        if isinstance(val, str):
            return val.strip().lower() in ["true", "1", "yes", "on"]
        return bool(val)

    if field.endswith("_id"):
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    if "date" in field and isinstance(val, str):
        try:
            from datetime import datetime
            return datetime.strptime(val, "%Y-%m-%d").date()
        except ValueError:
            return None

    if field in ("salary",) or "precio" in field.lower() or "price" in field.lower():
        try:
            return Decimal(str(val))
        except Exception:
            return None

    return val


def get_or_create_friar_proveedor_id() -> int:
    prov = Proveedor.query.filter(Proveedor.nombre.ilike("friar")).first()
    if prov:
        return int(prov.id)

    prov = Proveedor(nombre="Friar", activo=True)
    db.session.add(prov)
    db.session.flush()
    return int(prov.id)


# =============================================================================
# APIs REST para CRUD
# =============================================================================
@admin_bp.route("/api/admin/<modulo>/<entidad>", methods=["GET"])
@admin_or_hr_required
def api_listar(modulo, entidad):
    """Listar todos los registros de una entidad"""
    err = _hr_modulo_allowed(modulo)
    if err:
        return err
    if modulo not in ADMIN_MODELS or entidad not in ADMIN_MODELS[modulo]:
        return jsonify({"error": "Entidad no encontrada"}), 404
    
    config = ADMIN_MODELS[modulo][entidad]
    model = config["model"]
    
    try:
        items = model.query.all()
        result = []
        for item in items:
            row = {"id": item.id}
            for field in config["fields"]:
                val = getattr(item, field, None)
                # Serialización segura para JSON
                if isinstance(val, Decimal):
                    val = float(val)
                elif hasattr(val, "isoformat"):
                    # date/datetime
                    try:
                        val = val.isoformat()
                    except Exception:
                        val = str(val)
                elif hasattr(val, 'strftime'):
                    # time u otros
                    try:
                        val = val.strftime('%H:%M') if hasattr(val, 'hour') else val.strftime('%Y-%m-%d')
                    except Exception:
                        val = str(val)
                row[field] = val
            result.append(row)
        return jsonify({"items": result, "total": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/admin/<modulo>/<entidad>", methods=["POST"])
@admin_or_hr_required
def api_crear(modulo, entidad):
    """Crear un nuevo registro"""
    err = _hr_modulo_allowed(modulo)
    if err:
        return err
    if modulo not in ADMIN_MODELS or entidad not in ADMIN_MODELS[modulo]:
        return jsonify({"error": "Entidad no encontrada"}), 404
    
    config = ADMIN_MODELS[modulo][entidad]
    model = config["model"]
    data = request.get_json() or {}
    
    # Validar campos requeridos
    for field in config["required"]:
        if not data.get(field):
            return jsonify({"error": f"Campo requerido: {field}"}), 400
    
    try:
        item = model()
        for field in config["fields"]:
            if field in data:
                val = coerce_field_value(field, data[field])
                # Convertir strings de tiempo
                if 'hora' in field.lower() and isinstance(val, str) and ':' in val:
                    from datetime import time
                    parts = val.split(':')
                    val = time(int(parts[0]), int(parts[1]))
                setattr(item, field, val)

        if modulo == "tesoreria" and entidad == "cuenta_friar":
            # No pedir proveedor_id: Friar es único y se asigna server-side
            item.proveedor_id = get_or_create_friar_proveedor_id()
        
        db.session.add(item)
        db.session.commit()
        return jsonify({"success": True, "id": item.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/admin/<modulo>/<entidad>/<int:id>", methods=["PUT"])
@admin_or_hr_required
def api_actualizar(modulo, entidad, id):
    """Actualizar un registro existente"""
    err = _hr_modulo_allowed(modulo)
    if err:
        return err
    if modulo not in ADMIN_MODELS or entidad not in ADMIN_MODELS[modulo]:
        return jsonify({"error": "Entidad no encontrada"}), 404
    
    config = ADMIN_MODELS[modulo][entidad]
    model = config["model"]
    data = request.get_json() or {}
    
    try:
        item = model.query.get_or_404(id)
        for field in config["fields"]:
            if field in data:
                val = coerce_field_value(field, data[field])
                # Convertir strings de tiempo
                if 'hora' in field.lower() and isinstance(val, str) and ':' in val:
                    from datetime import time
                    parts = val.split(':')
                    val = time(int(parts[0]), int(parts[1]))
                setattr(item, field, val)
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/admin/<modulo>/<entidad>/<int:id>", methods=["DELETE"])
@admin_or_hr_required
def api_eliminar(modulo, entidad, id):
    """Eliminar un registro"""
    err = _hr_modulo_allowed(modulo)
    if err:
        return err
    if modulo not in ADMIN_MODELS or entidad not in ADMIN_MODELS[modulo]:
        return jsonify({"error": "Entidad no encontrada"}), 404
    
    config = ADMIN_MODELS[modulo][entidad]
    model = config["model"]
    
    try:
        item = model.query.get_or_404(id)
        db.session.delete(item)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/admin/<modulo>/<entidad>/<int:id>/toggle", methods=["PATCH"])
@admin_or_hr_required
def api_toggle(modulo, entidad, id):
    """Activar/Desactivar un registro"""
    err = _hr_modulo_allowed(modulo)
    if err:
        return err
    if modulo not in ADMIN_MODELS or entidad not in ADMIN_MODELS[modulo]:
        return jsonify({"error": "Entidad no encontrada"}), 404
    
    config = ADMIN_MODELS[modulo][entidad]
    model = config["model"]
    
    try:
        item = model.query.get_or_404(id)
        if not hasattr(item, 'activo'):
            return jsonify({"error": "Esta entidad no soporta activación/desactivación"}), 400
        
        item.activo = not item.activo
        db.session.commit()
        return jsonify({"success": True, "activo": item.activo})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Control de Accesos por Usuario
# =============================================================================
@admin_bp.route("/admin/accesos")
@admin_required
def admin_accesos():
    """Vista ABM de control de accesos por módulo"""
    users = User.query.filter_by(active=True).order_by(User.username).all()
    return render_template(
        "admin/admin_accesos.html",
        users=users,
        managed_modules=MANAGED_MODULES,
        access_map=ACCESS_MAP,
    )


@admin_bp.route("/api/admin/accesos", methods=["GET"])
@admin_required
def api_listar_accesos():
    """Lista usuarios activos con permisos efectivos"""
    users = User.query.filter_by(active=True).order_by(User.username).all()
    result = []
    for user in users:
        role_modules = ACCESS_MAP.get(user.role, [])
        has_all = "all" in role_modules
        permissions = {}
        for mod in MANAGED_MODULES:
            if has_all or mod in role_modules:
                permissions[mod] = "edit"
            else:
                permissions[mod] = get_user_module_access(mod, user.id, user.role)
        result.append({
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": permissions,
            "role_modules": role_modules,
        })
    return jsonify(result)


@admin_bp.route("/api/admin/accesos/<int:user_id>", methods=["PUT"])
@admin_required
def api_guardar_accesos(user_id):
    """Guarda permisos individuales para un usuario"""
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    perms = data.get("permissions", {})

    role_modules = ACCESS_MAP.get(user.role, [])
    has_all = "all" in role_modules

    try:
        for mod, level in perms.items():
            if mod not in MANAGED_MODULES:
                continue
            # Skip modules already inherited from role
            if has_all or mod in role_modules:
                continue
            if level not in ("view", "edit", "none"):
                continue

            existing = UserModulePermission.query.filter_by(
                user_id=user_id, module=mod
            ).first()

            if level == "none":
                if existing:
                    db.session.delete(existing)
            elif existing:
                existing.access_level = level
            else:
                db.session.add(UserModulePermission(
                    user_id=user_id, module=mod, access_level=level
                ))

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
