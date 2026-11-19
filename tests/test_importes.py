"""Pruebas del parser único de importes (services/importes.py, corte D1 · D-1)."""

from decimal import Decimal, InvalidOperation

import pytest

from services.importes import (
    MAXIMO_NUMERIC_12_2,
    MENSAJE_IMPORTE_INVALIDO,
    ImporteInvalido,
    parse_importe,
)

# Los 8 casos del informe (A-001) y los ejemplos de la regla de negocio.
CASOS_VALIDOS = [
    ("1234,56", "1234.56"),
    ("1234.56", "1234.56"),
    ("1.234", "1234"),
    ("12.5", "12.5"),
    ("12,5", "12.5"),
    ("1.234,56", "1234.56"),
    ("1.234.567,89", "1234567.89"),
    ("1,234.56", "1234.56"),
    # Miles, decimales y límites.
    ("1.000", "1000"),
    ("12.345.678", "12345678"),
    ("999.999.999,99", "999999999.99"),
    ("0,50", "0.50"),
    ("0", "0"),
    ("100", "100"),
    ("1.234,5", "1234.5"),
    # Negativos (cada formulario decide si los admite).
    ("-1.234,56", "-1234.56"),
    ("+12,5", "12.5"),
    # Símbolo de moneda y espacios de los extremos.
    (" $ 1.234,56 ", "1234.56"),
    ("$1.234", "1234"),
]

CASOS_INVALIDOS = [
    "abc",
    "",
    "   ",
    None,
    "1234,",  # coma final sin decimales
    ",5",  # sin parte entera
    ".5",
    "1.",
    "1,2,3",  # varias comas: decimales ambiguos
    "1,234",  # tres decimales (se rechaza: no se redondea en silencio)
    "1.234,567",  # tres decimales
    "1.234,56.7",  # dos separadores decimales
    "1.23.456",  # grupos de miles que no son de tres dígitos
    "1.2345",  # 4 dígitos después del punto
    "1234.567",  # 4 dígitos antes de los miles
    "1.23,4",  # grupo de miles de dos dígitos
    "12 345",  # espacio interno
    "--1",
    "1-2",
    "12a",
    "$",
    "NaN",
    "inf",
    "1e3",
    True,
    False,
    float("nan"),
    float("inf"),
]


@pytest.mark.parametrize(("entrada", "esperado"), CASOS_VALIDOS)
def test_importes_validos_en_formato_es_ar(entrada, esperado):
    assert parse_importe(entrada) == Decimal(esperado)


@pytest.mark.parametrize("entrada", CASOS_INVALIDOS, ids=[repr(c) for c in CASOS_INVALIDOS])
def test_importes_ambiguos_o_no_numericos_se_rechazan(entrada):
    with pytest.raises(ImporteInvalido) as error:
        parse_importe(entrada)
    assert error.value.mensaje == MENSAJE_IMPORTE_INVALIDO


def test_el_mensaje_de_error_es_el_del_formulario_sin_prefijo_tecnico():
    assert MENSAJE_IMPORTE_INVALIDO == "Ingresá un importe válido, por ejemplo 1.234,56"
    assert "Error" not in MENSAJE_IMPORTE_INVALIDO


def test_el_rechazo_nunca_devuelve_cero_en_silencio():
    for entrada in ("abc", "1.234,56.7", "1,234", ""):
        with pytest.raises(ImporteInvalido):
            parse_importe(entrada)


def test_importe_invalido_se_captura_con_except_valueerror_y_invalidoperation():
    with pytest.raises(ValueError):
        parse_importe("abc")
    with pytest.raises(InvalidOperation):
        parse_importe("abc")


def test_numeros_nativos_de_json_se_toman_tal_cual():
    assert parse_importe(1234.5) == Decimal("1234.5")
    assert parse_importe(0.1) == Decimal("0.1")
    assert parse_importe(7) == Decimal("7")
    assert parse_importe(Decimal("1.50")) == Decimal("1.50")


def test_limite_de_columna_numeric_12_2():
    assert parse_importe("9.999.999.999,99", maximo=MAXIMO_NUMERIC_12_2) == Decimal("9999999999.99")
    with pytest.raises(ImporteInvalido):
        parse_importe("10.000.000.000,00", maximo=MAXIMO_NUMERIC_12_2)
    with pytest.raises(ImporteInvalido):
        parse_importe("-10.000.000.000", maximo=MAXIMO_NUMERIC_12_2)


def test_cero_y_negativos_pasan_el_parser_y_los_valida_cada_formulario():
    assert parse_importe("0,00") == Decimal("0")
    assert parse_importe("-0,01") == Decimal("-0.01")
