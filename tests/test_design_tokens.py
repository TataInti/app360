"""Guard App360's design tokens and per-file literal ratchet."""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

from design_tokens_baseline import (
    BASELINE_PATH,
    CHART_JS_TEMPLATE_EXCLUSIONS,
    VAR_USAGE_RE,
    collect_counts,
    count_file_literals,
    css_source_for_file,
    custom_properties,
    document_color_count,
    root_custom_properties,
    source_files,
)

ROOT = Path(__file__).resolve().parents[1]
NEW_GLOBAL_TOKENS = {"--state-dot-size", "--drawer-width-form"}


def test_every_used_css_variable_is_defined_in_base_root_or_its_file():
    base_path = ROOT / "templates" / "base.html"
    base_source = base_path.read_text(encoding="utf-8")
    base_css = css_source_for_file("templates/base.html", base_source)
    base_root_tokens = root_custom_properties(base_css)
    undefined = {}

    for path in source_files(ROOT):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        css_source = css_source_for_file(relative, source)
        available = custom_properties(css_source) | base_root_tokens
        used = set(VAR_USAGE_RE.findall(source))
        missing = sorted(used - available)
        if missing:
            undefined[relative] = missing

    assert not undefined, "Tokens CSS sin definir (var(--x)):\n" + "\n".join(
        f"{path}: {', '.join(tokens)}" for path, tokens in sorted(undefined.items())
    )


def test_new_design_tokens_exist_in_base_root():
    base_source = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    base_css = css_source_for_file("templates/base.html", base_source)
    defined = root_custom_properties(base_css)
    missing = sorted(NEW_GLOBAL_TOKENS - defined)
    assert not missing, f"Tokens NUEVOS ausentes de :root en base.html: {missing}"


def test_inline_styles_and_non_chart_script_colors_are_measured():
    counts = count_file_literals(
        "templates/probe.html",
        '<div style=color:#abc123;border-radius:4px></div>'
        '<script>const accent = "#fedcba";</script>',
    )
    assert counts == {"colors": 2, "border_radius": 1}


def test_color_literals_remain_at_or_below_the_per_file_baseline():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["version"] == 1
    assert baseline["chart_js_color_exclusions"] == list(CHART_JS_TEMPLATE_EXCLUSIONS)
    current = collect_counts(ROOT)
    previous = baseline["files"]
    increases = []
    decreases = []

    for relative in sorted(set(current) | set(previous)):
        actual = current.get(relative, {"colors": 0, "border_radius": 0})
        expected = previous.get(relative, {"colors": 0, "border_radius": 0})
        for metric in ("colors", "border_radius"):
            before = expected.get(metric, 0)
            after = actual.get(metric, 0)
            if after > before:
                increases.append(f"{relative}: {metric} {before} -> {after}")
            elif after < before:
                decreases.append(f"{relative}: {metric} {before} -> {after}")

    if decreases:
        warnings.warn(
            "El ratchet bajó en uno o más archivos; para guardar la mejora en la línea base, "
            "ejecutá `python tests/design_tokens_baseline.py --update`.\n"
            + "\n".join(decreases),
            stacklevel=1,
        )
    assert not increases, (
        "Subieron los literales de diseño o apareció un archivo con literales:\n"
        + "\n".join(increases)
    )


def test_components_css_and_design_system_docs_have_no_color_literals():
    component_css = ROOT / "static" / "css" / "app_components.css"
    component_counts = count_file_literals(
        "static/css/app_components.css", component_css.read_text(encoding="utf-8")
    )
    assert component_counts["colors"] == 0, (
        "static/css/app_components.css debe consumir tokens y tener 0 literales de color; "
        f"encontrados: {component_counts['colors']}"
    )

    docs_root = ROOT / "docs" / "sistema"
    document_files = sorted(
        path
        for path in docs_root.glob("**/*")
        if path.is_file() and path.suffix.lower() in {".css", ".html", ".md"}
    )
    violations = {
        path.relative_to(ROOT).as_posix(): document_color_count(path, ROOT)
        for path in document_files
        if document_color_count(path, ROOT) > 0
    }
    assert not violations, f"docs/sistema/ debe tener 0 literales de color: {violations}"


def test_chart_js_color_exclusions_are_explicit_and_still_chart_templates():
    for relative in CHART_JS_TEMPLATE_EXCLUSIONS:
        path = ROOT / relative
        assert path.is_file(), f"Exclusión Chart.js sin archivo: {relative}"
        source = path.read_text(encoding="utf-8")
        assert re.search(r"App360Charts|\bChart\b", source), (
            f"Revisá la exclusión Chart.js; ya no parece contener un gráfico: {relative}"
        )

    chart_markup = (
        "<style>.probe { color: #abc123; }</style>"
        "<script>const seriesColor = '#fedcba';</script>"
    )
    counts = count_file_literals("templates/bi_dashboard.html", chart_markup)
    assert counts == {"colors": 1, "border_radius": 0}
