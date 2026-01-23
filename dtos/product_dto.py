from dataclasses import dataclass
from typing import Optional


@dataclass
class ProductDTO:
    id: Optional[int] = None
    sku: Optional[str] = None
    name: str = ""
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    stock_quantity: int = 0
    min_stock_level: int = 0
    business_unit_id: Optional[int] = None
    location_id: Optional[int] = None

    @classmethod
    def from_model(cls, product):
        return cls(
            id=product.id,
            sku=product.sku,
            name=product.name,
            description=product.description,
            price=product.price,
            category=product.category,
            stock_quantity=product.stock_quantity,
            min_stock_level=product.min_stock_level,
            business_unit_id=product.business_unit_id,
            location_id=product.location_id
        )