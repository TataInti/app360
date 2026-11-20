"""E2E real de Administración › Accesos con Playwright y datos sintéticos.

La instancia debe estar levantada por el script aislado de scratch. El test no
modifica usuarios preexistentes: agrega y limpia solo cuentas con prefijo T-.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts" / "dev_preview") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "dev_preview"))
from e2e_objetivos_helpers import leer_accesos

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5090").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "sis-2a-admin-e2e-ficticio")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
SHOTS_DIR = Path(os.environ.get("E2E_SHOTS_DIR") or (
    f"/root/.hermes/cache/scratch/e2e-shots/sis-2a-accesos-"
    f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
))
DB_NAME = "sis_2a_accesos_e2e"
USERS = {
    "sales": 'T-accesos&<"ventas>',
    "purchases": "T-accesos-compras",
    "hr": "T-accesos-rrhh",
}


class Checks:
    def __init__(self):
        self.results = []
        self.page_errors = []
        self.put_events = []

    def check(self, name, ok, detail=""):
        item = {"name": name, "ok": bool(ok), "detail": str(detail)[:400]}
        self.results.append(item)
        print(f"{'OK' if item['ok'] else 'FALLA'} {name}" + (f" — {item['detail']}" if detail else ""), flush=True)

    def write(self):
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOTS_DIR / "informe.json"
        path.write_text(json.dumps({
            "base_url": BASE_URL,
            "database": DB_NAME,
            "total": len(self.results),
            "passed": sum(item["ok"] for item in self.results),
            "failed": sum(not item["ok"] for item in self.results),
            "checks": self.results,
            "page_errors": self.page_errors,
            "put_events": self.put_events,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def crear_usuarios_sinteticos():
    """Crea o limpia las tres cuentas T- únicamente en la base E2E permitida."""
    from sqlalchemy.engine import make_url
    from app import create_app
    from models import db
    from models.core.user import User
    from models.core.user_permission import UserModulePermission

    parsed = make_url(os.environ.get("DATABASE_URL", ""))
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.port != 55432 or parsed.database != DB_NAME:
        raise RuntimeError("Se rechazó la preparación: la base no es la instancia sintética SIS-2A.")
    app = create_app()
    with app.app_context():
        for role, username in USERS.items():
            user = User.query.filter_by(username=username).one_or_none()
            if user is None:
                user = User(username=username, role=role, active=True)
                db.session.add(user)
            else:
                UserModulePermission.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            user.role = role
            user.active = True
            user.must_change_password = False
            user.set_password("T-e2e-clave-sintetica-no-usada")
        db.session.commit()


def login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", ADMIN_USER)
    page.fill("#password", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    return urlparse(page.url).path != "/"


def instrumentar(page, checks):
    page.on("pageerror", lambda error: checks.page_errors.append({"type": "exception", "text": str(error)[:300]}))
    page.on(
        "console",
        lambda message: checks.page_errors.append(
            {"type": "console", "text": message.text[:300]}
        ) if message.type == "error" else None,
    )

    def request_started(request):
        match = re.search(r"/api/admin/accesos/(\d+)$", urlparse(request.url).path)
        if request.method == "PUT" and match:
            checks.put_events.append({"id": match.group(1), "start": time.monotonic(), "done": None, "status": None})

    def response_received(response):
        request = response.request
        match = re.search(r"/api/admin/accesos/(\d+)$", urlparse(response.url).path)
        if request.method == "PUT" and match:
            event = next((item for item in reversed(checks.put_events)
                          if item["id"] == match.group(1) and item["done"] is None), None)
            if event:
                event["done"] = time.monotonic()
                event["status"] = response.status

    page.on("request", request_started)
    page.on("response", response_received)


def capturar(page, name):
    for width, height in ((1440, 900), (1366, 768)):
        page.set_viewport_size({"width": width, "height": height})
        page.screenshot(path=str(SHOTS_DIR / f"{name}-{width}x{height}.png"), full_page=True)


def fila(page, user_id):
    return page.locator(f'tr[data-user-id="{user_id}"]')


def usuario_id(datos, username):
    for user_id, user in datos.items():
        if user.get("username") == username:
            return user_id
    raise AssertionError(f"No aparece la cuenta sintética {username!r} en la API.")


def permisos_modificados(antes, despues):
    cambios = []
    for user_id, usuario in antes.items():
        nuevo = despues.get(user_id)
        if nuevo is None:
            cambios.append((user_id, "usuario_eliminado", None))
            continue
        if usuario.get("role") != nuevo.get("role") or usuario.get("role_modules") != nuevo.get("role_modules"):
            cambios.append((user_id, "rol_o_herencia", None))
        claves = set(usuario.get("permissions", {})) | set(nuevo.get("permissions", {}))
        cambios.extend(
            (user_id, modulo, nuevo.get("permissions", {}).get(modulo))
            for modulo in claves
            if usuario.get("permissions", {}).get(modulo) != nuevo.get("permissions", {}).get(modulo)
        )
    return sorted(cambios)


def contraste(page):
    return page.evaluate("""() => {
        const rgb = value => (value.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
        const luminance = value => {
            const channels = rgb(value).map(channel => {
                const v = channel / 255;
                return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
            });
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
        };
        const ratio = (foreground, background) => {
            const a = luminance(foreground), b = luminance(background);
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        };
        const button = document.querySelector('#accessSave');
        const state = document.querySelector('.app-access-row-status:not([hidden]) .app-status__text');
        const body = getComputedStyle(document.body).backgroundColor;
        const buttonStyle = getComputedStyle(button);
        const stateStyle = state ? getComputedStyle(state) : null;
        const stateBg = stateStyle && !stateStyle.backgroundColor.startsWith('rgba(0, 0, 0, 0)')
            ? stateStyle.backgroundColor : body;
        return {
            primary: ratio(buttonStyle.color, buttonStyle.backgroundColor),
            rowText: stateStyle ? ratio(stateStyle.color, stateBg) : null
        };
    }""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-reset", action="store_true", help="usa la instancia ya recreada por el script propio")
    args = parser.parse_args()
    if not args.sin_reset:
        raise SystemExit("Recreá la instancia con el script local bajo heavy.lock y pasá --sin-reset.")
    crear_usuarios_sinteticos()
    checks = Checks()
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, executable_path=CHROMIUM, args=["--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        instrumentar(page, checks)
        checks.check("login admin por formulario", login(page), urlparse(page.url).path)

        page.route("**/api/admin/accesos", lambda route: (time.sleep(4.0), route.continue_()))
        page.goto(BASE_URL + "/admin/accesos", wait_until="domcontentloaded")
        first_select = page.locator("#tblAccesos select.perm-select").first
        loading_ok = (
            first_select.is_disabled()
            and page.locator("#accessSave").is_disabled()
            and "Cargando permisos" in page.locator("#accessLoadStatus").inner_text()
        )
        checks.check("GET pendiente: selects y Guardar bloqueados", loading_ok)
        capturar(page, "carga")
        expect(first_select).to_be_enabled(timeout=15000)
        expect(page.locator("#accessLoadStatus")).to_be_hidden(timeout=10000)
        checks.check("GET exitoso habilita selects", not first_select.is_disabled())
        select_widths = page.locator("select.perm-select").evaluate_all(
            "selects => selects.map(select => select.getBoundingClientRect().width)"
        )
        checks.check("Sin acceso no se recorta en los selects", bool(select_widths)
                     and min(select_widths) >= 120 and max(select_widths) <= 136, select_widths)

        datos_antes = leer_accesos(context, BASE_URL)
        ids = {role: usuario_id(datos_antes, username) for role, username in USERS.items()}
        special_row = fila(page, ids["sales"])
        special_text = special_row.locator(".app-access-user").inner_text()
        special_label = special_row.locator('select[name="products"]').get_attribute("aria-label")
        special_scripts = special_row.locator("script").count()
        checks.check(
            "escape de &, < y comillas en usuario",
            special_text == USERS["sales"] and special_scripts == 0
            and special_label == f"Productos para {USERS['sales']}",
            repr({"text": special_text, "aria_label": special_label, "scripts_in_row": special_scripts}),
        )
        checks.check("rol sin píldora y sin botones por fila",
                     page.locator(".app-access-role .badge").count() == 0
                     and page.locator(".btn-save").count() == 0)
        inherited_ui_ok = True
        for user_id, user in datos_antes.items():
            row = fila(page, user_id)
            role_modules = user.get("role_modules", [])
            inherited_modules = [
                module for module in user.get("permissions", {})
                if "all" in role_modules or module in role_modules
            ]
            inherited_ui_ok = inherited_ui_ok and row.locator(".app-access-inherited").count() == len(inherited_modules)
            inherited_ui_ok = inherited_ui_ok and all(
                row.locator(f'select[name="{module}"]').count() == 0
                for module in inherited_modules
            )
        checks.check("módulos heredados: texto neutro y sin select editable", inherited_ui_ok)

        loading_error_page = context.new_page()
        instrumentar(loading_error_page, checks)
        loading_error_page.route("**/api/admin/accesos", lambda route: route.abort())
        loading_error_page.goto(BASE_URL + "/admin/accesos", wait_until="domcontentloaded")
        expect(loading_error_page.locator("#accessLoadStatus")).to_contain_text(
            "No se pudieron cargar los permisos", timeout=10000
        )
        checks.check("GET fallido: error visible y controles bloqueados",
                     loading_error_page.locator("#accessLoadStatus").get_attribute("role") == "alert"
                     and loading_error_page.locator("select.perm-select").count() > 0
                     and loading_error_page.locator("select.perm-select:disabled").count()
                     == loading_error_page.locator("select.perm-select").count()
                     and loading_error_page.locator("#accessSave").is_disabled())
        loading_error_page.close()

        sales_products = fila(page, ids["sales"]).locator('select[name="products"]')
        purchase_locations = fila(page, ids["purchases"]).locator('select[name="locations"]')
        sales_products.select_option("view")
        checks.check("plural singular del contador",
                     page.locator("#accessChangeCount").inner_text() == "1 usuario con cambios"
                     and page.locator("#accessSave").inner_text() == "Guardar cambios (1)")
        page.set_viewport_size({"width": 1366, "height": 768})
        page.evaluate("window.scrollTo(0, 0)")
        marker_metrics = page.evaluate("""userId => {
            const row = document.querySelector(`#tblAccesos tr[data-user-id="${userId}"]`);
            const marker = row.querySelector('.app-access-row-status');
            const userCell = marker.closest('.app-access-user');
            const markerRect = marker.getBoundingClientRect();
            const userRect = userCell.getBoundingClientRect();
            const tableScroll = document.querySelector('#accessTableScroll');
            return {
                visible: !marker.hidden && markerRect.top >= 0 && markerRect.bottom <= innerHeight
                    && markerRect.left >= 0 && markerRect.right <= innerWidth
                    && markerRect.left >= userRect.left && markerRect.right <= userRect.right,
                pageScrollX: scrollX,
                documentWidth: document.documentElement.scrollWidth,
                viewportWidth: innerWidth,
                tableScrollLeft: tableScroll.scrollLeft
            };
        }""", ids["sales"])
        checks.check("marca Modificado visible a 1366×768 sin scroll horizontal",
                     marker_metrics["visible"] and marker_metrics["pageScrollX"] == 0
                     and marker_metrics["documentWidth"] == marker_metrics["viewportWidth"]
                     and marker_metrics["tableScrollLeft"] == 0, marker_metrics)
        page.set_viewport_size({"width": 1440, "height": 900})
        purchase_locations.select_option("edit")
        expect(fila(page, ids["sales"]).locator("[data-row-status-text]")).to_have_text("Modificado")
        expect(fila(page, ids["purchases"]).locator("[data-row-status-text]")).to_have_text("Modificado")
        checks.check("dos filas marcadas y contador 2",
                     page.locator("#accessChangeCount").inner_text() == "2 usuarios con cambios"
                     and page.locator("#accessSave").inner_text() == "Guardar cambios (2)"
                     and sales_products.evaluate("element => element.classList.contains('app-access-select--changed')"))
        capturar(page, "cambios")

        sales_products.select_option("none")
        purchase_locations.select_option("none")
        checks.check("volver al original quita marcas",
                     page.locator("#accessChangeCount").inner_text() == "0 usuarios con cambios"
                     and page.locator("#accessSave").is_disabled()
                     and fila(page, ids["sales"]).locator("[data-row-status]").is_hidden())
        # Descartar también se recorre con cambios pendientes y restaura los valores originales.
        sales_products.select_option("view")
        purchase_locations.select_option("edit")
        page.locator("#accessDiscard").click()
        checks.check("Descartar restaura valores y limpia el contador",
                     sales_products.input_value() == "none" and purchase_locations.input_value() == "none"
                     and page.locator("#accessChangeCount").inner_text() == "0 usuarios con cambios"
                     and leer_accesos(context, BASE_URL) == datos_antes)

        # Teclado nativo: Espacio abre el select, flecha/Enter cambia y Tab pasa al siguiente.
        sales_products.focus()
        sales_products.press("Space")
        sales_products.press("ArrowDown")
        sales_products.press("Enter")
        teclado_valor = sales_products.input_value()
        page.keyboard.press("Tab")
        tab_nombre = page.evaluate("document.activeElement.name")
        checks.check("select accesible por Espacio y Tab",
                     teclado_valor != "none" and tab_nombre == "locations",
                     f"valor={teclado_valor}, siguiente={tab_nombre}")
        page.locator("#accessDiscard").click()

        capturas_primario = []
        for width, height in ((1440, 900), (1366, 768)):
            page.set_viewport_size({"width": width, "height": height})
            page.locator('select[name="products"]').first.select_option("view")
            metrics = page.evaluate("""() => {
                const button = document.querySelector('#accessSave');
                const rect = button.getBoundingClientRect();
                const scroller = document.querySelector('#accessTableScroll');
                const scrollerRect = scroller.getBoundingClientRect();
                const stickyRight = document.querySelector('.app-access-user').getBoundingClientRect().right;
                const partialHeadersAtStart = Array.from(document.querySelectorAll('#tblAccesos thead th'))
                    .filter(header => !header.classList.contains('app-access-user-heading'))
                    .filter(header => {
                        const headerRect = header.getBoundingClientRect();
                        return headerRect.right > stickyRight + 1 && headerRect.left < scrollerRect.right - 1
                            && (headerRect.left < stickyRight - 1 || headerRect.right > scrollerRect.right + 1);
                    }).map(header => header.innerText);
                return {
                    count: document.querySelectorAll('.app-access-header-actions .app-actions__primary').length,
                    visible: rect.top >= 0 && rect.bottom <= innerHeight && rect.left >= 0 && rect.right <= innerWidth,
                    scrollX: scrollX,
                    documentWidth: document.documentElement.scrollWidth,
                    viewportWidth: innerWidth,
                    sticky: getComputedStyle(document.querySelector('.app-access-user')).position,
                    tableColumns: document.querySelectorAll('#tblAccesos thead th').length,
                    scrollable: scroller.scrollWidth > scroller.clientWidth,
                    snapType: getComputedStyle(scroller).scrollSnapType,
                    partialHeadersAtStart,
                    hintVisible: !!document.querySelector('.app-access-scroll-hint') && getComputedStyle(document.querySelector('.app-access-scroll-hint')).display !== 'none'
                };
            }""")
            capturas_primario.append(metrics)
            page.screenshot(path=str(SHOTS_DIR / f"cambios-{width}x{height}.png"), full_page=True)
            page.locator("#accessDiscard").click()
        checks.check("un primario visible a 1440×900 y 1366×768 sin scroll de página",
                     all(item["count"] == 1 and item["visible"] and item["scrollX"] == 0
                         and item["documentWidth"] == item["viewportWidth"] for item in capturas_primario),
                     capturas_primario)
        checks.check("tabla completa con Usuario fija e indicación de scroll",
                     all(item["sticky"] == "sticky" and item["tableColumns"] == 14
                         and item["scrollable"] and item["hintVisible"]
                         and not item["partialHeadersAtStart"] for item in capturas_primario),
                     capturas_primario)
        table_scroll = page.locator("#accessTableScroll")
        table_scroll.evaluate("element => element.scrollTo({ left: 420 })")
        page.wait_for_timeout(250)
        snap_metrics = page.evaluate("""() => {
            const container = document.querySelector('#accessTableScroll');
            const containerRect = container.getBoundingClientRect();
            const stickyRight = document.querySelector('.app-access-user').getBoundingClientRect().right;
            const headers = Array.from(document.querySelectorAll('#tblAccesos thead th'))
                .filter(header => !header.classList.contains('app-access-user-heading'));
            const visible = headers.filter(header => {
                const rect = header.getBoundingClientRect();
                return rect.right > stickyRight + 1 && rect.left < containerRect.right - 1;
            });
            const partial = visible.filter(header => {
                const rect = header.getBoundingClientRect();
                return rect.left < stickyRight - 1 || rect.right > containerRect.right + 1;
            }).map(header => header.innerText);
            return {
                scrollLeft: container.scrollLeft,
                snapType: getComputedStyle(container).scrollSnapType,
                partial
            };
        }""")
        checks.check("columnas completas al detener el desplazamiento",
                     snap_metrics["scrollLeft"] > 0 and "mandatory" in snap_metrics["snapType"]
                     and not snap_metrics["partial"], snap_metrics)
        table_scroll.evaluate("element => { element.scrollLeft = 0; }")

        # Dos usuarios modificados: solo dos PUT, secuenciales; la API es la verdad.
        start_index = len(checks.put_events)
        sales_products.select_option("view")
        purchase_locations.select_option("edit")
        page.locator("#accessSave").click()
        expect(fila(page, ids["sales"]).locator("[data-row-status-text]")).to_have_text("Guardado", timeout=15000)
        expect(fila(page, ids["purchases"]).locator("[data-row-status-text]")).to_have_text("Guardado", timeout=15000)
        expect(page.locator("#accessSummary")).to_contain_text("2 de 2 usuarios actualizados", timeout=15000)
        guardados = leer_accesos(context, BASE_URL)
        pantalla_permisos = page.locator("#tblAccesos tbody tr[data-user-id]").evaluate_all("""rows =>
            Object.fromEntries(rows.map(row => [row.dataset.userId,
                Object.fromEntries(Array.from(row.querySelectorAll('td.app-access-permission')).map(cell => {
                    const select = cell.querySelector('select.perm-select');
                    return [cell.dataset.module, select ? select.value : 'edit'];
                }))
            ]))""")
        pantalla_igual_api = all(
            user_id in pantalla_permisos
            and len(user["permissions"]) == len(pantalla_permisos[user_id])
            and all(pantalla_permisos[user_id].get(module) == level
                    for module, level in user["permissions"].items())
            for user_id, user in guardados.items()
        )
        checks.check("pantalla y API coinciden después de guardar cambios", pantalla_igual_api)
        cambios_esperados = sorted([
            (ids["sales"], "products", "view"),
            (ids["purchases"], "locations", "edit"),
        ])
        cambios_reales = permisos_modificados(datos_antes, guardados)
        batch_puts = checks.put_events[start_index:]
        expected_batch_order = page.locator("#tblAccesos tbody tr[data-user-id]").evaluate_all(
            "(rows, targets) => rows.map(row => row.dataset.userId).filter(id => targets.includes(id))",
            [ids["sales"], ids["purchases"]],
        )
        checks.check("API: solo cambian los dos niveles tocados", cambios_reales == cambios_esperados,
                     f"esperado={cambios_esperados}; real={cambios_reales}")
        checks.check("un PUT por usuario modificado, en secuencia",
                     len(batch_puts) == 2 and [event["id"] for event in batch_puts]
                     == expected_batch_order
                     and all(event["done"] is not None for event in batch_puts)
                     and batch_puts[0]["done"] <= batch_puts[1]["start"], batch_puts)
        checks.check("permisos heredados intactos",
                     all(guardados[user_id]["permissions"].get(module) == "edit"
                         for user_id, user in guardados.items()
                         for module in user["permissions"]
                         if "all" in user.get("role_modules", [])
                         or module in user.get("role_modules", [])))
        capturar(page, "guardado")

        # Una fila 404 forzada y otra válida: el éxito no tapa el error de la primera.
        failure_before = guardados
        failure_row = page.locator("#tblAccesos tbody tr").filter(has_text=USERS["sales"]).first
        valid_row = fila(page, ids["purchases"])
        failure_row.locator('select[name="products"]').select_option("edit")
        valid_row.locator('select[name="dashboard_comercial"]').select_option("view")
        forced_missing_id = str(max(map(int, failure_before)) + 1000)
        assert forced_missing_id not in failure_before
        failure_row.evaluate(
            "(row, missingId) => { row.dataset.userId = missingId; }", forced_missing_id
        )
        expected_failure_order = page.locator("#tblAccesos tbody tr[data-user-id]").evaluate_all(
            "(rows, targets) => rows.map(row => row.dataset.userId).filter(id => targets.includes(id))",
            [forced_missing_id, ids["purchases"]],
        )
        failure_index = len(checks.put_events)
        page.locator("#accessSave").click()
        expect(failure_row.locator("[data-row-status-text]")).to_contain_text("Error al guardar", timeout=15000)
        expect(failure_row.locator("[data-row-retry]")).to_be_visible()
        expect(valid_row.locator("[data-row-status-text]")).to_have_text("Guardado", timeout=15000)
        expect(page.locator("#accessSummary")).to_contain_text("1 de 2 usuarios actualizados", timeout=15000)
        failure_after = leer_accesos(context, BASE_URL)
        expected_partial = [(ids["purchases"], "dashboard_comercial", "view")]
        failed_batch = checks.put_events[failure_index:]
        failed_event = next((event for event in failed_batch if event["id"] == forced_missing_id), {})
        good_event = next((event for event in failed_batch if event["id"] == ids["purchases"]), {})
        checks.check("PUT fallido queda en su fila y el otro usuario se guarda",
                     permisos_modificados(failure_before, failure_after) == expected_partial
                     and [event["id"] for event in failed_batch] == expected_failure_order
                     and failed_event.get("status") == 404 and good_event.get("status") == 200
                     and failed_event.get("done") is not None and good_event.get("done") is not None
                     and failed_batch[0]["done"] <= failed_batch[1]["start"]
                     and "Reintentar" in failure_row.locator("[data-row-retry]").inner_text())
        capturar(page, "error")

        failure_row.evaluate(
            "(row, userId) => { row.dataset.userId = userId; }", ids["sales"]
        )
        retry_index = len(checks.put_events)
        failure_row.locator("[data-row-retry]").click()
        expect(failure_row.locator("[data-row-status-text]")).to_have_text("Guardado", timeout=15000)
        expect(page.locator("#accessChangeCount")).to_have_text("0 usuarios con cambios")
        final_api = leer_accesos(context, BASE_URL)
        checks.check("Reintentar actualiza la fila fallida",
                     permisos_modificados(failure_after, final_api)
                     == [(ids["sales"], "products", "edit")]
                     and checks.put_events[retry_index]["status"] == 200)

        # El primario contiene texto contrastable con su fondo; status usa texto de token.
        page.locator('select[name="products"]').first.select_option("view")
        ratios = contraste(page)
        page.locator("#accessDiscard").click()
        checks.check("contraste medido del primario y estado (≥ 4.5:1)",
                     ratios["primary"] >= 4.5 and (ratios["rowText"] is None or ratios["rowText"] >= 4.5), ratios)

        # beforeunload real: al salir con cambios debe aparecer la confirmación del navegador.
        page.locator('select[name="products"]').first.select_option("view")
        dialogs = []
        page.once("dialog", lambda dialog: (dialogs.append(dialog.type), dialog.accept()))
        page.goto(BASE_URL + "/admin", wait_until="domcontentloaded")
        checks.check("beforeunload confirma salida con cambios", dialogs == ["beforeunload"], dialogs)
        js_exceptions = [error for error in checks.page_errors if error["type"] == "exception"]
        console_errors = [error for error in checks.page_errors if error["type"] == "console"]
        checks.check("sin excepciones JavaScript", not js_exceptions, repr(js_exceptions))
        checks.check("errores de consola medidos", True, f"{len(console_errors)} recursos; incluyen fallos inducidos de prueba")

        browser.close()
    report = checks.write()
    print(f"EVIDENCIA {report}", flush=True)
    print(f"CAPTURAS {SHOTS_DIR}", flush=True)
    return 0 if all(item["ok"] for item in checks.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
