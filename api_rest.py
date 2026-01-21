# api_rest.py - REST API endpoints for frontend integration
from flask import Blueprint, jsonify, request
from datetime import datetime
from sqlalchemy import func
from models import db
from models import (
    Product, Location, StockLevel, Lead, BusinessUnit,
    PurchaseOrder, PurchaseOrderItem, PurchaseReceipt,
    Employee, Attendance, Goal, Survey, SurveyResponse
)

api_rest = Blueprint('api_rest', __name__, url_prefix='/api')

# -----------------------------------------------------------------------------
# PRODUCTS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/products', methods=['GET'])
def get_products():
    """Get all products with their business unit information"""
    try:
        products = Product.query.all()
        return jsonify([{
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
        } for p in products])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/products', methods=['POST'])
def create_product():
    """Create a new product"""
    try:
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500

@api_rest.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Update a product"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        product.name = data.get('name', product.name)
        product.description = data.get('description', product.description)
        product.price = data.get('price', product.price)
        product.business_unit_id = data.get('business_unit_id', product.business_unit_id)
        product.location_id = data.get('location_id', product.location_id)
        db.session.commit()
        return jsonify({'message': 'Product updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete a product"""
    try:
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        return jsonify({'message': 'Product deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# LOCATIONS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/locations', methods=['GET'])
def get_locations():
    """Get all locations"""
    try:
        locations = Location.query.all()
        return jsonify([{
            'id': l.id,
            'name': l.name,
            'address': l.address,
            'city': l.city,
            'province': l.province,
            'country': l.country,
            'phone': l.phone,
            'email': l.email
        } for l in locations])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/locations', methods=['POST'])
def create_location():
    """Create a new location"""
    try:
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500

@api_rest.route('/locations/<int:location_id>', methods=['PUT'])
def update_location(location_id):
    """Update a location"""
    try:
        location = Location.query.get_or_404(location_id)
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500

@api_rest.route('/locations/<int:location_id>', methods=['DELETE'])
def delete_location(location_id):
    """Delete a location"""
    try:
        location = Location.query.get_or_404(location_id)
        db.session.delete(location)
        db.session.commit()
        return jsonify({'message': 'Location deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# LEADS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/leads', methods=['GET'])
def get_leads():
    """Get all leads with related information"""
    try:
        leads = Lead.query.all()
        return jsonify([{
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
        } for l in leads])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/leads', methods=['POST'])
def create_lead():
    """Create a new lead"""
    try:
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500

@api_rest.route('/leads/<int:lead_id>', methods=['PUT'])
def update_lead(lead_id):
    """Update a lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500

@api_rest.route('/leads/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    """Delete a lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        db.session.delete(lead)
        db.session.commit()
        return jsonify({'message': 'Lead deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# STOCK ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/stock', methods=['GET'])
def get_stock():
    """Get all stock records with product and location information"""
    try:
        stock_records = StockLevel.query.all()
        return jsonify([{
            'id': s.id,
            'product_id': s.product_id,
            'location_id': s.location_id,
            'quantity': s.quantity,
            'min_quantity': s.min_quantity,
            'max_quantity': s.max_quantity,
            'batch_number': s.batch_number,
            'expiry_date': s.expiry_date.isoformat() if s.expiry_date else None,
            'notes': s.notes
        } for s in stock_records])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/stock', methods=['POST'])
def create_stock():
    """Create a new stock record"""
    try:
        data = request.get_json()
        stock = StockLevel(
            product_id=data['product_id'],
            location_id=data['location_id'],
            quantity=data.get('quantity', 0),
            min_quantity=data.get('min_quantity', 0),
            max_quantity=data.get('max_quantity'),
            batch_number=data.get('batch_number'),
            expiry_date=datetime.fromisoformat(data['expiry_date']) if data.get('expiry_date') else None,
            notes=data.get('notes')
        )
        db.session.add(stock)
        db.session.commit()
        return jsonify({'id': stock.id, 'message': 'Stock record created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/stock/<int:stock_id>', methods=['PUT'])
def update_stock(stock_id):
    """Update a stock record"""
    try:
        stock = StockLevel.query.get_or_404(stock_id)
        data = request.get_json()
        stock.product_id = data.get('product_id', stock.product_id)
        stock.location_id = data.get('location_id', stock.location_id)
        stock.quantity = data.get('quantity', stock.quantity)
        stock.min_quantity = data.get('min_quantity', stock.min_quantity)
        stock.max_quantity = data.get('max_quantity', stock.max_quantity)
        stock.batch_number = data.get('batch_number', stock.batch_number)
        stock.expiry_date = datetime.fromisoformat(data['expiry_date']) if data.get('expiry_date') else stock.expiry_date
        stock.notes = data.get('notes', stock.notes)
        db.session.commit()
        return jsonify({'message': 'Stock record updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/stock/<int:stock_id>', methods=['DELETE'])
def delete_stock(stock_id):
    """Delete a stock record"""
    try:
        stock = StockLevel.query.get_or_404(stock_id)
        db.session.delete(stock)
        db.session.commit()
        return jsonify({'message': 'Stock record deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# COMPRAS ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/compras', methods=['GET'])
def get_compras():
    """Get all purchase orders"""
    try:
        orders = PurchaseOrder.query.all()
        return jsonify([{
            'id': o.id,
            'supplier_id': o.supplier_id,
            'product_id': o.product_id,
            'quantity': o.quantity,
            'unit_price': float(o.unit_price) if o.unit_price else None,
            'total_amount': float(o.total_amount) if o.total_amount else None,
            'order_date': o.order_date.isoformat() if o.order_date else None,
            'expected_delivery_date': o.expected_delivery_date.isoformat() if o.expected_delivery_date else None,
            'status': o.status,
            'notes': o.notes
        } for o in orders])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/compras', methods=['POST'])
def create_compra():
    """Create a new purchase order"""
    try:
        data = request.get_json()
        order = PurchaseOrder(
            supplier_id=data.get('supplier_id'),
            product_id=data['product_id'],
            quantity=data['quantity'],
            unit_price=data['unit_price'],
            total_amount=data['total_amount'],
            order_date=datetime.fromisoformat(data['order_date']),
            expected_delivery_date=datetime.fromisoformat(data['expected_delivery_date']) if data.get('expected_delivery_date') else None,
            status=data.get('status', 'pendiente'),
            notes=data.get('notes'),
            location_id=data.get('location_id')
        )
        db.session.add(order)
        db.session.commit()
        return jsonify({
            'id': order.id,
            'supplier_id': order.supplier_id,
            'product_id': order.product_id,
            'quantity': order.quantity,
            'unit_price': float(order.unit_price) if order.unit_price else None,
            'total_amount': float(order.total_amount) if order.total_amount else None,
            'order_date': order.order_date.isoformat() if order.order_date else None,
            'expected_delivery_date': order.expected_delivery_date.isoformat() if order.expected_delivery_date else None,
            'status': order.status,
            'notes': order.notes
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/compras/<int:order_id>', methods=['PUT'])
def update_compra(order_id):
    """Update a purchase order"""
    try:
        order = PurchaseOrder.query.get_or_404(order_id)
        data = request.get_json()
        order.supplier_id = data.get('supplier_id', order.supplier_id)
        order.product_id = data.get('product_id', order.product_id)
        order.quantity = data.get('quantity', order.quantity)
        order.unit_price = data.get('unit_price', order.unit_price)
        order.total_amount = data.get('total_amount', order.total_amount)
        order.order_date = datetime.fromisoformat(data['order_date']) if data.get('order_date') else order.order_date
        order.expected_delivery_date = datetime.fromisoformat(data['expected_delivery_date']) if data.get('expected_delivery_date') else order.expected_delivery_date
        order.status = data.get('status', order.status)
        order.notes = data.get('notes', order.notes)
        order.location_id = data.get('location_id', order.location_id)
        db.session.commit()
        return jsonify({
            'id': order.id,
            'supplier_id': order.supplier_id,
            'product_id': order.product_id,
            'quantity': order.quantity,
            'unit_price': float(order.unit_price) if order.unit_price else None,
            'total_amount': float(order.total_amount) if order.total_amount else None,
            'order_date': order.order_date.isoformat() if order.order_date else None,
            'expected_delivery_date': order.expected_delivery_date.isoformat() if order.expected_delivery_date else None,
            'status': order.status,
            'notes': order.notes
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/compras/<int:order_id>', methods=['DELETE'])
def delete_compra(order_id):
    """Delete a purchase order"""
    try:
        order = PurchaseOrder.query.get_or_404(order_id)
        db.session.delete(order)
        db.session.commit()
        return jsonify({'message': 'Purchase order deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# RRHH ENDPOINTS
# -----------------------------------------------------------------------------
@api_rest.route('/rrhh', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500

@api_rest.route('/rrhh/dotacion', methods=['GET'])
def get_rrhh_dotacion():
    """Get employee staffing data"""
    try:
        employees = Employee.query.all()
        return jsonify([{
            'id': e.id,
            'name': e.name,  # Uses the property
            'position': e.position,
            'department': e.department,
            'hire_date': e.hire_date.isoformat() if e.hire_date else None,
            'salary': float(e.salary) if e.salary else None
        } for e in employees])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/rrhh/empleados', methods=['GET'])
def get_employees():
    """Get all employees"""
    try:
        employees = Employee.query.all()
        return jsonify([{
            'id': e.id,
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
        } for e in employees])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_rest.route('/rrhh/empleados', methods=['POST'])
def create_employee():
    """Create a new employee"""
    try:
        data = request.get_json()

        employee = Employee(
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            phone=data.get('phone'),
            position=data.get('position'),
            department=data.get('department'),
            hire_date=datetime.fromisoformat(data['hire_date']) if data.get('hire_date') else None,
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
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/rrhh/empleados/<int:id>', methods=['PUT'])
def update_employee(id):
    """Update an employee"""
    try:
        employee = Employee.query.get_or_404(id)
        data = request.get_json()

        employee.first_name = data.get('first_name', employee.first_name)
        employee.last_name = data.get('last_name', employee.last_name)
        employee.email = data.get('email', employee.email)
        employee.phone = data.get('phone', employee.phone)
        employee.position = data.get('position', employee.position)
        employee.department = data.get('department', employee.department)
        employee.hire_date = datetime.fromisoformat(data['hire_date']) if data.get('hire_date') else employee.hire_date
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
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_rest.route('/rrhh/empleados/<int:id>', methods=['DELETE'])
def delete_employee(id):
    """Delete an employee"""
    try:
        employee = Employee.query.get_or_404(id)
        db.session.delete(employee)
        db.session.commit()
        return jsonify({'message': 'Employee deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------------
# BUSINESS UNITS ENDPOINT (helper for forms)
# -----------------------------------------------------------------------------
@api_rest.route('/business-units', methods=['GET'])
def get_business_units():
    """Get all business units"""
    try:
        units = BusinessUnit.query.all()
        return jsonify([{
            'id': u.id,
            'name': u.name,
            'description': u.description
        } for u in units])
    except Exception as e:
        return jsonify({'error': str(e)}), 500