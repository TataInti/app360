"""El modelo User exige un rol explícito (hallazgo R-08).

Antes, role tenía default "manager" (administración total): un alta sin rol
recibía acceso completo. Ahora la creación sin rol falla con un error claro.
"""

import pytest

from models import db
from models.core.user import User


def test_crear_usuario_sin_rol_falla_con_error_claro(app_seguridad):
    with pytest.raises(ValueError, match="rol explícito"):
        User(username="PROBE-sin-rol", active=True)


@pytest.mark.parametrize("rol", [None, ""])
def test_rol_vacio_en_el_constructor_falla(app_seguridad, rol):
    with pytest.raises(ValueError):
        User(username="PROBE-rol-vacio", role=rol, active=True)


def test_quitar_el_rol_despues_falla(app_seguridad):
    usuario = User(username="PROBE-rol", role="sales", active=True)
    with pytest.raises(ValueError):
        usuario.role = None


def test_usuario_con_rol_explicito_se_guarda(app_seguridad):
    usuario = User(username="PROBE-ventas", role="sales", active=True)
    usuario.set_password("PROBE-clave")
    db.session.add(usuario)
    db.session.commit()
    recuperado = User.query.filter_by(username="PROBE-ventas").first()
    assert recuperado.role == "sales"
    assert recuperado.check_password("PROBE-clave")


def test_columna_role_sin_default_en_el_modelo():
    columna = User.__table__.c.role
    assert columna.nullable is False
    assert columna.default is None
    assert columna.server_default is None
