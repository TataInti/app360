from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "templates" / "admin" / "admin_dashboard.html"
CURRENT_ROUTES = (
    "/admin/movimientos",
    "/admin/tesoreria",
    "/admin/rrhh",
    "/admin/stock",
    "/admin/accesos",
    "/admin/marketing",
)


def test_admin_dashboard_keeps_current_routes_and_single_primary():
    source = DASHBOARD.read_text(encoding="utf-8")
    missing = [route for route in CURRENT_ROUTES if f'href="{route}"' not in source]

    assert not missing, f"Faltan enlaces de administración existentes: {missing}"
    assert 'class="app-admin-list"' in source
    assert source.count('class="app-actions__primary app-admin-primary"') == 1
