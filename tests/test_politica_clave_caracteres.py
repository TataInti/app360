"""Política de la clave nueva: caracteres de control y claves solo de espacios (baja 4).

Los mensajes van ligados al campo clave_nueva y nunca repiten la clave. Datos sintéticos
rotulados PROBE; SQLite en memoria.
"""

import pytest

from models import db
from models.core.user import User
from services.politica_clave import errores_clave_nueva
from sesion_de_prueba import marcar_sesion

ACTUAL = "PROBE-clave-actual-2026"
MSG_CONTROL = "La clave no puede tener caracteres de control."
MSG_ESPACIOS = "La clave no puede ser solo espacios."


@pytest.mark.parametrize(
    "clave",
    [
        "PROBE\x07clave-2026",  # BEL, en medio
        "\x00PROBE-clave-2026",  # NUL al inicio
        "PROBE-clave-2026\x7f",  # DEL
        "PROBE\tclave-2026",  # tabulación
        "PROBE\nclave-2026",  # salto de línea
        "\x1f" * 12,  # control, aunque tenga el largo mínimo
        "\x07",  # control y corta: gana el mensaje de control, no el de largo
    ],
)
def test_rechaza_caracteres_de_control_en_el_campo(clave):
    assert errores_clave_nueva(clave, clave, "ana", ACTUAL) == {"clave_nueva": MSG_CONTROL}


@pytest.mark.parametrize("clave", [" " * 12, " " * 40, "   ", "\u00a0" * 12])
def test_rechaza_claves_solo_de_espacios(clave):
    assert errores_clave_nueva(clave, clave, "ana", ACTUAL) == {"clave_nueva": MSG_ESPACIOS}


@pytest.mark.parametrize(
    "clave",
    [
        "  PROBE-clave-2026  ",  # espacios al inicio y al final: la clave es exacta
        "PROBE clave nueva 2026",  # espacios internos
        "contraseña-ñandú-2026",  # Unicode
        "clave-con-emoji-🔐-2026",  # emoji
    ],
)
def test_acepta_espacios_internos_unicode_y_emojis(clave):
    assert errores_clave_nueva(clave, clave, "ana", ACTUAL) == {}


def test_cambio_con_caracter_de_control_responde_400_y_no_cambia_la_clave(app_seguridad):
    app = app_seguridad
    with app.app_context():
        cuenta = User(username="PROBE-control-web", role="sales", active=True)
        db.session.add(cuenta)
        cuenta.set_password(ACTUAL)
        db.session.commit()
        uid = cuenta.id
    cliente = app.test_client()
    marcar_sesion(cliente, uid)

    clave = "PROBE-clave\x07nueva-2026"
    respuesta = cliente.post(
        "/cambiar-clave",
        data={"clave_actual": ACTUAL, "clave_nueva": clave, "repetir_clave": clave},
    )

    assert respuesta.status_code == 400
    html = respuesta.get_data(as_text=True)
    assert MSG_CONTROL in html
    assert clave not in html
    with app.app_context():
        assert db.session.get(User, uid).check_password(ACTUAL)
