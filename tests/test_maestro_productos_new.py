"""GET /new del maestro de productos redirige al formulario real (defecto P2).

El BaseCRUD registraba un GET genérico que renderizaba products_form.html, plantilla que no
existe: respondía 500. Ahora GET /new redirige a /products/new, que tiene su formulario y la
misma guardia de módulo. El POST de /new no cambia. Datos sintéticos rotulados PROBE.
"""

from urllib.parse import urlsplit

from sesion_de_prueba import asegurar_usuario, marcar_sesion


def _cliente(app, usuario_id, usuario, rol):
    asegurar_usuario(app, usuario_id, usuario, rol)
    cliente = app.test_client()
    marcar_sesion(cliente, usuario_id)
    return cliente


def test_get_new_redirige_al_formulario_de_productos(app_seguridad):
    cliente = _cliente(app_seguridad, 1, "PROBE-admin", "admin")

    respuesta = cliente.get("/new")

    assert respuesta.status_code == 302
    assert urlsplit(respuesta.location).path == "/products/new"
    assert cliente.get("/products/new").status_code == 200


def test_get_new_conserva_la_guardia_del_modulo(app_seguridad):
    """Rol sales, sin el módulo products: /new responde igual que /products/new."""
    cliente = _cliente(app_seguridad, 3, "PROBE-ventas", "sales")

    en_new = cliente.get("/new")
    en_products = cliente.get("/products/new")

    assert en_new.status_code == en_products.status_code
    assert en_new.status_code != 200
    assert en_new.location == en_products.location
