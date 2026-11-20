import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "static" / "css" / "app_components.css"
BASE_PATH = ROOT / "templates" / "base.html"
GLOBAL_PRIMARY_SELECTOR = (
    ".btn-primary:not(.com-primary):not(.criterio-btn)"
    ":not(.btn-outline-primary):not(.btn-secondary):not(.btn-success)"
    ":not(.btn-warning)"
)
ALLOWED_GLOBAL_PRIMARY_SELECTORS = {
    GLOBAL_PRIMARY_SELECTOR,
    f"{GLOBAL_PRIMARY_SELECTOR}:focus-visible",
}


def test_css_exists_and_base_links_it_once():
    assert CSS_PATH.is_file()
    base = BASE_PATH.read_text(encoding="utf-8")
    assert base.count("asset('css/app_components.css')") == 1


def test_css_selectors_only_use_app_classes():
    css = re.sub(r"/\*.*?\*/", "", CSS_PATH.read_text(encoding="utf-8"), flags=re.S)
    selector_blocks = re.findall(r"([^{}]+)\{", css)

    assert selector_blocks
    for selector_block in selector_blocks:
        for selector in selector_block.split(","):
            selector = selector.strip()
            if not selector:
                continue
            if selector in ALLOWED_GLOBAL_PRIMARY_SELECTORS:
                continue
            classes = re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", selector)
            assert classes, f"Selector sin clase: {selector}"
            assert all(name.startswith("app-") for name in classes), selector

            remainder = re.sub(r"\.[A-Za-z_][A-Za-z0-9_-]*", "", selector)
            remainder = re.sub(r"\[[^\]]+\]", "", remainder)
            remainder = re.sub(r":(?:focus-visible|focus-within|hover)", "", remainder)
            remainder = re.sub(r"[\s>+~]", "", remainder)
            assert not remainder, f"Selector con etiqueta u operador ajeno: {selector}"

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)


def test_every_css_variable_is_defined_in_base_or_component_css():
    base = BASE_PATH.read_text(encoding="utf-8")
    root = re.search(r":root\s*\{([^}]*)\}", base, flags=re.S)
    assert root, "No se encontró :root en base.html"

    defined = set(re.findall(r"(--[A-Za-z0-9_-]+)\s*:", root.group(1)))
    css = CSS_PATH.read_text(encoding="utf-8")
    defined.update(re.findall(r"(--[A-Za-z0-9_-]+)\s*:", css))
    used = set(re.findall(r"var\(\s*(--[A-Za-z0-9_-]+)", css))
    assert used <= defined, f"Tokens sin definir: {sorted(used - defined)}"


def test_new_state_and_drawer_tokens_are_present_once():
    base = BASE_PATH.read_text(encoding="utf-8")
    assert len(re.findall(r"^\s*--state-dot-size:\s*8px;\s*$", base, flags=re.M)) == 1
    assert len(re.findall(r"^\s*--drawer-width-form:\s*440px;\s*$", base, flags=re.M)) == 1


def test_bootstrap_primary_maps_states_to_tokens_and_preserves_exceptions():
    css = re.sub(r"/\*.*?\*/", "", CSS_PATH.read_text(encoding="utf-8"), flags=re.S)

    def rule_body(selector):
        match = re.search(re.escape(selector) + r"\s*\{([^{}]*)\}", css, flags=re.S)
        assert match, f"Falta la regla global de botón primario: {selector}"
        return match.group(1)

    primary_body = rule_body(GLOBAL_PRIMARY_SELECTOR)
    declarations = dict(re.findall(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);", primary_body))
    expected = {
        "--bs-btn-color": "var(--color-surface)",
        "--bs-btn-bg": "var(--color-action)",
        "--bs-btn-border-color": "var(--color-action)",
        "--bs-btn-hover-color": "var(--color-surface)",
        "--bs-btn-hover-bg": "var(--color-action-hover)",
        "--bs-btn-hover-border-color": "var(--color-action-hover)",
        "--bs-btn-active-color": "var(--color-surface)",
        "--bs-btn-active-bg": "var(--color-action-hover)",
        "--bs-btn-active-border-color": "var(--color-action-hover)",
        "--bs-btn-disabled-color": "var(--color-text-muted)",
        "--bs-btn-disabled-bg": "var(--color-surface-muted)",
        "--bs-btn-disabled-border-color": "var(--color-border)",
        "--bs-btn-disabled-opacity": "1",
    }
    assert {name: declarations.get(name, "").strip() for name in expected} == expected

    for excluded in (
        ".com-primary",
        ".criterio-btn",
        ".btn-outline-primary",
        ".btn-secondary",
        ".btn-success",
        ".btn-warning",
    ):
        assert f":not({excluded})" in GLOBAL_PRIMARY_SELECTOR

    # Pulido final 1 (H01): el primario de modales vuelve al token; ninguna regla lo excluye.
    assert ":not(.app-modal .btn-primary)" not in css
    assert ".app-modal .btn-primary" not in GLOBAL_PRIMARY_SELECTOR

    assert ".btn-save" not in GLOBAL_PRIMARY_SELECTOR
    admin_access = (ROOT / "templates" / "admin" / "admin_accesos.html").read_text(
        encoding="utf-8"
    )
    assert 'id="accessSave" class="app-actions__primary" disabled' in admin_access
    assert "Guardar cambios (0)" in admin_access
    assert "btn-save" not in admin_access
    access_js = (ROOT / "static" / "js" / "admin_accesos.js").read_text(encoding="utf-8")
    assert "querySelectorAll('tbody tr[data-user-id]')" in access_js
    assert "Guardar cambios (${count})" in access_js

    focus_body = rule_body(f"{GLOBAL_PRIMARY_SELECTOR}:focus-visible")
    assert re.search(r"outline:\s*3px\s+solid\s+var\(--color-focus\)", focus_body)
    assert re.search(r"outline-offset:\s*2px", focus_body)
    assert re.search(r"box-shadow:\s*none", focus_body)
