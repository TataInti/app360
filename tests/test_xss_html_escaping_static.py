"""Static guard for data interpolated into App360 HTML strings.

All values must pass through escapeHtml/esc. The small explicit exception map below
covers HTML fragments, not raw user values: each fragment is either constant markup,
rendered by a helper that escapes its fields, or assembled from already-escaped rows.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT = re.compile(r"\binnerHTML\s*(?:\+=|=(?!=))")

# SAFE HTML fragments (each exception is documented at its point of use).
SAFE_HTML_EXCEPTIONS = {
    # Maestros
    # Compras-ventas
    # Tesorería
    "templates/cta_cte_friar.html": {
        "isAdmin ?": "The nested button is fixed markup; its numeric record id is escaped.",
    },
    "templates/tesoreria_arqueos.html": {
        "acciones": "Buttons are fixed markup with numeric ids escaped before interpolation.",
        "cambios": "compararCambios escapes every value and inserts only fixed strong/br markup.",
        "difClass": "CSS class is selected from fixed numeric sign branches.",
        "logs.map(": "Each audit row encodes time/user/justification; the change fragment is escaped.",
        "TesoreriaForms.celdaDiferenciaHtml(a.diferencia, decimales)": "Returns the amount escaped by importe plus fixed status markup from a numeric sign; no record text.",
        "TesoreriaForms.celdaDiferenciaHtml(d.diferencia, decimales)": "Returns the amount escaped by importe plus fixed status markup from a numeric sign; no record text.",
    },
    "templates/tesoreria_movimientos.html": {
        "acciones": "Buttons are fixed markup with numeric ids escaped before interpolation.",
        "destinoCategoria": "The fragment escapes category/nature/effect values before insertion.",
        "estadoBadge": "TesoreriaForms.estadoHtml returns fixed status markup (Activo / Anulado / Pend. anulación) selected by enum; no record text.",
        "TesoreriaForms.tipoHtml(m.tipo)": "Returns a fixed chip (Ingreso / Egreso) or the escaped fallback label; no record text.",
        "TesoreriaForms.montoHtml(m.tipo, m.monto, decimalesMov)": "Returns the amount escaped by importe with a fixed sign and class chosen by the tipo enum; no record text.",
        "TesoreriaForms.claseFila(m.tipo)": "Returns one of two fixed row class names selected by the tipo enum, or an empty string; no record text.",
        "rowClass": "Only fixed class text selected by the movement status or tipo enums is inserted.",
    },
    "templates/tesoreria_panel.html": {
        "a.diferencia < 0 ?": "The conditional selects one of three fixed CSS class names.",
        "m.tipo === 'ingreso' ? '<span": "The conditional returns fixed status badge markup.",
        "TesoreriaForms.tipoHtml(m.tipo)": "Returns a fixed chip (Ingreso / Egreso) or the escaped fallback label; no record text.",
        "TesoreriaForms.montoHtml(m.tipo, m.monto, decimales)": "Returns the amount escaped by importe with a fixed sign and class chosen by the tipo enum; no record text.",
        "TesoreriaForms.claseFila(m.tipo)": "Returns one of two fixed row class names selected by the tipo enum, or an empty string; no record text.",
        "TesoreriaForms.celdaDiferenciaHtml(a.diferencia, decimales)": "Returns the amount escaped by importe plus fixed status markup from a numeric sign; no record text.",
    },

    # RRHH
    "templates/rrhh_adelantos.html": {
        "!a.aprobado ?": "The nested approve button is fixed markup with an escaped numeric id.",
        "estadoBadge": "The fragment contains only fixed status badges selected by boolean state.",
    },
    "templates/rrhh_ausentismo.html": {
        "badgeEstado(r)": "Returns one of fixed status badges; it interpolates no record text.",
        "canJustify ?": "The nested button is fixed markup with an escaped numeric id.",
        "color": "A CSS class selected only from fixed enum branches in verDetalleEmpleado.",
    },
    "templates/rrhh_liquidaciones.html": {
        "detalleLiquidacion(": "The helper escapes numeric counts and inserts only fixed <br> markup.",
    },
    "templates/rrhh_panel.html": {
        "badgeEstadoAdelanto(": "The helper returns only fixed badge markup selected by boolean state.",
        "badgeTipoAdelanto(": "The helper returns fixed badge markup and escapes the unknown type fallback.",
        "e.is_active": "The conditional branches are fixed active/inactive badge markup.",
    },

    # CRM
    # Paneles de lectura
    # Admin
    "templates/admin/admin_modulo.html": {
        "buildSelectOptions(": "The helper escapes each option value and label before returning markup.",
        "field === 'incluye_resultado' ?": "Both branches are fixed literal markup, not API data.",
        "inactiveNote": "This variable contains only a fixed '(inactivo)' span selected by a boolean.",
    },

    # Objetivos
    "static/js/objetivos_comerciales.js": {
        "rows": "Legacy rows are built field-by-field with escapeHtml before insertion.",
    },

    # SabioGo
    "templates/sabiogo_admin.html": {
        "badge": "The value is a fixed success/warning badge selected by the boolean mapeado.",
        "cell": "Coverage-cell markup is assembled from escaped counts, ids, and missing-day labels.",
    },
}


def _skip_quoted(source: str, start: int) -> int:
    quote = source[start]
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        else:
            index += 1
    return len(source)


def _skip_comment(source: str, start: int) -> int:
    if source.startswith("//", start):
        end = source.find("\n", start + 2)
        return len(source) if end < 0 else end + 1
    if source.startswith("/*", start):
        end = source.find("*/", start + 2)
        return len(source) if end < 0 else end + 2
    return start


def _expression_end(source: str, start: int) -> int:
    """Return the index of the closing brace for a ${...} expression."""
    depth = 0
    index = start
    while index < len(source):
        comment_end = _skip_comment(source, index)
        if comment_end != index:
            index = comment_end
            continue
        char = source[index]
        if char in "'\"":
            index = _skip_quoted(source, index)
            continue
        if char == "`":
            index, _ = _template_end(source, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if depth == 0:
                return index
            depth -= 1
        index += 1
    return len(source)


def _template_end(source: str, start: int):
    """Return template end and interpolation expressions, including nested templates."""
    expressions = []
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
            continue
        if source[index] == "`":
            return index + 1, expressions
        if source.startswith("${", index):
            end = _expression_end(source, index + 2)
            expression = source[index + 2:end]
            expressions.append(expression)
            # A fully escaped outer expression is the HTML sink boundary; nested templates
            # inside it format data (for example a date) and are not HTML interpolation sinks.
            if not re.match(r"^(?:escapeHtml|esc)\s*\(", expression.strip()):
                expressions.extend(_all_template_interpolations(expression))
            index = min(end + 1, len(source))
            continue
        index += 1
    return len(source), expressions


def _all_template_interpolations(source: str):
    expressions = []
    index = 0
    while index < len(source):
        comment_end = _skip_comment(source, index)
        if comment_end != index:
            index = comment_end
            continue
        char = source[index]
        if char in "'\"":
            index = _skip_quoted(source, index)
            continue
        if char == "`":
            index, nested = _template_end(source, index)
            expressions.extend(nested)
            continue
        index += 1
    return expressions


def _rhs_end(source: str, start: int) -> int:
    paren = bracket = brace = 0
    index = start
    while index < len(source):
        comment_end = _skip_comment(source, index)
        if comment_end != index:
            index = comment_end
            continue
        char = source[index]
        if char in "'\"":
            index = _skip_quoted(source, index)
            continue
        if char == "`":
            index, _ = _template_end(source, index)
            continue
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "{":
            brace += 1
        elif char == "}":
            if paren == bracket == brace == 0:
                return index
            brace = max(0, brace - 1)
        elif char == ";" and paren == bracket == brace == 0:
            return index
        index += 1
    return len(source)


def _exception_for(path: str, expression: str):
    expression = expression.strip()
    for prefix, reason in SAFE_HTML_EXCEPTIONS.get(path, {}).items():
        if expression == prefix or expression.startswith(prefix):
            return reason
    return None


def _unescaped_interpolations(path: str, source: str):
    unsafe = []
    for match in ASSIGNMENT.finditer(source):
        start = match.end()
        end = _rhs_end(source, start)
        rhs = source[start:end]
        for expression in _all_template_interpolations(rhs):
            value = expression.strip()
            if re.match(r"^(?:escapeHtml|esc)\s*\(", value):
                continue
            if _exception_for(path, value):
                continue
            unsafe.append(value)
    return unsafe


def test_every_innerhtml_interpolation_is_escaped_or_explicitly_safe():
    files = sorted((ROOT / "templates").rglob("*.html")) + sorted((ROOT / "static/js").rglob("*.js"))
    unsafe = []
    for file_path in files:
        relative = file_path.relative_to(ROOT).as_posix()
        source = file_path.read_text(encoding="utf-8")
        unsafe.extend(f"{relative}: {expr}" for expr in _unescaped_interpolations(relative, source))
    assert not unsafe, "Unescaped HTML interpolation(s):\n" + "\n".join(unsafe)


def test_static_checker_detects_unescaped_innerhtml_payload():
    source = 'row.innerHTML = `<div>${comment}</div>`;'
    assert _unescaped_interpolations("templates/probe.html", source) == ["comment"]


def test_admin_accesos_keeps_api_text_out_of_html_sinks():
    """Accesos renders usernames/errors from the API through textContent, not HTML strings."""
    source = (ROOT / "static" / "js" / "admin_accesos.js").read_text(encoding="utf-8")
    assert "innerHTML" not in source
    assert "textContent" in source
    assert "text.textContent = message" in source


def test_admin_modulo_keeps_catalog_actions_and_uses_status_components():
    source = (ROOT / "templates" / "admin" / "admin_modulo.html").read_text(encoding="utf-8")
    assert not re.search(r'class="[^"]*\bbadge\s+bg-(?:success|secondary|danger|primary|warning)\b', source)
    assert "app-status__dot" in source
    assert "app-tipo--ambos" in source

    for contract in (
        'id="modalEntidad"',
        'id="modalTurnoDias"',
        'id="modalInstrumentoPortadores"',
        'id="tabla-{{ entidad }}"',
        'data-entidad="{{ entidad }}"',
        'data-id="{{ item.id }}"',
        "data-fields='{{ data.fields|tojson }}'",
        "data-required='{{ data.required|tojson }}'",
        'onclick="abrirModalNuevoFromBtn(this)"',
        'onclick="editarDesdeBtn(this)"',
        'onclick="toggleItem(\'{{ entidad }}\', {{ item.id }})"',
        'onclick="abrirModalTurnoDias({{ item.id }}, {{ item.nombre|tojson|forceescape }})"',
        'onclick="abrirModalPortadoresInstrumento({{ item.id }}, {{ item.nombre|tojson|forceescape }})"',
        'onclick="eliminarItem(\'{{ entidad }}\', {{ item.id }})"',
    ):
        assert contract in source
