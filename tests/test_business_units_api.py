"""GET /api/business-units con 0, 1 y 2 unidades (defecto P1 de la verificación del PR #19).

El listado leía u.description, que BusinessUnit no tiene: con al menos una unidad respondía
500. La respuesta trae id y name por unidad. Datos sintéticos rotulados PROBE; SQLite en memoria.
"""

import pytest

from models import BusinessUnit, db
from security import generate_access_token
from sesion_de_prueba import asegurar_usuario

RUTA = "/api/business-units"


@pytest.fixture
def cabecera(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    token = generate_access_token(1, "PROBE-admin", "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("cantidad", [0, 1, 2])
def test_listado_responde_200_con_id_y_name(app_seguridad, cabecera, cantidad):
    with app_seguridad.app_context():
        for indice in range(cantidad):
            db.session.add(BusinessUnit(name=f"PROBE-unidad-{indice}"))
        db.session.commit()

    respuesta = app_seguridad.test_client().get(RUTA, headers=cabecera)

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["total"] == cantidad
    assert len(datos["items"]) == cantidad
    assert all(set(item) == {"id", "name"} for item in datos["items"])
    assert sorted(item["name"] for item in datos["items"]) == sorted(
        f"PROBE-unidad-{indice}" for indice in range(cantidad)
    )
