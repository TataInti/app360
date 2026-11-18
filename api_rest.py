# api_rest.py - REST API endpoints for frontend integration
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from models import db
from models import (
    Product, Location, StockLevel, Lead, BusinessUnit,
    PurchaseOrder, PurchaseOrderItem, PurchaseReceipt,
    Employee, Attendance, Goal, Survey, SurveyResponse, User
)
from security import (
    generate_access_token, generate_refresh_token, decode_token,
    jwt_required, jwt_o_sesion, log_login_attempt, log_security_event
)
from extensions import limiter

api_rest = Blueprint('api_rest', __name__, url_prefix='/api')


def error_response(status_code, message, details=None):
    payload = {"error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def get_json_payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def require_fields(data, fields):
    missing = [
        field
        for field in fields
        if field not in data or data[field] is None or data[field] == ""
    ]
    if missing:
        return error_response(400, "Missing required fields", {"fields": missing})
    return None


def parse_iso_datetime(value, field_name):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid datetime format for {field_name}")


def parse_iso_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        raise ValueError(f"Invalid date format for {field_name}")


def parse_pagination_args():
    page_raw = request.args.get("page", "1")
    per_page_raw = request.args.get("per_page", "50")
    try:
        page = int(page_raw)
        per_page = int(per_page_raw)
    except ValueError:
        return None, error_response(400, "Invalid pagination params")

    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 1
    if per_page > 200:
        per_page = 200

    return (page, per_page), None


def paginate_query(query):
    pagination, error = parse_pagination_args()
    if error:
        return None, error
    page, per_page = pagination
    result = query.paginate(page=page, per_page=per_page, error_out=False)
    return result, None

# -----------------------------------------------------------------------------
# AUTH ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    }), 200


@api_rest.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """Login endpoint for API - returns JWT tokens"""
    data = get_json_payload()
    if not data:
        return error_response(400, "Invalid request body")

    missing = require_fields(data, ["username", "password"])
    if missing:
        return missing

    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username, active=True).first()
    if user and user.check_password(password):
        # Generate JWT tokens
        access_token = generate_access_token(user.id, user.username, user.role)
        refresh_token = generate_refresh_token(user.id, user.username)
        
        log_login_attempt(username, success=True, ip=request.remote_addr)
        
        return jsonify({
            'user': user.username,
            'role': user.role,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': 900,  # 15 minutes
            'message': 'Login successful'
        }), 200
    
    log_login_attempt(username, success=False, ip=request.remote_addr)
    return error_response(401, "Invalid credentials")


@api_rest.route('/refresh', methods=['POST'])
@limiter.limit("10 per minute")
def refresh_token():
    """Refresh access token using refresh token"""
    data = get_json_payload()
    if not data:
        return error_response(400, "Invalid request body")

    missing = require_fields(data, ["refresh_token"])
    if missing:
        return missing
    
    payload = decode_token(data['refresh_token'])
    if not payload or payload.get('type') != 'refresh':
        log_security_event('REFRESH_TOKEN_INVALID', 'Invalid refresh token used')
        return error_response(401, "Invalid or expired refresh token")
    
    # Get user to ensure they're still active
    user = User.query.filter_by(username=payload['username'], active=True).first()
    if not user:
        return error_response(401, "User not found or inactive")
    
    # Generate new access token
    access_token = generate_access_token(user.id, user.username, user.role)
    
    return jsonify({
        'access_token': access_token,
        'token_type': 'Bearer',
        'expires_in': 900
    }), 200


@api_rest.route('/me', methods=['GET'])
@jwt_required
def get_current_user():
    """Get current authenticated user info"""
    return jsonify({
        'user_id': request.current_user['user_id'],
        'username': request.current_user['username'],
        'role': request.current_user['role']
    }), 200


# -----------------------------------------------------------------------------
# PRODUCTS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/products', methods=['GET'])
@jwt_required
def get_products():
    """Get all products with their business unit information"""
    try:
        result, error = paginate_query(Product.query)
        if error:
            return error
        items = [{
            'id': p.id,
            'sku': p.sku,
            'name': p.name,
            'description': p.description,
            'price': float(p.price) if p.price else None,
            'category': p.category,
            'stock_quantity': p.stock_quantity,
            'min_stock_level': p.min_stock_level,
            'business_unit_id': p.business_unit_id,
            'location_id': p.location_id
        } for p in result.items]
        return jsonify({
            "items": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list products")
        return error_response(500, "Internal server error")

@api_rest.route('/products', methods=['POST'])
@jwt_required
def create_product():
    """Create a new product"""
    try:
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        missing = require_fields(data, ["name"])
        if missing:
            return missing
        product = Product(
            name=data['name'],
            description=data.get('description'),
            price=data.get('price'),
            business_unit_id=data.get('business_unit_id'),
            location_id=data.get('location_id')
        )
        db.session.add(product)
        db.session.commit()
        return jsonify({'id': product.id, 'message': 'Product created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to create product")
        return error_response(500, "Internal server error")

@api_rest.route('/products/<int:product_id>', methods=['PUT'])
@jwt_required
def update_product(product_id):
    """Update a product"""
    try:
        product = Product.query.get_or_404(product_id)
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        product.name = data.get('name', product.name)
        product.description = data.get('description', product.description)
        product.price = data.get('price', product.price)
        product.business_unit_id = data.get('business_unit_id', product.business_unit_id)
        product.location_id = data.get('location_id', product.location_id)
        db.session.commit()
        return jsonify({'message': 'Product updated successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to update product")
        return error_response(500, "Internal server error")

@api_rest.route('/products/<int:product_id>', methods=['DELETE'])
@jwt_required
def delete_product(product_id):
    """Delete a product"""
    try:
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        return jsonify({'message': 'Product deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to delete product")
        return error_response(500, "Internal server error")

# -----------------------------------------------------------------------------
# LOCATIONS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/locations', methods=['GET'])
@jwt_required
def get_locations():
    """Get all locations"""
    try:
        result, error = paginate_query(Location.query)
        if error:
            return error
        items = [{
            'id': l.id,
            'name': l.name,
            'address': l.address,
            'city': l.city,
            'province': l.province,
            'country': l.country,
            'phone': l.phone,
            'email': l.email
        } for l in result.items]
        return jsonify({
            "items": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list locations")
        return error_response(500, "Internal server error")

@api_rest.route('/locations', methods=['POST'])
@jwt_required
def create_location():
    """Create a new location"""
    try:
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        missing = require_fields(data, ["name"])
        if missing:
            return missing
        location = Location(
            name=data['name'],
            address=data.get('address'),
            city=data.get('city'),
            province=data.get('province'),
            country=data.get('country'),
            phone=data.get('phone'),
            email=data.get('email')
        )
        db.session.add(location)
        db.session.commit()
        return jsonify({'id': location.id, 'message': 'Location created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to create location")
        return error_response(500, "Internal server error")

@api_rest.route('/locations/<int:location_id>', methods=['PUT'])
@jwt_required
def update_location(location_id):
    """Update a location"""
    try:
        location = Location.query.get_or_404(location_id)
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        location.name = data.get('name', location.name)
        location.address = data.get('address', location.address)
        location.city = data.get('city', location.city)
        location.province = data.get('province', location.province)
        location.country = data.get('country', location.country)
        location.phone = data.get('phone', location.phone)
        location.email = data.get('email', location.email)
        db.session.commit()
        return jsonify({'message': 'Location updated successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to update location")
        return error_response(500, "Internal server error")

@api_rest.route('/locations/<int:location_id>', methods=['DELETE'])
@jwt_required
def delete_location(location_id):
    """Delete a location"""
    try:
        location = Location.query.get_or_404(location_id)
        db.session.delete(location)
        db.session.commit()
        return jsonify({'message': 'Location deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to delete location")
        return error_response(500, "Internal server error")

# -----------------------------------------------------------------------------
# LEADS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/leads', methods=['GET'])
@jwt_required
def get_leads():
    """Get all leads with related information"""
    try:
        query = Lead.query.options(
            selectinload(Lead.business_unit),
            selectinload(Lead.product),
            selectinload(Lead.location),
            selectinload(Lead.campaign),
        )
        result, error = paginate_query(query)
        if error:
            return error
        items = [{
            'id': l.id,
            'name': l.name,
            'phone': l.phone,
            'email': l.email,
            'source': l.source,
            'status': l.status,
            'stage': l.stage,
            'business_unit': {
                'id': l.business_unit.id,
                'name': l.business_unit.name
            } if l.business_unit else None,
            'product': {
                'id': l.product.id,
                'name': l.product.name
            } if l.product else None,
            'location': {
                'id': l.location.id,
                'name': l.location.name
            } if l.location else None,
            'owner_name': l.owner_name,
            'last_contacted_at': l.last_contacted_at.isoformat() if l.last_contacted_at else None,
            'campaign': {
                'id': l.campaign.id,
                'name': l.campaign.name
            } if l.campaign else None
        } for l in result.items]
        return jsonify({
            "items": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list leads")
        return error_response(500, "Internal server error")

@api_rest.route('/leads', methods=['POST'])
@jwt_required
def create_lead():
    """Create a new lead"""
    try:
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        missing = require_fields(data, ["name", "business_unit_id"])
        if missing:
            return missing
        lead = Lead(
            name=data['name'],
            phone=data.get('phone'),
            email=data.get('email'),
            source=data.get('source'),
            status=data.get('status', 'nuevo'),
            stage=data.get('stage', 'nuevo'),
            business_unit_id=data.get('business_unit_id'),
            product_id=data.get('product_id'),
            location_id=data.get('location_id'),
            owner_name=data.get('owner_name'),
            campaign_id=data.get('campaign_id')
        )
        db.session.add(lead)
        db.session.commit()
        return jsonify({'id': lead.id, 'message': 'Lead created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to create lead")
        return error_response(500, "Internal server error")

@api_rest.route('/leads/<int:lead_id>', methods=['PUT'])
@jwt_required
def update_lead(lead_id):
    """Update a lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        lead.name = data.get('name', lead.name)
        lead.phone = data.get('phone', lead.phone)
        lead.email = data.get('email', lead.email)
        lead.source = data.get('source', lead.source)
        lead.status = data.get('status', lead.status)
        lead.stage = data.get('stage', lead.stage)
        lead.business_unit_id = data.get('business_unit_id', lead.business_unit_id)
        lead.product_id = data.get('product_id', lead.product_id)
        lead.location_id = data.get('location_id', lead.location_id)
        lead.owner_name = data.get('owner_name', lead.owner_name)
        lead.campaign_id = data.get('campaign_id', lead.campaign_id)
        db.session.commit()
        return jsonify({'message': 'Lead updated successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to update lead")
        return error_response(500, "Internal server error")

@api_rest.route('/leads/<int:lead_id>', methods=['DELETE'])
@jwt_required
def delete_lead(lead_id):
    """Delete a lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        db.session.delete(lead)
        db.session.commit()
        return jsonify({'message': 'Lead deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to delete lead")
        return error_response(500, "Internal server error")

# -----------------------------------------------------------------------------
# STOCK ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/stock', methods=['GET'])
@jwt_required
def get_stock():
    """Get all stock records with product and location information"""
    try:
        result, error = paginate_query(StockLevel.query)
        if error:
            return error
        items = [{
            'id': s.id,
            'product_id': s.product_id,
            'location_id': s.location_id,
            'quantity': s.quantity,
            'min_quantity': s.min_quantity,
            'max_quantity': s.max_quantity,
            'batch_number': s.batch_number,
            'expiry_date': s.expiry_date.isoformat() if s.expiry_date else None,
            'notes': s.notes
        } for s in result.items]
        return jsonify({
            "items": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list stock records")
        return error_response(500, "Internal server error")

@api_rest.route('/stock', methods=['POST'])
@jwt_required
def create_stock():
    """Create a new stock record"""
    try:
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        missing = require_fields(data, ["product_id", "location_id"])
        if missing:
            return missing
        expiry_date = parse_iso_date(data.get('expiry_date'), 'expiry_date')
        stock = StockLevel(
            product_id=data['product_id'],
            location_id=data['location_id'],
            quantity=data.get('quantity', 0),
            min_quantity=data.get('min_quantity', 0),
            max_quantity=data.get('max_quantity'),
            batch_number=data.get('batch_number'),
            expiry_date=expiry_date,
            notes=data.get('notes')
        )
        db.session.add(stock)
        db.session.commit()
        return jsonify({'id': stock.id, 'message': 'Stock record created successfully'}), 201
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to create stock record")
        return error_response(500, "Internal server error")

@api_rest.route('/stock/<int:stock_id>', methods=['PUT'])
@jwt_required
def update_stock(stock_id):
    """Update a stock record"""
    try:
        stock = StockLevel.query.get_or_404(stock_id)
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        stock.product_id = data.get('product_id', stock.product_id)
        stock.location_id = data.get('location_id', stock.location_id)
        stock.quantity = data.get('quantity', stock.quantity)
        stock.min_quantity = data.get('min_quantity', stock.min_quantity)
        stock.max_quantity = data.get('max_quantity', stock.max_quantity)
        stock.batch_number = data.get('batch_number', stock.batch_number)
        if 'expiry_date' in data:
            stock.expiry_date = parse_iso_date(data.get('expiry_date'), 'expiry_date')
        stock.notes = data.get('notes', stock.notes)
        db.session.commit()
        return jsonify({'message': 'Stock record updated successfully'})
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to update stock record")
        return error_response(500, "Internal server error")

@api_rest.route('/stock/<int:stock_id>', methods=['DELETE'])
@jwt_required
def delete_stock(stock_id):
    """Delete a stock record"""
    try:
        stock = StockLevel.query.get_or_404(stock_id)
        db.session.delete(stock)
        db.session.commit()
        return jsonify({'message': 'Stock record deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to delete stock record")
        return error_response(500, "Internal server error")

# -----------------------------------------------------------------------------
# COMPRAS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/compras', methods=['GET'])
@jwt_o_sesion('compras')
def get_compras():
    """Get all purchase orders."""
    try:
        query = PurchaseOrder.query
        result, error = paginate_query(query)
        if error:
            return error

        items = []
        for o in result.items:
            items.append({
                'id': o.id,
                'supplier': getattr(o, 'supplier', None),
                'supplier_id': getattr(o, 'supplier_id', None),
                'product_id': getattr(o, 'product_id', None),
                'quantity': getattr(o, 'quantity', None),
                'unit_price': float(o.unit_price) if getattr(o, 'unit_price', None) is not None else None,
                'total_amount': float(o.total_amount) if getattr(o, 'total_amount', None) is not None else None,
                'monto_total': float(o.monto_total) if getattr(o, 'monto_total', None) is not None else None,
                'order_date': o.order_date.isoformat() if o.order_date else None,
                'expected_delivery_date': o.expected_delivery_date.isoformat() if o.expected_delivery_date else None,
                'status': getattr(o, 'status', None),
                'notes': getattr(o, 'notes', None),
                'location_id': getattr(o, 'location_id', None),
                'comprobante_numero': getattr(o, 'comprobante_numero', None),
                'instrumento_id': getattr(o, 'instrumento_id', None),
                'tesoreria_movimiento_id': getattr(o, 'tesoreria_movimiento_id', None),
                'created_at': o.created_at.isoformat() if getattr(o, 'created_at', None) else None,
            })

        return jsonify({
            'items': items,
            'page': result.page,
            'per_page': result.per_page,
            'total': result.total,
            'pages': result.pages,
        })
    except Exception:
        current_app.logger.exception('Failed to list purchase orders')
        return error_response(500, 'Internal server error')


@api_rest.route('/compras/overview', methods=['GET'])
@jwt_o_sesion('compras')
def compras_overview():
    """KPIs simples para panel de compras (similar a paneles estratégicos)."""
    try:
        # Período default: últimos 30 días (en base a order_date o created_at)
        period_raw = request.args.get('period', '30')
        try:
            period_days = 30 if str(period_raw).lower() == 'ytd' else int(period_raw)
        except ValueError:
            period_days = 30

        today = datetime.utcnow().date()
        desde = date(today.year, 1, 1) if str(period_raw).lower() == 'ytd' else (today - timedelta(days=period_days - 1))

        q_period = PurchaseOrder.query.filter(
            PurchaseOrder.order_date >= desde,
            PurchaseOrder.order_date <= today,
        )

        total_orders = q_period.count()
        statuses = dict(
            q_period.with_entities(PurchaseOrder.status, func.count(PurchaseOrder.id))
            .group_by(PurchaseOrder.status)
            .all()
        )

        total_monto = q_period.with_entities(func.sum(PurchaseOrder.total_amount)).scalar() or 0

        return jsonify({
            'period': str(period_raw),
            'desde': desde.isoformat(),
            'hasta': today.isoformat(),
            'kpis': {
                'orders_total': int(total_orders),
                'monto_total': float(total_monto) if total_monto is not None else 0.0,
                'ticket_promedio': float(total_monto) / float(total_orders) if total_orders else 0.0,
            },
            'series': {
                'orders_por_estado': { (k or 'sin_estado'): int(v) for k, v in statuses.items() },
            }
        })
    except Exception:
        current_app.logger.exception('Failed to build compras overview')
        return error_response(500, 'Internal server error')

@api_rest.route('/compras', methods=['POST'])
@jwt_required
def create_compra():
    """Create a new purchase order"""
    try:
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        missing = require_fields(data, ["product_id", "quantity", "unit_price", "total_amount", "order_date"])
        if missing:
            return missing
        order_date = parse_iso_date(data.get('order_date'), 'order_date')
        expected_delivery_date = parse_iso_date(data.get('expected_delivery_date'), 'expected_delivery_date')

        supplier_id = data.get('supplier_id')
        supplier_name = data.get('supplier')
        if not supplier_name and supplier_id:
            supplier_name = f"Proveedor {supplier_id}"

        order = PurchaseOrder(
            supplier_id=supplier_id,
            supplier=supplier_name,
            product_id=data['product_id'],
            quantity=data['quantity'],
            unit_price=data['unit_price'],
            total_amount=data['total_amount'],
            location_id=data.get('location_id'),
            status=data.get('status', 'pendiente'),
            notes=data.get('notes'),
            order_date=order_date,
            expected_delivery_date=expected_delivery_date,
            monto_total=data.get('monto_total', data.get('total_amount')),
            comprobante_numero=data.get('comprobante_numero'),
            instrumento_id=data.get('instrumento_id'),
        )
        db.session.add(order)
        db.session.flush()

        # Mantener compat con detalle por items
        try:
            item = PurchaseOrderItem(order_id=order.id, product_id=data['product_id'], quantity=data['quantity'])
            db.session.add(item)
        except Exception:
            # Si por algún motivo la tabla/relación no está disponible, igual guardamos la OC.
            pass
        db.session.commit()
        return jsonify({
            'id': order.id,
            'supplier_id': order.supplier_id,
            'supplier': order.supplier,
            'product_id': order.product_id,
            'quantity': order.quantity,
            'unit_price': float(order.unit_price) if order.unit_price is not None else None,
            'total_amount': float(order.total_amount) if order.total_amount is not None else None,
            'monto_total': float(order.monto_total) if order.monto_total is not None else None,
            'order_date': order.order_date.isoformat() if order.order_date else None,
            'expected_delivery_date': order.expected_delivery_date.isoformat() if order.expected_delivery_date else None,
            'status': order.status,
            'notes': order.notes
        }), 201
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to create purchase order")
        return error_response(500, "Internal server error")

@api_rest.route('/compras/<int:order_id>', methods=['PUT'])
@jwt_required
def update_compra(order_id):
    """Update a purchase order"""
    try:
        order = PurchaseOrder.query.get_or_404(order_id)
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        order.supplier_id = data.get('supplier_id', order.supplier_id)
        order.supplier = data.get('supplier', order.supplier)
        order.product_id = data.get('product_id', order.product_id)
        order.quantity = data.get('quantity', order.quantity)
        order.unit_price = data.get('unit_price', order.unit_price)
        order.total_amount = data.get('total_amount', order.total_amount)
        order.monto_total = data.get('monto_total', order.monto_total)
        if 'order_date' in data:
            order.order_date = parse_iso_date(data.get('order_date'), 'order_date')
        if 'expected_delivery_date' in data:
            order.expected_delivery_date = parse_iso_date(data.get('expected_delivery_date'), 'expected_delivery_date')
        order.status = data.get('status', order.status)
        order.notes = data.get('notes', order.notes)
        order.location_id = data.get('location_id', order.location_id)
        db.session.commit()
        return jsonify({
            'id': order.id,
            'supplier_id': order.supplier_id,
            'supplier': order.supplier,
            'product_id': order.product_id,
            'quantity': order.quantity,
            'unit_price': float(order.unit_price) if order.unit_price is not None else None,
            'total_amount': float(order.total_amount) if order.total_amount is not None else None,
            'monto_total': float(order.monto_total) if order.monto_total is not None else None,
            'order_date': order.order_date.isoformat() if order.order_date else None,
            'expected_delivery_date': order.expected_delivery_date.isoformat() if order.expected_delivery_date else None,
            'status': order.status,
            'notes': order.notes
        })
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to update purchase order")
        return error_response(500, "Internal server error")

@api_rest.route('/compras/<int:order_id>', methods=['DELETE'])
@jwt_required
def delete_compra(order_id):
    """Delete a purchase order"""
    try:
        order = PurchaseOrder.query.get_or_404(order_id)
        db.session.delete(order)
        db.session.commit()
        return jsonify({'message': 'Purchase order deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to delete purchase order")
        return error_response(500, "Internal server error")

# -----------------------------------------------------------------------------
# RRHH ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/rrhh', methods=['GET'])
@jwt_o_sesion('rrhh')
def get_rrhh():
    """Get RRHH dashboard data"""
    try:
        # Get employee count
        employee_count = Employee.query.count()

        # Get attendance data for today
        today = db.func.current_date()
        attendance_today = Attendance.query.filter(
            db.func.date(Attendance.check_in) == today
        ).count()

        # Get goals data
        goals = Goal.query.all()
        goals_data = [{
            'id': g.id,
            'employee_name': g.employee.name if g.employee else 'N/A',
            'description': g.description,
            'target_value': g.target_value,
            'current_value': g.current_value,
            'deadline': g.deadline.isoformat() if g.deadline else None
        } for g in goals]

        return jsonify({
            'employee_count': employee_count,
            'attendance_today': attendance_today,
            'goals': goals_data
        })
    except Exception as e:
        current_app.logger.exception("Failed to load RRHH dashboard")
        return error_response(500, "Internal server error")

@api_rest.route('/rrhh/dotacion', methods=['GET'])
@jwt_required
def get_rrhh_dotacion():
    """Get employee staffing data"""
    try:
        result, error = paginate_query(Employee.query)
        if error:
            return error
        items = [{
            'id': e.id,
            'name': e.name,
            'position': e.position,
            'department': e.department,
            'hire_date': e.hire_date.isoformat() if e.hire_date else None,
            'salary': float(e.salary) if e.salary else None
        } for e in result.items]
        return jsonify({
            "items": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list staffing data")
        return error_response(500, "Internal server error")

@api_rest.route('/rrhh/empleados', methods=['GET'])
@jwt_o_sesion('rrhh')
def get_employees():
    """Get all employees"""
    try:
        result, error = paginate_query(Employee.query)
        if error:
            return error
        items = [{
            'id': e.id,
            'name': e.name,
            'first_name': e.first_name,
            'last_name': e.last_name,
            'email': e.email,
            'phone': e.phone,
            'position': e.position,
            'department': e.department,
            'hire_date': e.hire_date.isoformat() if e.hire_date else None,
            'salary': float(e.salary) if e.salary else None,
            'location_id': e.location_id,
            'is_active': e.is_active
        } for e in result.items]
        # Compat: algunos templates esperan `employees` en lugar de `items`.
        return jsonify({
            "items": items,
            "employees": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list employees")
        return error_response(500, "Internal server error")

@api_rest.route('/rrhh/empleados', methods=['POST'])
@jwt_required
def create_employee():
    """Create a new employee"""
    try:
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")
        missing = require_fields(data, ["first_name", "last_name", "email"])
        if missing:
            return missing
        hire_date = parse_iso_date(data.get('hire_date'), 'hire_date')

        employee = Employee(
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            phone=data.get('phone'),
            position=data.get('position'),
            department=data.get('department'),
            hire_date=hire_date,
            salary=data.get('salary'),
            location_id=data.get('location_id'),
            is_active=data.get('is_active', True)
        )

        db.session.add(employee)
        db.session.commit()

        return jsonify({
            'id': employee.id,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'email': employee.email,
            'phone': employee.phone,
            'position': employee.position,
            'department': employee.department,
            'hire_date': employee.hire_date.isoformat() if employee.hire_date else None,
            'salary': float(employee.salary) if employee.salary else None,
            'location_id': employee.location_id,
            'is_active': employee.is_active
        }), 201
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to create employee")
        return error_response(500, "Internal server error")

@api_rest.route('/rrhh/empleados/<int:id>', methods=['PUT'])
@jwt_required
def update_employee(id):
    """Update an employee"""
    try:
        employee = Employee.query.get_or_404(id)
        data = get_json_payload()
        if not data:
            return error_response(400, "Invalid request body")

        employee.first_name = data.get('first_name', employee.first_name)
        employee.last_name = data.get('last_name', employee.last_name)
        employee.email = data.get('email', employee.email)
        employee.phone = data.get('phone', employee.phone)
        employee.position = data.get('position', employee.position)
        employee.department = data.get('department', employee.department)
        if 'hire_date' in data:
            employee.hire_date = parse_iso_date(data.get('hire_date'), 'hire_date')
        employee.salary = data.get('salary', employee.salary)
        employee.location_id = data.get('location_id', employee.location_id)
        employee.is_active = data.get('is_active', employee.is_active)

        db.session.commit()

        return jsonify({
            'id': employee.id,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'email': employee.email,
            'phone': employee.phone,
            'position': employee.position,
            'department': employee.department,
            'hire_date': employee.hire_date.isoformat() if employee.hire_date else None,
            'salary': float(employee.salary) if employee.salary else None,
            'location_id': employee.location_id,
            'is_active': employee.is_active
        })
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to update employee")
        return error_response(500, "Internal server error")

@api_rest.route('/rrhh/empleados/<int:id>', methods=['DELETE'])
@jwt_required
def delete_employee(id):
    """Delete an employee"""
    try:
        employee = Employee.query.get_or_404(id)
        db.session.delete(employee)
        db.session.commit()
        return jsonify({'message': 'Employee deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to delete employee")
        return error_response(500, "Internal server error")

# -----------------------------------------------------------------------------
# BUSINESS UNITS ENDPOINT (helper for forms)
# -----------------------------------------------------------------------------
@api_rest.route('/business-units', methods=['GET'])
@jwt_required
def get_business_units():
    """Get all business units"""
    try:
        result, error = paginate_query(BusinessUnit.query)
        if error:
            return error
        items = [{
            'id': u.id,
            'name': u.name,
            'description': u.description
        } for u in result.items]
        return jsonify({
            "items": items,
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        })
    except Exception as e:
        current_app.logger.exception("Failed to list business units")
        return error_response(500, "Internal server error")