import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "static" / "css" / "app_components.css"
BASE_PATH = ROOT / "templates" / "base.html"


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
