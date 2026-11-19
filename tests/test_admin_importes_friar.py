"""Importes en Cta Cte Friar y errores sin texto técnico (hallazgo A-010 del Barrido A).

El alta con saldo «1000,00» (formato argentino) crea la cuenta con 1000,00. Un importe
inválido responde 400 con un mensaje en español y no crea nada. Ningún handler genérico
de administración, Tesorería ni Cta Cte Friar devuelve el texto de la excepción (PostgreSQL,
SQL, decimal). Datos sintéticos rotulados PROBE; base SQLite en memoria.
"""

from decimal import Decimal

import pytest

from blueprints import admin as admin_mod
from models import db
from models.gastos import Proveedor
from models.tesoreria import CuentaCorrienteFriar
from sesion_de_prueba import asegurar_usuario, marcar_sesion

MENSAJE_IMPORTE = "Ingresá un importe válido, por ejemplo 1.234,56"
MENSAJE_GENERICO = "No se pudo completar la operación. Intentá de nuevo."
RUTA_ADMIN = "/api/admin/tesoreria/cuenta_friar"
# Fragmentos que jamás deben llegar al navegador.
FRAGMENTOS_TECNICOS = ("psycopg2", "SQL", "invalid input syntax", "numeric", "decimal",
                       "Traceback", "InvalidOperation", "ConversionSyntax")


@pytest.fixture
def admin_cliente(app_seguridad):
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)
    return cliente


def _cuentas(app):
    with app.app_context():
        return db.session.query(CuentaCorrienteFriar).count()


# -----------------------------------------------------------------------------
# Parser es-AR de admin.py
# -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("1000,00", Decimal("1000.00")),
        ("1.000,50", Decimal("1000.50")),
        ("1000.00", Decimal("1000.00")),
        ("1.234", Decimal("1234.00")),
        ("1.234.567", Decimal("1234567.00")),
        ("1,234.56", Decimal("1234.56")),
        ("-1.000,00", Decimal("-1000.00")),
        ("0,5", Decimal("0.50")),
        ("12.5", Decimal("12.50")),
        (1000, Decimal("1000.00")),
        (1.5, Decimal("1.50")),
    ],
)
def test_parser_acepta_formatos_de_importe(texto, esperado):
    assert admin_mod.parsear_importe_es_ar(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    ["abc", "", "   ", None, True, "1,234", "1.23.456", "1000,000", "1.234,5.6",
     "1.2345", "1 000,00", "$ 1.000", 1.234, "20.000.000.000"],
)
def test_parser_rechaza_con_mensaje_en_espanol(texto):
    # 1.234 numérico (float) tiene tres decimales: se rechaza y no se redondea en silencio.
    with pytest.raises(ValueError) as info:
        admin_mod.parsear_importe_es_ar(texto)
    assert str(info.value) == MENSAJE_IMPORTE


def test_parser_no_devuelve_cero_en_silencio():
    for texto in ("abc", "", "  ", "x,y"):
        with pytest.raises(ValueError):
            admin_mod.parsear_importe_es_ar(texto)


# -----------------------------------------------------------------------------
# Alta y edición de la cuenta Friar desde la administración
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("saldo, esperado", [
    ("1000,00", Decimal("1000.00")),
    ("1.000,50", Decimal("1000.50")),
    ("1000.00", Decimal("1000.00")),
])
def test_alta_de_cuenta_friar_con_formato_argentino_crea_la_cuenta(admin_cliente, app_seguridad, saldo, esperado):
    respuesta = admin_cliente.post(RUTA_ADMIN, json={"saldo_inicial": saldo, "observaciones": "PROBE"})
    assert respuesta.status_code == 201, respuesta.get_data(as_text=True)
    assert respuesta.get_json()["success"] is True
    with app_seguridad.app_context():
        cuenta = db.session.get(CuentaCorrienteFriar, respuesta.get_json()["id"])
        assert cuenta.saldo_inicial == esperado


@pytest.mark.parametrize("saldo", ["abc", "", "   ", None, "1,234"])
def test_alta_con_importe_invalido_responde_400_y_no_crea_nada(admin_cliente, app_seguridad, saldo):
    respuesta = admin_cliente.post(RUTA_ADMIN, json={"saldo_inicial": saldo})
    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": MENSAJE_IMPORTE}
    assert _cuentas(app_seguridad) == 0


def test_alta_sin_saldo_inicial_responde_con_mensaje_de_importe(admin_cliente, app_seguridad):
    respuesta = admin_cliente.post(RUTA_ADMIN, json={"observaciones": "PROBE"})
    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": MENSAJE_IMPORTE}
    assert _cuentas(app_seguridad) == 0


def test_edicion_de_saldo_con_formato_argentino(admin_cliente, app_seguridad):
    creada = admin_cliente.post(RUTA_ADMIN, json={"saldo_inicial": "1000,00"})
    cuenta_id = creada.get_json()["id"]

    editada = admin_cliente.put(f"{RUTA_ADMIN}/{cuenta_id}", json={"saldo_inicial": "1.000,50"})
    assert editada.status_code == 200, editada.get_data(as_text=True)
    with app_seguridad.app_context():
        assert db.session.get(CuentaCorrienteFriar, cuenta_id).saldo_inicial == Decimal("1000.50")

    invalida = admin_cliente.put(f"{RUTA_ADMIN}/{cuenta_id}", json={"saldo_inicial": "abc"})
    assert invalida.status_code == 400
    assert invalida.get_json() == {"error": MENSAJE_IMPORTE}


# -----------------------------------------------------------------------------
# Handlers genéricos: sin texto de la excepción en la respuesta
# -----------------------------------------------------------------------------
def test_error_inesperado_de_base_no_llega_al_navegador(admin_cliente, monkeypatch):
    def falla(*_args, **_kwargs):
        raise Exception('(psycopg2.errors.InvalidTextRepresentation) invalid input syntax for type numeric: "1000,00"')

    monkeypatch.setattr(admin_mod, "get_or_create_friar_proveedor_id", falla)
    respuesta = admin_cliente.post(RUTA_ADMIN, json={"saldo_inicial": "1000.00"})
    assert respuesta.status_code == 500
    assert respuesta.get_json() == {"error": MENSAJE_GENERICO}
    cuerpo = respuesta.get_data(as_text=True)
    for fragmento in FRAGMENTOS_TECNICOS:
        assert fragmento not in cuerpo, fragmento


def test_cta_cte_friar_no_devuelve_el_texto_de_la_excepcion(app_seguridad):
    with app_seguridad.app_context():
        proveedor = Proveedor(nombre="PROBE Friar", activo=True)
        db.session.add(proveedor)
        db.session.commit()
        proveedor_id = proveedor.id
    asegurar_usuario(app_seguridad, 1, "PROBE-admin", "admin")
    cliente = app_seguridad.test_client()
    marcar_sesion(cliente, 1)

    respuesta = cliente.post(
        "/api/tesoreria/cta-cte-friar",
        json={"proveedor_id": proveedor_id, "saldo_inicial": "abc"},
    )
    assert respuesta.status_code == 500
    assert respuesta.get_json() == {"error": "No se pudo crear la cuenta. Revisá los datos e intentá de nuevo."}
    cuerpo = respuesta.get_data(as_text=True)
    for fragmento in FRAGMENTOS_TECNICOS:
        assert fragmento not in cuerpo, fragmento


def test_arqueo_con_importe_invalido_responde_mensaje_generico(admin_cliente):
    respuesta = admin_cliente.post(
        "/api/tesoreria/arqueos",
        json={"fecha": "2026-11-18", "turno": "mañana", "saldo_final": "abc", "saldo_inicial": "1"},
    )
    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"error": "Datos numéricos inválidos. Revisá los importes y la fecha."}
    for fragmento in FRAGMENTOS_TECNICOS:
        assert fragmento not in respuesta.get_data(as_text=True), fragmento
