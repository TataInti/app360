"""Regresiones de Pulido final 1: correcciones de presentacion de la revision visual (H02, H04, H05, H06, H07, H08, H14, H29)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def leer(ruta):
    return (ROOT / ruta).read_text(encoding="utf-8")


def cuerpo_de_regla(fuente, selector):
    match = re.search(re.escape(selector) + r"\s*\{([^{}]*)\}", fuente, flags=re.S)
    assert match, f"Falta la regla: {selector}"
    return match.group(1)


def test_h02_hover_del_primario_de_comercial_usa_el_token_de_accion():
    css = leer("static/css/comercial_paneles.css")
    cuerpo = cuerpo_de_regla(css, ".com-panel button.com-primary:hover")
    assert "background:var(--color-action-hover)" in cuerpo
    assert "#" not in cuerpo


def test_h04_total_al_pie_del_scroll_table_queda_sticky_con_tokens():
    base = leer("templates/base.html")
    cuerpo = cuerpo_de_regla(base, ".scroll-table tfoot > tr > *")
    assert re.search(r"position:\s*sticky", cuerpo)
    assert re.search(r"bottom:\s*0", cuerpo)
    assert "var(--color-surface-subtle)" in cuerpo
    assert "var(--color-border)" in cuerpo
    assert "#" not in cuerpo


def test_h04_subtotal_de_movimientos_en_una_linea_bajo_monto_sin_azul_bootstrap():
    html = leer("templates/tesoreria_movimientos.html")
    assert '<th class="text-end">Monto</th>' in html
    assert '<td id="subtotalMonto" class="text-end app-table__numeric"></td>' in html
    tfoot = html[html.index('<tfoot id="tfootMovimientos"'):].split("</tfoot>")[0]
    assert "table-light" not in tfoot
    assert '<span class="text-primary">' not in html
    assert html.count('text-nowrap">') >= 3


def test_h29_botones_de_anulacion_con_aria_label_igual_al_title():
    html = leer("templates/tesoreria_movimientos.html")
    for texto in ("Solicitar anulación", "Autorizar", "Rechazar"):
        assert f'title="{texto}" aria-label="{texto}"' in html


def test_h06_selects_de_gastos_con_control_del_sistema_y_ids_intactos():
    html = leer("templates/gastos_panel.html")
    for id_ in ("selCategoria", "selProveedor", "selInstrumento"):
        match = re.search(rf'<select id="{id_}"([^>]*)>', html)
        assert match, id_
        assert "app-field__control" in match.group(1)


def test_h05_actualizar_del_lead_sin_columna_centrada():
    html = leer("templates/lead_detail.html")
    assert "col-xl-10 mx-auto" not in html
    assert '<section class="mb-4" aria-labelledby="leadUpdateTitle">' in html


def test_h07_h1_de_criterio_con_peso_700():
    html = leer("templates/criterio_clientes.html")
    assert '<h1 class="h4 mb-1 fw-bold">Criterio de clientes</h1>' in html


def test_h08_encabezados_numericos_de_salon_a_la_derecha():
    js = leer("static/js/tablero_salon.js")
    assert "const encabezadosNumericos = ['Importe', 'Cajas', 'Kilos'];" in js
    assert "th.className = 'salon-number-cell'" in js


def test_h14_proveedor_manual_en_fila_propia_y_ids_intactos():
    html = leer("templates/compras_orden_nueva.html")
    assert 'ingresalo manualmente abajo.</small>\n            </div>' in html
    assert (
        '<div class="app-field app-form-grid__full">\n'
        '                <label class="app-field__label" for="supplier_text">Proveedor (manual)</label>\n'
        '                <input id="supplier_text" type="text" name="supplier_text"'
    ) in html
    assert 'id="supplier_id"' in html
