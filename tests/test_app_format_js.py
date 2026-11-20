import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


_NODE_FORMAT_CASES = r"""
const assert = require('node:assert/strict');
const path = require('node:path');
global.window = {};
require(path.join(process.cwd(), 'static/js/app_format.js'));
const f = window.App360Format;

assert.equal(f.formatARS(0), '$ 0');
assert.equal(f.formatARS(-1500), '$ -1.500');
assert.equal(f.formatARS(1500), '$ 1.500');
assert.equal(f.formatARS(765000), '$ 765.000');
assert.equal(f.formatARS(250000.5), '$ 250.001');
assert.equal(f.formatARS(1234.56, {decimales: 2}), '$ 1.234,56');
assert.equal(f.formatARS(1234.5, {decimales: 2}), '$ 1.234,50');
assert.equal(f.formatARS(1500, {signo: false}), '1.500');
assert.equal(f.formatNumber(1500), '1.500');
assert.equal(f.formatNumber(1234.56, {decimales: 2}), '1.234,56');
assert.equal(f.formatPercent(0.004, {decimales: 1}), '0,4\u00a0%');
assert.equal(f.formatPercent(0.62), '62\u00a0%');
assert.equal(f.formatARS(null), '—');
assert.equal(f.formatARS(undefined), '—');
assert.equal(f.formatARS(Number.NaN), '—');
assert.equal(f.formatNumber(Number.POSITIVE_INFINITY), '—');
assert.equal(f.parseNumberAR('1.234,56'), 1234.56);
assert.equal(f.parseNumberAR('1234,56'), 1234.56);
assert.equal(f.parseNumberAR('1.500'), 1500);
assert.equal(f.parseNumberAR('$ 1.500'), 1500);
assert.equal(f.parseNumberAR('12.34'), 12.34);
assert.equal(f.parseNumberAR(''), null);
process.stdout.write('Casos de formato OK\n');
"""


_NODE_STATUS_CASES = r"""
const assert = require('node:assert/strict');
const path = require('node:path');
class Element {
  constructor(tag) { this.tagName = tag; this.className = ''; this.attributes = {}; this.children = []; this.value = ''; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  append(...children) { this.children.push(...children); }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(''); }
}
global.window = {};
global.document = {createElement: tag => new Element(tag)};
require(path.join(process.cwd(), 'static/js/app_status.js'));
const render = window.App360Status.statusDot;
const cases = {
  'Cumplido': 'ok',
  'Por debajo del ritmo esperado': 'warn',
  'Sin meta': 'neutral',
  'Activo': 'ok',
  'Inactivo': 'neutral',
  'Pendiente': 'warn',
  'Anulado': 'neutral',
  'Pend. anulación': 'warn',
  'Aprobado': 'ok',
  'Pagado': 'ok',
  'Liquidado': 'neutral',
  'Falta': 'error',
  'Justificado': 'neutral',
};
for (const [state, tone] of Object.entries(cases)) {
  const node = render(state);
  assert.ok(node.className.includes(`app-status--${tone}`), state);
  assert.equal(node.children[0].className, 'app-status__dot');
  assert.equal(node.children[0].attributes['aria-hidden'], 'true');
  assert.equal(node.children[1].textContent, state);
}
const hostile = '<i>dato</i> & "comillas"';
for (const unknown of ['Desconocido', 'constructor', 'toString', '__proto__']) {
  const node = render(unknown, {texto: hostile});
  assert.ok(node.className.includes('app-status--neutral'));
  assert.equal(node.children[1].textContent, hostile);
  assert.equal(node.children[1].innerHTML, undefined);
}
process.stdout.write('Casos de estado y texto seguro OK\n');
"""


def _run_node(source: str) -> None:
    if NODE is None:
        pytest.skip("Node.js no está disponible en PATH; no se pueden ejecutar las pruebas JS.")
    result = subprocess.run(
        [NODE, "-e", source],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_app_format_cases_with_node():
    _run_node(_NODE_FORMAT_CASES)


def test_app_status_variants_and_text_with_node():
    _run_node(_NODE_STATUS_CASES)


def test_javascript_syntax_and_csp_without_dynamic_code():
    for relative_path in ("static/js/app_format.js", "static/js/app_status.js"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert re.search(r"\beval\s*\(|\bnew\s+Function\b", source) is None
        if NODE is None:
            pytest.skip("Node.js no está disponible en PATH; node --check no se puede ejecutar.")
        result = subprocess.run(
            [NODE, "--check", relative_path],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
