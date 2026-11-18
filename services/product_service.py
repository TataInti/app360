from models.core import Product
from repositories.base_repository import BaseRepository
from dtos.product_dto import ProductDTO


class ProductRepository(BaseRepository):
    # Campos que el formulario y la API de productos pueden asignar. stock_quantity
    # queda fuera: el stock se gestiona en StockLevel y ningún formulario lo envía.
    ALLOWED_FIELDS = frozenset({
        "sku",
        "name",
        "description",
        "price",
        "category",
        "min_stock_level",
        "business_unit_id",
        "location_id",
    })

    def __init__(self):
        super().__init__(Product)

    def get_by_sku(self, sku):
        return self.model_class.query.filter_by(sku=sku).first()

    def get_by_category(self, category):
        return self.model_class.query.filter_by(category=category).all()


class ProductService:
    # Lista blanca por entidad: la misma que aplica el repositorio antes de guardar.
    ALLOWED_FIELDS = ProductRepository.ALLOWED_FIELDS

    def __init__(self):
        self.repository = ProductRepository()

    def get_all(self):
        products = self.repository.get_all()
        return [ProductDTO.from_model(p) for p in products]

    def get_by_id(self, product_id):
        product = self.repository.get_by_id(product_id)
        return ProductDTO.from_model(product) if product else None

    def create(self, **kwargs):
        datos = self.repository.filtrar_campos(kwargs)
        # Validate SKU uniqueness
        if datos.get('sku') and self.repository.get_by_sku(datos['sku']):
            raise ValueError("SKU already exists")
        product = self.repository.create(**datos)
        return ProductDTO.from_model(product)

    def update(self, product_id, /, **kwargs):
        # Posicional-only: un campo 'product_id' de un formulario no debe chocar con él.
        product = self.repository.update(product_id, **kwargs)
        return ProductDTO.from_model(product) if product else None

    def delete(self, product_id):
        return self.repository.delete(product_id)
