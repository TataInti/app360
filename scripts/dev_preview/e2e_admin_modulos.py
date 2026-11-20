"""Recorrido E2E de Administración › Catálogos por módulo con datos T-.

Usa una instancia local aislada y el login/telemetría existentes de e2e_accesos.
No modifica blueprint ni datos fuera de la base indicada por E2E_DATABASE_URL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "dev_preview"))

import e2e_accesos
from e2e_accesos import Checks, instrumentar, login
from e2e_objetivos_helpers import leer_accesos

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5062").rstrip("/")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
SHOTS_DIR = Path(
    os.environ.get("E2E_SHOTS_DIR")
    or f"/root/.hermes/cache/scratch/e2e-shots/sis2a-admin-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
)
CAPTURE_LABEL = os.environ.get("E2E_CAPTURE_LABEL", "after")
DB_NAME = "app360_sis2a_admin"
TOKEN = "T-SIS2A"

# Los inputs type=number del modal no aceptan decimales (el atributo step se escapa en el
# template: hallazgo previo al PR). Por eso importes enteros en el alta.
MODULES = {
    "movimientos": {
        "conceptos": {
            "values": {
                "nombre": 'T-SIS2A & <"concepto>',
                "descripcion": 'T-SIS2A & <"descripcion>',
                "naturaleza": "ingreso",
                "incluye_resultado": True,
                "activo": True,
            },
            "display": "nombre",
            "edit": {"field": "nombre", "value": 'T-SIS2A & <"concepto editado>'},
            "toggle": True,
        },
        "proveedores": {
            "values": {
                "nombre": 'T-SIS2A & <"proveedor>',
                "cuit": "T-SIS2A-001",
                "email": "t-sis2a@example.invalid",
                "telefono": "T-SIS2A",
                "direccion": 'T-SIS2A & <"direccion>',
                "activo": True,
            },
            "display": "nombre",
            "edit": {"field": "nombre", "value": 'T-SIS2A & <"proveedor editado>'},
            "toggle": True,
        },
    },
    "tesoreria": {
        "instrumentos": {
            "values": {
                "nombre": 'T-SIS2A & <"instrumento>',
                "descripcion": 'T-SIS2A & <"descripcion>',
                "requiere_portador": True,
                "activo": True,
            },
            "display": "nombre",
            "edit": {"field": "nombre", "value": 'T-SIS2A & <"instrumento editado>'},
            "toggle": True,
        },
        "portadores": {
            "values": {
                "nombre": 'T-SIS2A & <"portador>',
                "documento": "T-SIS2A-DOC",
                "telefono": "T-SIS2A",
                "notas": 'T-SIS2A & <"nota>',
                "activo": True,
            },
            "display": "nombre",
            "edit": {"field": "nombre", "value": 'T-SIS2A & <"portador editado>'},
            "toggle": True,
        },
        "cuenta_friar": {
            "values": {
                "saldo_inicial": "1.234,50",
                "observaciones": 'T-SIS2A & <"cuenta>',
            },
            "display": "observaciones",
            "edit": {"field": "observaciones", "value": 'T-SIS2A & <"cuenta editada>'},
            "toggle": False,
        },
    },
    "rrhh": {
        "empleados": {
            "values": {
                "first_name": "T-SIS2A",
                "last_name": "Empleado",
                "email": "t-sis2a-empleado@example.invalid",
                "phone": "T-SIS2A",
                "position": "vendedor",
                "department": "T-SIS2A",
                "hire_date": "2026-11-01",
                "salary": "1234",
                "location_id": "",
                "clock_id": "",
                "turno_id": "",
                "is_active": "true",
            },
            "display": "first_name",
            "edit": {"field": "last_name", "value": "T-SIS2A Editado"},
            "toggle": False,
        },
        "turnos": {
            "values": {
                "nombre": 'T-SIS2A & <"turno>',
                "descripcion": 'T-SIS2A & <"horario>',
                "activo": True,
            },
            "display": "nombre",
            "edit": {"field": "nombre", "value": 'T-SIS2A & <"turno editado>'},
            "toggle": True,
        },
    },
    "stock": {
        "ubicaciones": {
            "values": {"name": 'T-SIS2A & <"ubicacion>', "address": 'T-SIS2A & <"direccion>'},
            "display": "name",
            "edit": {"field": "name", "value": 'T-SIS2A & <"ubicacion editada>'},
            "toggle": False,
        },
        "productos": {
            "values": {
                "name": 'T-SIS2A & <"producto>',
                "sku": "T-SIS2A-SKU-001",
                "price": "123",
                "category": "T-SIS2A",
            },
            "display": "name",
            "edit": {"field": "name", "value": 'T-SIS2A & <"producto editado>'},
            "toggle": False,
        },
        "unidades": {
            "values": {"name": 'T-SIS2A & <"unidad>'},
            "display": "name",
            "edit": {"field": "name", "value": 'T-SIS2A & <"unidad editada>'},
            "toggle": False,
        },
    },
    "marketing": {
        "pipeline": {
            "values": {"name": 'T-SIS2A & <"etapa>', "position": "99", "activo": True},
            "display": "name",
            "edit": {"field": "name", "value": 'T-SIS2A & <"etapa editada>'},
            "toggle": True,
        },
    },
}


def check(checks: Checks, name: str, ok: bool, detail: str = "") -> None:
    checks.check(name, ok, detail)


def api_list(page, module: str, entity: str) -> dict:
    response = page.request.get(f"{BASE_URL}/api/admin/{module}/{entity}", max_redirects=0)
    if response.status != 200:
        raise AssertionError(f"GET API {module}/{entity}: HTTP {response.status}")
    payload = response.json()
    if not isinstance(payload.get("items"), list):
        raise AssertionError(f"GET API {module}/{entity}: respuesta sin items")
    return payload


def api_item(page, module: str, entity: str, item_id: int) -> dict:
    payload = api_list(page, module, entity)
    return next((row for row in payload["items"] if row.get("id") == item_id), {})


def visible_row(page, entity: str, item_id: int):
    row = page.locator(f'#tabla-{entity} tbody tr[data-id="{item_id}"]')
    row.wait_for(state="visible", timeout=10000)
    return row


def marcar_pantalla(page) -> None:
    """Marca la pantalla: la recarga que la app hace tras una acción la borra."""
    page.evaluate("() => { window.__sis2aMarca = true; }")


def esperar_recarga(page) -> None:
    """Espera la recarga (location.reload) que la app hace tras guardar, cambiar estado o eliminar."""
    fin = time.monotonic() + 30
    while time.monotonic() < fin:
        try:
            page.wait_for_load_state("load", timeout=3000)
            if page.evaluate("() => window.__sis2aMarca !== true"):
                page.wait_for_load_state("networkidle", timeout=20000)
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(250)
    raise AssertionError("la pantalla no se recargó después de la acción")


def ensure_tab(page, module: str, entity: str) -> None:
    if urlparse(page.url).path != f"/admin/{module}":
        page.goto(f"{BASE_URL}/admin/{module}", wait_until="networkidle")
    tab = page.locator(f"#tab-{entity}")
    tab.wait_for(state="visible")
    if tab.get_attribute("aria-selected") != "true":
        tab.click()
    page.locator(f"#content-{entity}.active .table-card").wait_for(state="visible")


def fill_modal(page, values: dict) -> None:
    for field, value in values.items():
        control = page.locator(f'#modalCampos [name="{field}"]')
        if not control.count():
            continue
        if control.get_attribute("type") == "checkbox":
            control.set_checked(bool(value))
        elif control.evaluate("element => element.tagName.toLowerCase()") == "select":
            control.select_option(str(value))
        else:
            control.fill(str(value))


def wait_for_confirm_and_accept(page) -> None:
    confirm = page.locator("#app360ConfirmModal")
    try:
        confirm.wait_for(state="visible", timeout=6000)
    except PlaywrightTimeoutError:
        return
    # El clic durante la transición de apertura del modal se pierde: esperar a que esté visible del todo.
    page.locator("#app360ConfirmModal.show").wait_for(state="visible")
    page.wait_for_timeout(800)
    page.locator("#app360ConfirmAccept").click()
    confirm.wait_for(state="hidden", timeout=10000)


def create_item(page, module: str, entity: str, values: dict, display: str) -> int:
    ensure_tab(page, module, entity)
    empty_cta = page.locator(f"#content-{entity} .empty-state button[onclick*='abrirModalNuevoFromBtn']")
    new_button = empty_cta if empty_cta.is_visible() else page.locator(
        f"#content-{entity} .table-card-head button[onclick*='abrirModalNuevoFromBtn']"
    )
    marcar_pantalla(page)
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and f"/api/admin/{module}/{entity}" in urlparse(response.url).path,
        timeout=15000,
    ) as response_info:
        new_button.click()
        page.locator("#modalEntidad").wait_for(state="visible")
        fill_modal(page, values)
        page.locator('#modalEntidad button[type="submit"]').click()
    response = response_info.value
    if response.status != 201:
        raise AssertionError(f"POST {module}/{entity}: HTTP {response.status}")
    esperar_recarga(page)
    matches = [row for row in api_list(page, module, entity)["items"] if row.get(display) == values.get(display)]
    if len(matches) != 1:
        raise AssertionError(f"POST {module}/{entity}: readback ambiguo para {display}")
    item_id = int(matches[0]["id"])
    ensure_tab(page, module, entity)
    visible_row(page, entity, item_id)
    return item_id


def edit_item(page, module: str, entity: str, item_id: int, field: str, value: str) -> None:
    ensure_tab(page, module, entity)
    row = visible_row(page, entity, item_id)
    marcar_pantalla(page)
    with page.expect_response(
        lambda response: response.request.method == "PUT"
        and f"/api/admin/{module}/{entity}/{item_id}" in urlparse(response.url).path,
        timeout=15000,
    ) as response_info:
        row.locator('button[aria-label="Editar registro"]').click()
        page.locator("#modalEntidad").wait_for(state="visible")
        control = page.locator(f'#modalCampos [name="{field}"]')
        if control.get_attribute("type") == "checkbox":
            control.set_checked(bool(value))
        elif control.evaluate("element => element.tagName.toLowerCase()") == "select":
            control.select_option(str(value))
        else:
            control.fill(str(value))
        page.locator('#modalEntidad button[type="submit"]').click()
        wait_for_confirm_and_accept(page)
    response = response_info.value
    if response.status != 200:
        raise AssertionError(f"PUT {module}/{entity}/{item_id}: HTTP {response.status}")
    esperar_recarga(page)


def toggle_item(page, module: str, entity: str, item_id: int, expected: bool) -> None:
    ensure_tab(page, module, entity)
    row = visible_row(page, entity, item_id)
    marcar_pantalla(page)
    with page.expect_response(
        lambda response: response.request.method == "PATCH"
        and f"/api/admin/{module}/{entity}/{item_id}/toggle" in urlparse(response.url).path,
        timeout=15000,
    ) as response_info:
        row.locator('button[aria-label="Activar o desactivar registro"]').click()
    response = response_info.value
    if response.status != 200:
        raise AssertionError(f"PATCH {module}/{entity}/{item_id}/toggle: HTTP {response.status}")
    esperar_recarga(page)
    ensure_tab(page, module, entity)
    record = api_item(page, module, entity, item_id)
    state_field = "activo" if "activo" in record else "is_active"
    if bool(record.get(state_field)) != expected:
        raise AssertionError(f"Estado API inesperado para {module}/{entity}/{item_id}")
    status_text = "Activo" if expected else "Inactivo"
    labels = [text.strip() for text in visible_row(page, entity, item_id).locator(".app-status__text").all_inner_texts()]
    if status_text not in labels:
        raise AssertionError(f"Estado visible inesperado: {labels!r}")


def configure_turno(page, turno_id: int) -> dict:
    ensure_tab(page, "rrhh", "turnos")
    row = visible_row(page, "turnos", turno_id)
    row.locator('button[aria-label="Configurar horarios"]').click()
    page.locator("#modalTurnoDias").wait_for(state="visible")
    monday = page.locator("#turno-dia-0")
    monday.locator(".td-activo").check()
    monday.locator(".td-hi1").fill("09:00")
    monday.locator(".td-hf1").fill("17:00")
    with page.expect_response(
        lambda response: response.request.method == "PUT"
        and f"/api/rrhh/turnos/{turno_id}/dias" in urlparse(response.url).path,
        timeout=15000,
    ) as response_info:
        page.locator('button[onclick="guardarTurnoDias()"]')
        page.get_by_role("button", name="Guardar horarios").click()
    response = response_info.value
    if response.status != 200:
        raise AssertionError(f"PUT turnos/{turno_id}/dias: HTTP {response.status}")
    payload = response.json()
    # El endpoint confirma con «message» (contrato de rrhh.py), no con «success».
    if payload.get("message") != "Horarios actualizados":
        raise AssertionError("La API no confirmó el guardado de horarios")
    data = page.request.get(f"{BASE_URL}/api/rrhh/turnos/{turno_id}/dias", max_redirects=0)
    if data.status != 200:
        raise AssertionError(f"GET turnos/{turno_id}/dias: HTTP {data.status}")
    monday_api = next((day for day in data.json().get("dias", []) if day.get("dia_semana") == 0), {})
    return monday_api


def configure_portador(page, instrument_id: int, portador_id: int) -> dict:
    ensure_tab(page, "tesoreria", "instrumentos")
    row = visible_row(page, "instrumentos", instrument_id)
    row.locator('button[aria-label="Configurar portadores"]').click()
    page.locator("#modalInstrumentoPortadores").wait_for(state="visible")
    checkbox = page.locator(f'#modalInstrumentoPortadores .instr-port-cb[value="{portador_id}"]')
    checkbox.wait_for(state="visible")
    checkbox.check()
    with page.expect_response(
        lambda response: response.request.method == "PUT"
        and f"/api/admin/tesoreria/instrumentos/{instrument_id}/portadores" in urlparse(response.url).path,
        timeout=15000,
    ) as response_info:
        page.get_by_role("button", name="Guardar", exact=True).last.click()
    response = response_info.value
    if response.status != 200:
        raise AssertionError(f"PUT instrumentos/{instrument_id}/portadores: HTTP {response.status}")
    payload = response.json()
    if payload.get("count") != 1:
        raise AssertionError("La API no confirmó un portador asociado")
    readback = page.request.get(
        f"{BASE_URL}/api/admin/tesoreria/instrumentos/{instrument_id}/portadores", max_redirects=0
    )
    if readback.status != 200:
        raise AssertionError(f"GET instrumentos/{instrument_id}/portadores: HTTP {readback.status}")
    return next((item for item in readback.json().get("portadores", []) if item.get("id") == portador_id), {})


def delete_item(page, module: str, entity: str, item_id: int) -> None:
    ensure_tab(page, module, entity)
    row = visible_row(page, entity, item_id)
    marcar_pantalla(page)
    with page.expect_response(
        lambda response: response.request.method == "DELETE"
        and f"/api/admin/{module}/{entity}/{item_id}" in urlparse(response.url).path,
        timeout=15000,
    ) as response_info:
        row.locator('button[aria-label="Eliminar registro"]').click()
        page.locator("#app360ConfirmModal.show").wait_for(state="visible")
        page.wait_for_timeout(800)
        page.locator("#app360ConfirmAccept").click()
    response = response_info.value
    if response.status != 200:
        raise AssertionError(f"DELETE {module}/{entity}/{item_id}: HTTP {response.status}")
    esperar_recarga(page)


def verify_dom_and_api(checks: Checks, page, module: str, entity: str, item_id: int, display: str, expected: str) -> dict:
    ensure_tab(page, module, entity)
    payload = api_list(page, module, entity)
    record = next((row for row in payload["items"] if row.get("id") == item_id), {})
    row = visible_row(page, entity, item_id)
    dom_text = row.inner_text()
    api_value = str(record.get(display, ""))
    check(checks, f"{module}/{entity}: API y fila muestran el mismo dato", bool(record) and api_value == expected and expected in dom_text,
          f"campo={display}; api={api_value!r}; fila_coincide={expected in dom_text}")
    check(checks, f"{module}/{entity}: texto T- escapado sin markup", expected in dom_text and row.locator("script").count() == 0,
          f"texto_visible_exacto={expected in dom_text}; scripts_en_fila={row.locator('script').count()}")
    return record


def capture_viewports(page, checks: Checks) -> None:
    for width, height in ((1440, 900), (1366, 768)):
        page.set_viewport_size({"width": width, "height": height})
        for module in ("movimientos", "rrhh"):
            page.goto(f"{BASE_URL}/admin/{module}", wait_until="networkidle")
            page.locator(".panel-header h1").wait_for(state="visible")
            primary_count = page.locator("button.btn-primary:visible").count()
            check(checks, f"{module} {width}x{height}: una acción primaria visible", primary_count == 1,
                  f"botones_primarios={primary_count}")
            SHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SHOTS_DIR / f"{CAPTURE_LABEL}-{module}-{width}x{height}.png"), full_page=True)


def contrast_ratio(foreground: str, background: str) -> float:
    def channels(value: str) -> list[float]:
        parts = value.removeprefix("rgb(").removeprefix("rgba(").removesuffix(")").split(",")
        rgb = [float(part.strip()) / 255 for part in parts[:3]]
        return [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in rgb]

    luminance = lambda rgb: 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    first, second = sorted((luminance(channels(foreground)), luminance(channels(background))), reverse=True)
    return (first + 0.05) / (second + 0.05)


def measure_contrast(page) -> dict:
    samples = page.evaluate("""() => {
        const text = document.querySelector('.app-status__text');
        const chip = document.querySelector('.app-tipo');
        if (!text || !chip) return null;
        const bgFor = element => {
            for (let node = element; node; node = node.parentElement) {
                const color = getComputedStyle(node).backgroundColor;
                if (color && color !== 'rgba(0, 0, 0, 0)' && color !== 'transparent') return color;
            }
            return getComputedStyle(document.body).backgroundColor;
        };
        return {
            status: { fg: getComputedStyle(text).color, bg: bgFor(text) },
            chip: { fg: getComputedStyle(chip).color, bg: getComputedStyle(chip).backgroundColor },
            dot: { fg: getComputedStyle(document.querySelector('.app-status__dot')).backgroundColor, bg: bgFor(text) }
        };
    }""")
    if not samples:
        return {}
    for key in ("status", "chip", "dot"):
        samples[key]["ratio"] = contrast_ratio(samples[key]["fg"], samples[key]["bg"])
    return samples


def run_capture_only(page, checks: Checks) -> None:
    capture_viewports(page, checks)


def seed_visual_fixtures(page, checks: Checks) -> None:
    csrf_token = page.locator('meta[name="csrf-token"]').get_attribute("content")
    fixtures = (
        ("movimientos", "conceptos", {
            "nombre": 'T-SIS2A-VIS & <"concepto>',
            "descripcion": 'T-SIS2A-VIS & <"detalle>',
            "naturaleza": "ingreso",
            "incluye_resultado": True,
            "activo": True,
        }),
        ("rrhh", "turnos", {
            "nombre": 'T-SIS2A-VIS & <"turno>',
            "descripcion": 'T-SIS2A-VIS & <"horario>',
            "activo": True,
        }),
    )
    for module, entity, values in fixtures:
        response = page.request.post(
            f"{BASE_URL}/api/admin/{module}/{entity}",
            data=values,
            headers={"X-CSRFToken": csrf_token or ""},
        )
        item_id = response.json().get("id") if response.status == 201 else None
        ok = item_id is not None
        if item_id is not None:
            page.goto(f"{BASE_URL}/admin/{module}", wait_until="networkidle")
            ensure_tab(page, module, entity)
            row = visible_row(page, entity, int(item_id))
            ok = values["nombre"] in row.inner_text()
        check(checks, f"captura fixture {module}/{entity}: API y pantalla", ok,
              f"HTTP={response.status}; id={item_id or 'ausente'}")


def cleanup_synthetic(page, checks: Checks) -> None:
    """Borra solo filas con el prefijo de esta corrida en la base E2E propia."""
    csrf_token = page.locator('meta[name="csrf-token"]').get_attribute("content") or ""
    instruments = api_list(page, "tesoreria", "instrumentos")["items"]
    synthetic_instruments = [
        row for row in instruments
        if str(row.get("nombre", "")).startswith(TOKEN)
    ]
    for instrument in synthetic_instruments:
        response = page.request.put(
            f"{BASE_URL}/api/admin/tesoreria/instrumentos/{instrument['id']}/portadores",
            data={"portador_ids": []},
            headers={"X-CSRFToken": csrf_token},
        )
        check(checks, "limpieza T-: quitar asociaciones anteriores de portadores", response.status == 200,
              f"instrumento_id={instrument['id']}; HTTP={response.status}")

    for module, entities in reversed(list(MODULES.items())):
        for entity, spec in reversed(list(entities.items())):
            payload = api_list(page, module, entity)
            candidates = [
                row for row in payload["items"]
                if any(str(row.get(field, "")).startswith(TOKEN) for field in spec["values"])
            ]
            for row in candidates:
                response = page.request.delete(
                    f"{BASE_URL}/api/admin/{module}/{entity}/{row['id']}",
                    headers={"X-CSRFToken": csrf_token},
                )
                absent = not any(item.get("id") == row["id"] for item in api_list(page, module, entity)["items"])
                check(checks, f"limpieza T- previa {module}/{entity}", response.status == 200 and absent,
                      f"id={row['id']}; HTTP={response.status}; ausente={absent}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-only", action="store_true", help="solo captura dos módulos y mide primarios")
    parser.add_argument("--seed-visual-fixtures", action="store_true", help="crea dos fixtures T- para las capturas comparativas")
    parser.add_argument("--cleanup-only", action="store_true", help="elimina solo los registros con prefijo T-SIS2A de la base propia")
    args = parser.parse_args()

    parsed = urlparse(os.environ.get("DATABASE_URL", ""))
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != 55432 or parsed.path.lstrip("/") != DB_NAME:
        raise SystemExit("Se rechazó el E2E: DATABASE_URL no apunta a la base sintética propia.")
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    e2e_accesos.SHOTS_DIR = SHOTS_DIR
    checks = Checks()
    created: dict[tuple[str, str], dict] = {}
    total_errors = 0
    resource_failures: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204))
        instrumentar(page, checks)
        page.on(
            "response",
            lambda response: resource_failures.append({"status": response.status, "url": response.url})
            if response.status >= 400 else None,
        )
        logged_in = login(page)
        check(checks, "login admin del seed", logged_in, f"ruta={urlparse(page.url).path}")
        if not logged_in:
            browser.close()
            return 1
        try:
            access_rows = leer_accesos(context, BASE_URL)
            admin_visible = any(row.get("username") == os.environ.get("E2E_ADMIN_USER", "admin") for row in access_rows.values())
            check(checks, "sesión admin verificada por API", admin_visible, f"usuarios={len(access_rows)}")
        except Exception as error:
            check(checks, "sesión admin verificada por API", False, str(error))

        if args.cleanup_only:
            cleanup_synthetic(page, checks)
        elif args.seed_visual_fixtures:
            seed_visual_fixtures(page, checks)
        elif args.capture_only:
            run_capture_only(page, checks)
        else:
            try:
                cleanup_synthetic(page, checks)
            except Exception as error:
                check(checks, "limpieza de la corrida T- anterior", False, f"{type(error).__name__}: {error}")
            for module, entities in MODULES.items():
                page.goto(f"{BASE_URL}/admin/{module}", wait_until="networkidle")
                page.locator(".panel-header h1").wait_for(state="visible")
                primary_count = page.locator("button.btn-primary:visible").count()
                check(checks, f"{module}: una acción primaria visible", primary_count == 1,
                      f"botones_primarios={primary_count}")
                for entity, spec in entities.items():
                    key = (module, entity)
                    try:
                        if module == "stock" and entity == "unidades":
                            ensure_tab(page, module, entity)
                            empty_title = page.locator("#content-unidades .empty-title")
                            empty_action = page.locator("#content-unidades .empty-state button")
                            empty_ok = empty_title.is_visible() and empty_action.is_visible()
                            check(checks, "stock/unidades: vacío con frase y acción", empty_ok,
                                  f"frase={empty_title.is_visible()}; accion={empty_action.is_visible()}")
                        item_id = create_item(page, module, entity, spec["values"], spec["display"])
                        record = api_item(page, module, entity, item_id)
                        check(checks, f"{module}/{entity}: alta visible y persistida", bool(record), f"id={item_id}")
                        created[key] = {"id": item_id, "record": record, "spec": spec}
                        verify_dom_and_api(checks, page, module, entity, item_id, spec["display"], str(spec["values"].get(spec["display"], "")))
                    except Exception as error:
                        check(checks, f"{module}/{entity}: alta y lectura", False, f"{type(error).__name__}: {error}")

            for (module, entity), entry in list(created.items()):
                item_id = entry["id"]
                spec = entry["spec"]
                try:
                    edit = spec.get("edit")
                    if edit:
                        edit_item(page, module, entity, item_id, edit["field"], edit["value"])
                        record = api_item(page, module, entity, item_id)
                        check(checks, f"{module}/{entity}: edición leída desde API", record.get(edit["field"]) == edit["value"],
                              f"campo={edit['field']}; persistido={record.get(edit['field'])!r}")
                        verify_dom_and_api(checks, page, module, entity, item_id, edit["field"], str(edit["value"]))
                    if spec.get("toggle"):
                        toggle_item(page, module, entity, item_id, False)
                        check(checks, f"{module}/{entity}: desactivar coincide en API y pantalla", True)
                        toggle_item(page, module, entity, item_id, True)
                        check(checks, f"{module}/{entity}: activar coincide en API y pantalla", True)
                except Exception as error:
                    check(checks, f"{module}/{entity}: edición/estado", False, f"{type(error).__name__}: {error}")

            turno = created.get(("rrhh", "turnos"))
            if turno:
                try:
                    monday = configure_turno(page, turno["id"])
                    ok = monday.get("activo") and monday.get("hora_inicio_1", "").startswith("09:00") and monday.get("hora_fin_1", "").startswith("17:00")
                    check(checks, "rrhh/turnos: horarios leídos desde API", bool(ok), f"lunes_activo={bool(monday.get('activo'))}")
                except Exception as error:
                    check(checks, "rrhh/turnos: horarios", False, f"{type(error).__name__}: {error}")

            instrument = created.get(("tesoreria", "instrumentos"))
            portador = created.get(("tesoreria", "portadores"))
            if instrument and portador:
                try:
                    associated = configure_portador(page, instrument["id"], portador["id"])
                    check(checks, "tesoreria/instrumentos: portador asociado por API y pantalla", bool(associated.get("asociado")),
                          f"asociado={bool(associated.get('asociado'))}")
                except Exception as error:
                    check(checks, "tesoreria/instrumentos: portadores", False, f"{type(error).__name__}: {error}")

            capture_viewports(page, checks)

            # Catálogos con botón «Eliminar». cuenta_friar no tiene baja en la UI (cuenta única).
            # Instrumentos antes que portadores: el instrumento tiene la asociación M2M.
            delete_targets = [
                ("movimientos", "conceptos"),
                ("movimientos", "proveedores"),
                ("tesoreria", "instrumentos"),
                ("tesoreria", "portadores"),
                ("rrhh", "empleados"),
                ("rrhh", "turnos"),
                ("stock", "ubicaciones"),
                ("stock", "productos"),
                ("stock", "unidades"),
                ("marketing", "pipeline"),
            ]
            for module, entity in delete_targets:
                entry = created.get((module, entity))
                if not entry:
                    check(checks, f"{module}/{entity}: eliminar con confirmación", False, "no se creó el registro sintético")
                    continue
                item_id = entry["id"]
                try:
                    delete_item(page, module, entity, item_id)
                    absent = not any(row.get("id") == item_id for row in api_list(page, module, entity)["items"])
                    check(checks, f"{module}/{entity}: eliminar con confirmación y API", absent, f"id={item_id}; ausente={absent}")
                except Exception as error:
                    check(checks, f"{module}/{entity}: eliminar con confirmación", False, f"{type(error).__name__}: {error}")

            page.goto(f"{BASE_URL}/admin/movimientos", wait_until="networkidle")
            page.locator(".panel-header h1").wait_for(state="visible")
            if created.get(("movimientos", "conceptos")):
                concept_id = created[("movimientos", "conceptos")]["id"]
                row = page.locator(f'#tabla-conceptos tbody tr[data-id="{concept_id}"]')
                check(checks, "movimientos: estado con punto y texto", row.locator(".app-status__dot").count() > 0,
                      f"puntos={row.locator('.app-status__dot').count()}")
                check(checks, "movimientos: chip de tipo", row.locator(".app-tipo").count() > 0,
                      f"chips={row.locator('.app-tipo').count()}")
                contrast = measure_contrast(page)
                status_ok = contrast.get("status", {}).get("ratio", 0) >= 4.5
                chip_ok = contrast.get("chip", {}).get("ratio", 0) >= 4.5
                dot_ok = contrast.get("dot", {}).get("ratio", 0) >= 3
                check(checks, "contraste de estado/chip/punto", status_ok and chip_ok and dot_ok,
                      json.dumps({key: round(value.get("ratio", 0), 2) for key, value in contrast.items()}))

        favicon_404 = any(item["status"] == 404 and urlparse(item["url"]).path == "/favicon.ico" for item in resource_failures)
        unexpected_console_errors = [
            error for error in checks.page_errors
            if not (favicon_404 and error.get("type") == "console" and "Failed to load resource" in error.get("text", ""))
        ]
        check(checks, "sin errores de consola de la app (favicon 404 se informa aparte)", not unexpected_console_errors,
              f"consola_total={len(checks.page_errors)}; 404_favicon={favicon_404}; app_errors={len(unexpected_console_errors)}")
        report = {
            "base_url": BASE_URL,
            "database": DB_NAME,
            "total": len(checks.results),
            "passed": sum(item["ok"] for item in checks.results),
            "failed": sum(not item["ok"] for item in checks.results),
            "checks": checks.results,
            "page_errors": checks.page_errors,
            "resource_failures": resource_failures,
            "capturas": sorted(path.name for path in SHOTS_DIR.glob("*.png")),
        }
        (SHOTS_DIR / "informe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()

    total_errors = sum(not item["ok"] for item in checks.results)
    print(f"E2E_ADMIN_MODULOS {len(checks.results) - total_errors}/{len(checks.results)}; informe={SHOTS_DIR / 'informe.json'}")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
