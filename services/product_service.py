from models.core import Product
from repositories.base_repository import BaseRepository
from dtos.product_dto import ProductDTO


class ProductRepository(BaseRepository):
    def __init__(self):
        super().__init__(Product)

    def get_by_sku(self, sku):
        return self.model_class.query.filter_by(sku=sku).first()

    def get_by_category(self, category):
        return self.model_class.query.filter_by(category=category).all()


class ProductService:
    def __init__(self):
        self.repository = ProductRepository()

    def get_all(self):
        products = self.repository.get_all()
        return [ProductDTO.from_model(p) for p in products]

    def get_by_id(self, product_id):
        product = self.repository.get_by_id(product_id)
        return ProductDTO.from_model(product) if product else None

    def create(self, **kwargs):
        # Validate SKU uniqueness
        if kwargs.get('sku') and self.repository.get_by_sku(kwargs['sku']):
            raise ValueError("SKU already exists")
        product = self.repository.create(**kwargs)
        return ProductDTO.from_model(product)

    def update(self, product_id, **kwargs):
        product = self.repository.update(product_id, **kwargs)
        return ProductDTO.from_model(product) if product else None

    def delete(self, product_id):
        return self.repository.delete(product_id)