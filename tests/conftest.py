import pytest
import os

# Configurar variables de entorno ANTES de importar la app
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing-only'
os.environ['ADMIN_PASSWORD'] = 'testpassword123'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SERVER_NAME'] = 'localhost'
os.environ['SESSION_COOKIE_SECURE'] = 'False'
os.environ['REMEMBER_COOKIE_SECURE'] = 'False'
os.environ['RATELIMIT_ENABLED'] = 'False'
os.environ['WTF_CSRF_ENABLED'] = 'False'

from app import create_app
from models import db


@pytest.fixture
def app():
    """Create and configure a test app instance."""
    app = create_app()
    app.config['TESTING'] = True
    # Override database URI for testing
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SERVER_NAME'] = None  # Permite rutas sin dominio
    app.config['RATELIMIT_ENABLED'] = False
    app.config['WTF_CSRF_ENABLED'] = False
    
    return app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def init_database(app):
    """Initialize the database."""
    with app.app_context():
        db.create_all()
        yield db
        db.drop_all()


@pytest.fixture
def auth_headers(client, init_database):
    """Create authenticated headers for testing."""
    from models.core import User

    # Check if test user already exists
    user = User.query.filter_by(username="testadmin").first()
    if not user:
        # Create test user
        user = User(username="testadmin", role="manager")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

    # Login usando session (la API no usa JWT tokens)
    response = client.post('/api/login', json={
        'username': 'testadmin',
        'password': 'testpass'
    })
    data = response.get_json()
    # La API usa sesiones, no tokens JWT
    return {'Content-Type': 'application/json'}