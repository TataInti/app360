"""Measure and safely regenerate the design-token literal ratchet baseline."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "data" / "design_tokens_baseline.json"

# Chart.js series colors are JavaScript drawing data, not CSS tokens. These templates
# intentionally keep their Chart.js color configuration outside this CSS-only ratchet;
# any <style> blocks or style= attributes in the same templates remain in scope.
CHART_JS_TEMPLATE_EXCLUSIONS = (
    "templates/bi_dashboard.html",
    "templates/compras_overview.html",
    "templates/dashboard_financiero.html",
    "templates/gastos_panel.html",
    "templates/panel_ejecutivo.html",
    "templates/rrhh_ausentismo.html",
    "templates/tesoreria_arqueos.html",
    "templates/tesoreria_movimientos.html",
    "templates/tesoreria_panel.html",
)

COLOR_LITERAL_RE = re.compile(
    r"(?<![\w-])#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})(?![\w-])"
    r"|(?<![\w-])rgba?\s*\(",
    flags=re.IGNORECASE,
)
DECLARATION_RE = re.compile(
    r"(?:^|[;{])\s*([a-zA-Z][a-zA-Z0-9-]*)\s*:\s*([^;{}]+)",
    flags=re.MULTILINE,
)
RADIUS_UNIT_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem)\b", flags=re.IGNORECASE)
CUSTOM_PROPERTY_RE = re.compile(r"(?<![\w-])(--[a-zA-Z0-9_-]+)\s*:")
VAR_USAGE_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")
STYLE_ATTRIBUTE_RE = re.compile(
    r"(?<![\w:-])style\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    flags=re.IGNORECASE | re.DOTALL,
)


def source_files(root: Path = ROOT) -> list[Path]:
    """Return the exact CSS/template files covered by this ratchet."""
    files = list((root / "static" / "css").glob("*.css"))
    files.extend((root / "templates").glob("**/*.html"))
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def css_source_for_file(relative_path: str, source: str) -> str:
    """Return stylesheet text, including CSS embedded in HTML but not its scripts."""
    if relative_path.endswith(".css"):
        return _strip_css_comments(source)

    html = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)
    style_blocks = re.findall(r"<style\b[^>]*>(.*?)</style\s*>", html, flags=re.IGNORECASE | re.DOTALL)
    markup = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", html, flags=re.IGNORECASE | re.DOTALL)
    markup = re.sub(r"<style\b[^>]*>.*?</style\s*>", "", markup, flags=re.IGNORECASE | re.DOTALL)
    style_attributes = [
        next(value for value in match.groups() if value is not None)
        for match in STYLE_ATTRIBUTE_RE.finditer(markup)
    ]
    embedded_css = style_blocks + style_attributes
    return _strip_css_comments("\n".join(embedded_css))


def _strip_css_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def count_css_literals(css_source: str) -> dict[str, int]:
    """Count direct color literals and un-tokenized px/rem border radii in CSS."""
    color_count = 0
    radius_count = 0
    for match in DECLARATION_RE.finditer(_strip_css_comments(css_source)):
        property_name, value = match.groups()
        if property_name.startswith("--"):
            continue
        color_count += len(COLOR_LITERAL_RE.findall(value))
        if (
            property_name.lower() == "border-radius"
            and RADIUS_UNIT_RE.search(value)
            and not VAR_USAGE_RE.search(value)
        ):
            radius_count += 1
    return {"colors": color_count, "border_radius": radius_count}


def count_file_literals(relative_path: str, source: str) -> dict[str, int]:
    css_counts = count_css_literals(css_source_for_file(relative_path, source))
    script_colors = 0
    if relative_path.endswith(".html") and relative_path not in CHART_JS_TEMPLATE_EXCLUSIONS:
        script_sources = re.findall(
            r"<script\b[^>]*>(.*?)</script\s*>",
            source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        script_colors = sum(len(COLOR_LITERAL_RE.findall(script)) for script in script_sources)
    return {
        "colors": css_counts["colors"] + script_colors,
        "border_radius": css_counts["border_radius"],
    }


def collect_counts(root: Path = ROOT) -> dict[str, dict[str, int]]:
    counts = {}
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        counts[relative] = count_file_literals(relative, path.read_text(encoding="utf-8"))
    return counts


def custom_properties(css_source: str) -> set[str]:
    return set(CUSTOM_PROPERTY_RE.findall(_strip_css_comments(css_source)))


def root_custom_properties(css_source: str) -> set[str]:
    root_block = re.search(r":root\s*\{([^{}]*)\}", _strip_css_comments(css_source), flags=re.DOTALL)
    if not root_block:
        return set()
    return custom_properties(root_block.group(1))


def document_color_count(path: Path, root: Path) -> int:
    relative = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".css", ".html"}:
        return count_file_literals(relative, source)["colors"]
    # Documentation files are held to zero direct colors too; token definitions are
    # allowed and removed before checking their explanatory examples.
    source = re.sub(r"(?m)^\s*--[a-zA-Z0-9_-]+\s*:\s*[^\n;]+;?", "", source)
    return len(COLOR_LITERAL_RE.findall(source))


def collect_baseline_payload(root: Path = ROOT) -> dict:
    return {
        "version": 1,
        "chart_js_color_exclusions": list(CHART_JS_TEMPLATE_EXCLUSIONS),
        "files": collect_counts(root),
    }


def _increases(current: dict, previous: dict) -> list[str]:
    changes = []
    current_files = current["files"]
    previous_files = previous.get("files", {})
    for relative in sorted(set(current_files) | set(previous_files)):
        actual = current_files.get(relative, {"colors": 0, "border_radius": 0})
        baseline = previous_files.get(relative, {"colors": 0, "border_radius": 0})
        for metric in ("colors", "border_radius"):
            if actual.get(metric, 0) > baseline.get(metric, 0):
                changes.append(
                    f"{relative}: {metric} {baseline.get(metric, 0)} -> {actual.get(metric, 0)}"
                )
    return changes


def update_baseline(root: Path = ROOT) -> int:
    current = collect_baseline_payload(root)
    baseline_path = root / "tests" / "data" / "design_tokens_baseline.json"
    previous = None
    if baseline_path.exists():
        try:
            previous = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"No se pudo leer la línea base existente: {error}", file=sys.stderr)
            return 1

    if previous is not None:
        increases = _increases(current, previous)
        if increases:
            print("No se actualizó la línea base: el ratchet detectó aumentos:", file=sys.stderr)
            print("\n".join(increases), file=sys.stderr)
            return 1

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Línea base escrita: {baseline_path.relative_to(root)} "
        f"({len(current['files'])} archivos medidos; sin aumentos)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="regenera la línea base solo si ningún conteo sube",
    )
    args = parser.parse_args()
    if not args.update:
        parser.error("indicá --update para regenerar la línea base")
    return update_baseline()


if __name__ == "__main__":
    raise SystemExit(main())
