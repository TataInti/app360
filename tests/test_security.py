"""
Security Tests for APP360
Tests rate limiting, CSRF, JWT, and security headers
"""
import pytest
import json
import time
from models import db
from models.core import User


class TestSecurityHeaders:
    """Test security headers are present"""
    
    def test_x_frame_options_header(self, client, init_database):
        response = client.get('/api/health')
        assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    
    def test_x_content_type_options_header(self, client, init_database):
        response = client.get('/api/health')
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
    
    def test_x_xss_protection_header(self, client, init_database):
        response = client.get('/api/health')
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'
    
    def test_referrer_policy_header(self, client, init_database):
        response = client.get('/api/health')
        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    
    def test_content_security_policy_header(self, client, init_database):
        response = client.get('/api/health')
        csp = response.headers.get('Content-Security-Policy')
        assert csp is not None
        assert "default-src 'self'" in csp


class TestJWTAuthentication:
    """Test JWT token authentication"""
    
    def test_login_returns_tokens(self, client, init_database):
        # Create test user
        user = User(username="jwtuser", role="manager")
        user.set_password("testpass123")
        db.session.add(user)
        db.session.commit()
        
        # Login
        response = client.post('/api/login', json={
            'username': 'jwtuser',
            'password': 'testpass123'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'access_token' in data
        assert 'refresh_token' in data
        assert data['token_type'] == 'Bearer'
    
    def test_protected_endpoint_without_token(self, client, init_database):
        response = client.get('/api/me')
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_protected_endpoint_with_valid_token(self, client, init_database):
        # Create user and get token
        user = User(username="jwtuser2", role="manager")
        user.set_password("testpass123")
        db.session.add(user)
        db.session.commit()
        
        login_response = client.post('/api/login', json={
            'username': 'jwtuser2',
            'password': 'testpass123'
        })
        token = json.loads(login_response.data)['access_token']
        
        # Access protected endpoint
        response = client.get('/api/me', headers={
            'Authorization': f'Bearer {token}'
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['username'] == 'jwtuser2'
    
    def test_protected_endpoint_with_invalid_token(self, client, init_database):
        response = client.get('/api/me', headers={
            'Authorization': 'Bearer invalid-token'
        })
        assert response.status_code == 401
    
    def test_refresh_token(self, client, init_database):
        # Create user and get tokens
        user = User(username="jwtuser3", role="manager")
        user.set_password("testpass123")
        db.session.add(user)
        db.session.commit()
        
        login_response = client.post('/api/login', json={
            'username': 'jwtuser3',
            'password': 'testpass123'
        })
        refresh_token = json.loads(login_response.data)['refresh_token']
        
        # Use refresh token to get new access token
        response = client.post('/api/refresh', json={
            'refresh_token': refresh_token
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'access_token' in data


class TestLoginSecurity:
    """Test login security measures"""
    
    def test_login_with_missing_fields(self, client, init_database):
        response = client.post('/api/login', json={})
        assert response.status_code == 400
    
    def test_login_with_empty_password(self, client, init_database):
        response = client.post('/api/login', json={
            'username': 'test',
            'password': ''
        })
        assert response.status_code == 400
    
    def test_login_with_inactive_user(self, client, init_database):
        # Create inactive user
        user = User(username="inactive", role="manager", active=False)
        user.set_password("testpass123")
        db.session.add(user)
        db.session.commit()
        
        response = client.post('/api/login', json={
            'username': 'inactive',
            'password': 'testpass123'
        })
        assert response.status_code == 401


class TestInputValidation:
    """Test input validation and sanitization"""
    
    def test_sql_injection_in_login(self, client, init_database):
        """Test that SQL injection attempts are blocked"""
        response = client.post('/api/login', json={
            'username': "admin' OR '1'='1",
            'password': "password"
        })
        assert response.status_code == 401
    
    def test_xss_in_login(self, client, init_database):
        """Test that XSS attempts don't break the system"""
        response = client.post('/api/login', json={
            'username': "<script>alert('xss')</script>",
            'password': "password"
        })
        assert response.status_code == 401
