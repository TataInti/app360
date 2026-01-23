import pytest
import json
from models import db
from models.core import User


class TestAuthAPI:
    def test_login_success(self, client, init_database):
        # Create test user
        user = User(username="testadmin")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

        # Test login
        response = client.post('/api/login', json={
            'username': 'testadmin',
            'password': 'testpass'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'user' in data

    def test_login_failure(self, client, init_database):
        response = client.post('/api/login', json={
            'username': 'wrong',
            'password': 'wrong'
        })
        assert response.status_code == 401


class TestProductsAPI:
    def test_get_products(self, client, init_database):
        # This would test the actual API endpoint
        # For now, just check the route exists
        response = client.get('/api/products')
        # Assuming the API is implemented
        assert response.status_code in [200, 401]  # 401 if not authenticated