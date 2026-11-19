"""Compras (D-4): PurchaseReceipt.order_id se guarda en la columna purchase_order_id.

En producción y en la cadena de migraciones la columna se llama purchase_order_id. El atributo
conserva el nombre order_id para no tocar el código que lo usa.
"""

from models import PurchaseReceipt


def test_el_atributo_order_id_usa_la_columna_purchase_order_id():
    tabla = PurchaseReceipt.__table__
    assert tabla.c.get("purchase_order_id") is not None
    assert tabla.c.get("order_id") is None
    assert PurchaseReceipt.order_id.property.columns[0].name == "purchase_order_id"
