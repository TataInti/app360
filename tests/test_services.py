import pytest
from unittest.mock import Mock
from services.product_service import ProductService
from models.core import Product


class TestProductService:
    def test_get_all_products(self):
        # Mock repository
        mock_repo = Mock()
        mock_repo.get_all.return_value = [
            Product(id=1, name="Product 1"),
            Product(id=2, name="Product 2")
        ]

        service = ProductService()
        service.repository = mock_repo

        products = service.get_all()
        assert len(products) == 2
        assert products[0].name == "Product 1"

    def test_create_product_success(self):
        mock_repo = Mock()
        mock_repo.get_by_sku.return_value = None
        mock_repo.create.return_value = Product(id=1, name="New Product", sku="NEW001")

        service = ProductService()
        service.repository = mock_repo

        product = service.create(name="New Product", sku="NEW001")
        assert product.name == "New Product"
        mock_repo.create.assert_called_once()

    def test_create_product_duplicate_sku(self):
        mock_repo = Mock()
        mock_repo.get_by_sku.return_value = Product(id=1, sku="EXISTING")

        service = ProductService()
        service.repository = mock_repo

        with pytest.raises(ValueError, match="SKU already exists"):
            service.create(name="New Product", sku="EXISTING")