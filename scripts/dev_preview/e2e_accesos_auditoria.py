"""E2E mínimo: un admin concede RRHH «Ver» y el cambio aparece en Usuarios › Auditoría.

Requiere una instancia levantada con usuarios sintéticos (E2E_ADMIN_USER / E2E_ADMIN_PASSWORD) y
un usuario destino E2E_TARGET con rol sin RRHH. Guarda dos capturas en E2E_SHOTS_DIR.
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5072").rstrip("/")
ADMIN = os.environ.get("E2E_ADMIN_USER", "e2e_admin")
CLAVE = os.environ["E2E_ADMIN_PASSWORD"]
TARGET = os.environ.get("E2E_TARGET", "e2e_ventas")
CHROMIUM = os.environ.get("E2E_CHROMIUM")
SHOTS = Path(os.environ.get("E2E_SHOTS_DIR", "."))


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM) if CHROMIUM else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 800})
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.fill("#username", ADMIN)
        page.fill("#password", CLAVE)
        page.click("button[type=submit]")
        page.wait_for_load_state("domcontentloaded")

        page.goto(BASE + "/admin/accesos", wait_until="domcontentloaded")
        fila = page.locator(f'tr[data-user-id]:has-text("{TARGET}")')
        select = fila.locator('select[name="rrhh"]')
        expect(select).to_be_enabled()
        expect(page.get_by_text("«Sin acceso» retira solo la excepción individual")).to_be_visible()
        select.select_option("view")
        expect(page.locator("#accessRrhhNotice")).to_be_visible()
        page.screenshot(path=str(SHOTS / "accesos.png"))
        page.click("#accessSave")
        expect(page.locator("#accessSummary")).to_contain_text("1 de 1 usuarios actualizados")

        page.goto(BASE + "/admin/usuarios/auditoria", wait_until="domcontentloaded")
        expect(page.locator("td", has_text="Acceso modificado").first).to_be_visible()
        expect(page.get_by_text("RRHH: Sin acceso → Ver").first).to_be_visible()
        page.screenshot(path=str(SHOTS / "auditoria.png"))
        browser.close()
    print("OK e2e accesos auditoría")


if __name__ == "__main__":
    sys.exit(main())
