import pytest
from models.core import User, Product, BusinessUnit


class TestUser:
    def test_password_hashing(self):
        user = User(username="testuser")
        user.set_password("password123")
        assert user.check_password("password123")
        assert not user.check_password("wrongpassword")

    def test_user_creation(self):
        user = User(username="testuser", role="manager", active=True)
        assert user.username == "testuser"
        assert user.role == "manager"
        assert user.active is True


class TestProduct:
    def test_product_creation(self):
        product = Product(
            name="Test Product",
            sku="TEST001",
            price=100.0,
            category="Test Category"
        )
        assert product.name == "Test Product"
        assert product.sku == "TEST001"
        assert product.price == 100.0


class TestBusinessUnit:
    def test_business_unit_creation(self):
        bu = BusinessUnit(name="Test Unit")
        assert bu.name == "Test Unit"