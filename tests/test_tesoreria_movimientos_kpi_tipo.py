"""Tesorería › Movimientos: tarjetas de totales restituidas y color franco de Ingreso / Egreso.

Pruebas baratas de regresión, sin base de datos: marcado y fórmula de las tres tarjetas, alcance
(D4 sigue vigente en el resto de las pantallas), selectores de app-tipo, contraste medido de los
tokens y escape de tipoHtml / montoHtml / claseFila ejecutado con Node.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or ""
MOVIMIENTOS = ROOT / "templates" / "tesoreria_movimientos.html"
PANEL = ROOT / "templates" / "tesoreria_panel.html"
ARQUEOS = ROOT / "templates" / "tesoreria_arqueos.html"
BASE = ROOT / "templates" / "base.html"
FORMS_JS = ROOT / "static" / "js" / "tesoreria_forms.js"
COMPONENTES_CSS = ROOT / "static" / "css" / "app_components.css"


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _funcion(fuente: str, firma: str, hasta: str) -> str:
    inicio = fuente.index(firma)
    return fuente[inicio:fuente.index(hasta, inicio)]


# ---------------------------------------------------------------- Parte 1: tarjetas de totales

def test_movimientos_restituye_las_tres_tarjetas_con_los_ids_y_clases_de_ayer():
    html = _texto(MOVIMIENTOS)
    assert html.count('<div class="kpi-grid">') == 1
    assert '<div class="kpi-card accent-green"><span class="kpi-label">Total Ingresos</span>'\
        '<span class="kpi-value" id="totalIngresos">$0</span></div>' in html
    assert '<div class="kpi-card accent-red"><span class="kpi-label">Total Egresos</span>'\
        '<span class="kpi-value" id="totalEgresos">$0</span></div>' in html
    assert '<div class="kpi-card accent-blue"><span class="kpi-label">Balance Neto</span>'\
        '<span class="kpi-value" id="balanceNeto">$0</span></div>' in html
    for id_tarjeta in ("totalIngresos", "totalEgresos", "balanceNeto"):
        assert html.count(f'id="{id_tarjeta}"') == 1, id_tarjeta


def test_tarjetas_van_entre_el_filtro_y_el_grafico_por_instrumento():
    html = _texto(MOVIMIENTOS)
    assert html.index('id="tipoFiltro"') < html.index('<div class="kpi-grid">') < html.index('id="movimientosChart"')


def test_cargar_movimientos_asigna_las_tres_tarjetas_con_el_formato_de_ayer():
    funcion = _funcion(_texto(MOVIMIENTOS), "async function cargarMovimientos()", "async function descargarExcel")
    asignaciones = [
        "document.getElementById('totalIngresos').textContent = '$' + ingresos.toLocaleString('es-AR', {maximumFractionDigits:0});",
        "document.getElementById('totalEgresos').textContent = '$' + egresos.toLocaleString('es-AR', {maximumFractionDigits:0});",
        "document.getElementById('balanceNeto').textContent = '$' + (ingresos - egresos).toLocaleString('es-AR', {maximumFractionDigits:0});",
    ]
    posiciones = []
    for linea in asignaciones:
        assert funcion.count(linea) == 1, linea
        posiciones.append(funcion.index(linea))
    # Suma sobre la lista filtrada (salta anulados), luego las tarjetas y, después, el armado de la tabla.
    assert funcion.index("let ingresos = 0, egresos = 0;") < funcion.index("if (m.estado === 'anulado') return;") < posiciones[0]
    assert posiciones == sorted(posiciones)
    assert posiciones[-1] < funcion.index("const tbody = document.getElementById('tablaMovimientos');")


def test_las_tarjetas_no_se_restituyen_en_panel_ni_arqueos():
    # D4 sigue vigente en las demás pantallas: el panel tiene sus propias tarjetas (Saldo, Ingresos Hoy, Egresos Hoy, Diferencia).
    for ruta in (PANEL, ARQUEOS):
        html = _texto(ruta)
        for id_tarjeta in ("totalIngresos", "totalEgresos", "balanceNeto"):
            assert f'id="{id_tarjeta}"' not in html, (ruta.name, id_tarjeta)


# ---------------------------------------------------------------- Parte 2: color franco Ingreso / Egreso

def test_componente_app_tipo_define_chip_monto_y_fila_con_tokens():
    css = _texto(COMPONENTES_CSS)
    for selector in (
        ".app-tipo", ".app-tipo--ingreso", ".app-tipo--egreso",
        ".app-tipo__monto", ".app-tipo__monto--ingreso", ".app-tipo__monto--egreso",
        ".app-tipo-fila--ingreso", ".app-tipo-fila--egreso",
        ".app-tipo-fila--anulado .app-tipo", ".app-tipo-fila--anulado .app-tipo__monto",
    ):
        assert re.search(re.escape(selector) + r"\s*\{", css), selector


def test_las_pantallas_usan_las_funciones_compartidas_de_tipo_y_monto():
    movimientos = _texto(MOVIMIENTOS)
    panel = _texto(PANEL)
    assert "${TesoreriaForms.montoHtml(m.tipo, m.monto, decimalesMov)}" in movimientos
    assert "${TesoreriaForms.tipoHtml(m.tipo)}" in movimientos
    assert "class=\"${TesoreriaForms.claseFila(m.tipo)}\"" in panel
    assert "${TesoreriaForms.montoHtml(m.tipo, m.monto, decimales)}" in panel
    assert "${TesoreriaForms.tipoHtml(m.tipo)}" in panel
    # El estado de la fila (Activo, Anulado, Pend. anulación) no cambia: sigue con estadoHtml.
    assert "TesoreriaForms.estadoHtml(m.estado)" in movimientos


def _tokens_de_root(html: str) -> dict[str, str]:
    bloque = re.search(r":root\s*\{([^{}]*)\}", html, re.S)
    assert bloque, "base.html debe definir :root"
    return {nombre: valor.lower() for nombre, valor in re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", bloque.group(1))}


def _luminancia(hex_color: str) -> float:
    def canal(valor: int) -> float:
        c = valor / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def _contraste(texto: str, fondo: str) -> float:
    claro, oscuro = sorted((_luminancia(texto), _luminancia(fondo)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def test_texto_de_ingreso_y_egreso_supera_4_5_a_1_en_su_fondo_suave_y_en_blanco():
    tokens = _tokens_de_root(_texto(BASE))
    tinta_ingreso = tokens["--color-positive-ink"]
    tinta_egreso = tokens["--state-error-ink"]
    assert _contraste(tinta_ingreso, tokens["--color-positive-soft"]) >= 4.5
    assert _contraste(tinta_egreso, tokens["--color-negative-soft"]) >= 4.5
    # El monto va sobre fondo blanco con el mismo color de texto.
    assert _contraste(tinta_ingreso, "#ffffff") >= 4.5
    assert _contraste(tinta_egreso, "#ffffff") >= 4.5


def test_borde_de_fila_usa_el_verde_y_el_rojo_de_los_tokens_de_acento():
    css = _texto(COMPONENTES_CSS)
    tokens = _tokens_de_root(_texto(BASE))
    assert "border-left: 3px solid var(--color-positive);" in css
    assert "border-left: 3px solid var(--color-negative);" in css
    # Borde no textual: 3:1 mínimo contra el blanco.
    assert _contraste(tokens["--color-positive"], "#ffffff") >= 3.0
    assert _contraste(tokens["--color-negative"], "#ffffff") >= 3.0


_NODE_TIPO_MONTO = r"""
const assert = require('node:assert/strict');
const path = require('node:path');
global.window = {};
require(path.join(process.cwd(), 'static/js/escape_html.js'));
global.escapeHtml = window.escapeHtml;
require(path.join(process.cwd(), 'static/js/app_format.js'));
require(path.join(process.cwd(), 'static/js/tesoreria_forms.js'));
const F = window.TesoreriaForms;

assert.equal(F.tipoHtml('ingreso'), '<span class="app-tipo app-tipo--ingreso">Ingreso</span>');
assert.equal(F.tipoHtml('egreso'), '<span class="app-tipo app-tipo--egreso">Egreso</span>');
assert.equal(F.tipoHtml(null), '<span class="app-tipo">\u2014</span>');

const hostil = '<img src=x onerror="alert(1)">&\'';
for (const salida of [F.tipoHtml(hostil), F.montoHtml(hostil, 5, 0), F.claseFila(hostil)]) {
  assert.ok(!salida.includes('<img'), salida);
}
assert.ok(F.tipoHtml(hostil).includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;&#39;'));
assert.equal(F.montoHtml(hostil, 5, 0), '<span class="app-tipo__monto">$ 5</span>');

assert.equal(F.montoHtml('ingreso', 1500, 2), '<span class="app-tipo__monto app-tipo__monto--ingreso">+ $ 1.500,00</span>');
assert.equal(F.montoHtml('egreso', 120, 2), '<span class="app-tipo__monto app-tipo__monto--egreso">\u2212 $ 120,00</span>');
assert.equal(F.montoHtml('egreso', 120, 0), '<span class="app-tipo__monto app-tipo__monto--egreso">\u2212 $ 120</span>');
assert.equal(F.montoHtml('ingreso', 1234.5, 2), '<span class="app-tipo__monto app-tipo__monto--ingreso">+ $ 1.234,50</span>');

assert.equal(F.claseFila('ingreso'), 'app-tipo-fila app-tipo-fila--ingreso');
assert.equal(F.claseFila('egreso'), 'app-tipo-fila app-tipo-fila--egreso');
assert.equal(F.claseFila('otro'), '');
process.stdout.write('Chip, monto y fila: OK\n');
"""


@pytest.mark.skipif(not NODE, reason="Node.js no está disponible en PATH; no se pueden ejecutar las pruebas JS.")
def test_tipo_y_monto_escapan_su_entrada_y_fijan_el_signo_con_node():
    resultado = subprocess.run(
        [NODE, "-e", _NODE_TIPO_MONTO],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
