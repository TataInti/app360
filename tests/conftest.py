import pytest
import os
from app import create_app
from models import db


@pytest.fixture
def app():
    """Create and configure a test app instance."""
    app = create_app()
    app.config['TESTING'] = True
    # Override database URI for testing BEFORE loading other config
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
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

    # Login to get token
    response = client.post('/api/login', json={
        'username': 'testadmin',
        'password': 'testpass'
    })
    data = response.get_json()
    token = data['token']

    return {'Authorization': f'Bearer {token}'}