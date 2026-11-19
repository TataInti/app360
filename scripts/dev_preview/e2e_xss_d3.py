"""Acceptance E2E for D3 stored-XSS sinks and screen regressions.

Runs against the isolated D3 instance only. Data written to the database uses
synthetic D3 product/lead records; other text fixtures are injected into local
JSON responses by Playwright and are never persisted.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from datetime import date
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5060").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-ficticio")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
OUT = pathlib.Path("/root/.hermes/cache/scratch/d3/captures/after")
OUT.mkdir(parents=True, exist_ok=True)

IMG = '<img src=x onerror="window.__xss=1">'
SCRIPT = '<script>window.__xss=2</script>'
SVG = '"><svg onload=window.__xss=3>'
NORMAL = 'Pérez & Hijos S.A. — D\'Angelo "Especial"'
SKU_FIXTURE = "D3-XSS-ORIGINAL"
SKU_NEW = "D3-XSS-ALTA"
LEAD_EMAIL = "d3-xss-lead@example.invalid"
TODAY = date.today().isoformat()
PERIOD = TODAY[:7]

TEXT_KEYS = {
    "name", "nombre", "cliente", "supplier", "proveedor", "proveedor_nombre",
    "employee_name", "empleado", "descripcion", "description", "observaciones",
    "comment", "justificacion", "vendedor", "portador", "instrumento", "usuario",
    "label", "titulo", "title",
}

RESULT = {"base_url": BASE_URL, "out": str(OUT), "checks": [], "screenshots": [], "injected": {}}


def verify(name, condition, detail=""):
    ok = bool(condition)
    RESULT["checks"].append({"name": name, "ok": ok, "detail": str(detail)[:500]})
    print(("OK   " if ok else "FALLA") + name + (f" — {detail}" if detail else ""), flush=True)
    return ok


def seed_primary_fixtures():
    """Reuse only the synthetic product/lead created for the D3 local database."""
    database_url = os.environ.get("E2E_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Configurá DATABASE_URL para la base local app360_fix_d3")
    from sqlalchemy.engine import make_url
    parsed = make_url(database_url)
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.port != 55432 or parsed.database != "app360_fix_d3":
        raise RuntimeError("E2E D3 solo escribe en 127.0.0.1:55432/app360_fix_d3")
    os.environ.update({
        "PYTHON_DOTENV_DISABLED": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": database_url,
        "SECRET_KEY": "d3-local-secret-synthetic-only",
        "JWT_SECRET_KEY": "d3-local-jwt-synthetic-only",
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "FLASK_ENV": "development",
        "DEBUG": "False",
        "RATELIMIT_ENABLED": "False",
    })
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    from app import create_app
    from models import Product, db
    from models.crm.lead import Lead
    from models.crm.lead_stage_history import LeadStageHistory

    app = create_app()
    with app.app_context():
        product = Product.query.filter_by(sku=SKU_FIXTURE).first()
        lead = Lead.query.filter_by(email=LEAD_EMAIL).first()
        if product is None or lead is None:
            raise RuntimeError("Faltan los fixtures sintéticos D3 del producto o lead")
        previous_e2e_product = Product.query.filter_by(sku=SKU_NEW).first()
        if previous_e2e_product is not None:
            db.session.delete(previous_e2e_product)
        product.name = IMG
        product.description = NORMAL
        LeadStageHistory.query.filter_by(
            lead_id=lead.id, created_by="D3-E2E-XSS"
        ).delete(synchronize_session=False)
        db.session.add(LeadStageHistory(
            lead_id=lead.id, from_stage="nuevo", to_stage="contactado",
            comment=SVG, created_by="D3-E2E-XSS",
        ))
        lead.name = SCRIPT
        db.session.commit()


def _generic_text_injection(value, counter):
    if isinstance(value, list):
        for item in value:
            _generic_text_injection(item, counter)
    elif isinstance(value, dict):
        for key, item in list(value.items()):
            if key.lower() in TEXT_KEYS and isinstance(item, str) and item:
                replacement = (IMG, NORMAL, SCRIPT, SVG)[counter[0] % 4]
                value[key] = replacement
                counter[0] += 1
            else:
                _generic_text_injection(item, counter)


def _first_or_append(data, key, record):
    values = data.setdefault(key, [])
    if not values:
        values.append(record)
    else:
        values[0].update(record)
    return values[0]


def patch_response(path, data, counter):
    """Inject synthetic strings into real local response shapes; add rows if empty."""
    if path == "/ventas/criterio-clientes/datos":
        rows = data.setdefault("clientes", [])
        while len(rows) < 3:
            rows.append({"cliente": "Cliente D3", "criterio": "FAC", "actualizado_por": "D3", "actualizado_en": None})
        rows[0]["cliente"], rows[1]["cliente"], rows[2]["cliente"] = IMG, NORMAL, SCRIPT
    elif path == "/api/rrhh/empleados":
        for key in ("employees", "items"):
            rows = data.get(key)
            if isinstance(rows, list):
                while len(rows) < 3:
                    rows.append({"id": 930001 + len(rows), "is_active": True})
                for row, name in zip(rows[:3], (SVG, NORMAL, SCRIPT)):
                    row["name"] = name
                    row["first_name"] = name
                    row["last_name"] = "D3"
    elif path == "/api/compras":
        _first_or_append(data, "items", {
            "id": 930001, "supplier": SCRIPT, "supplier_id": 930002,
            "status": "borrador", "total_amount": 1234.5, "order_date": TODAY,
        })
    elif path == "/api/gastos/listar":
        _first_or_append(data, "gastos", {
            "fecha": TODAY, "descripcion": SVG, "categoria_nombre": NORMAL,
            "proveedor_nombre": SCRIPT, "instrumento": "Transferencia", "portador": "D'Angelo",
            "monto": 1234.5, "usuario": "D3 synthetic",
        })
    elif path == "/api/tesoreria/movimientos":
        _first_or_append(data, "movimientos", {
            "id": 930003, "fecha_hora": f"{TODAY}T12:00:00", "tipo": "ingreso",
            "monto": 1234.5, "descripcion": IMG, "instrumento": NORMAL,
            "categoria_gasto": "Concepto D3", "categoria_naturaleza": "ambos",
            "categoria_efecto": "suma", "proveedor": "D'Angelo", "portador": "D3",
            "estado": "activo", "usuario": "D3 synthetic",
        })
        data["total"] = max(int(data.get("total") or 0), 1)
        data["pages"] = max(int(data.get("pages") or 0), 1)
        data["current_page"] = 1
    elif path == "/api/tesoreria/arqueos":
        _first_or_append(data, "arqueos", {
            "id": 930004, "fecha": TODAY, "turno": "D3 mañana", "saldo_inicial": 1000.0,
            "ingresos_total": 500.0, "egresos_total": 100.0, "saldo_final": 1400.0,
            "diferencia": 0.0, "usuario": "D3 synthetic", "observaciones": SCRIPT,
        })
    elif path == "/api/tesoreria/instrumentos":
        rows = data.setdefault("instrumentos", [])
        if rows:
            rows[0]["nombre"] = SCRIPT
            if len(rows) > 1:
                rows[1]["nombre"] = NORMAL
    elif path == "/api/tesoreria/cta-cte-friar":
        data["cuenta"] = {
            "id": 930005, "proveedor_id": 930006, "proveedor": IMG,
            "saldo_inicial": 1000.0, "total_liquidaciones": 500.0, "total_pagos": 250.0,
            "saldo_actual": 1250.0, "observaciones": SVG, "editado_por": "D3",
            "fecha_edicion": f"{TODAY}T12:00:00", "created_at": f"{TODAY}T11:00:00",
            "updated_at": f"{TODAY}T12:00:00",
        }
    elif path == "/api/rrhh/adelantos":
        _first_or_append(data, "adelantos", {
            "id": 930007, "empleado": {"nombre": SVG}, "tipo": "adelanto_efectivo",
            "monto": 1234.5, "concepto": IMG, "fecha_solicitud": f"{TODAY}T12:00:00",
            "aprobado": True, "pagado": False, "liquidado": False,
        })
    elif path == "/api/rrhh/fichadas/resumen":
        _first_or_append(data, "registros", {
            "id": 930008, "empleado_id": 930009, "fecha": TODAY, "empleado": SCRIPT,
            "fichadas": 0, "esperadas": 2, "entrada_1": "—", "salida_1": "—",
            "entrada_2": "—", "salida_2": "—", "min_tarde": 0, "es_falta": True,
            "es_tarde": False, "fichada_faltante": False, "justificado": False,
        })
    elif path.startswith("/api/rrhh/liquidaciones") and isinstance(data.get("liquidaciones"), list):
        _first_or_append(data, "liquidaciones", {
            "id": 930010, "empleado_nombre": SVG, "empleado": {"nombre": SVG},
            "sueldo_base": 1000.0, "descuento_adelanto_efectivo": 10.0,
            "descuento_adelanto_mercaderia": 20.0, "descuento_cuota_prestamo": 30.0,
            "sueldo_neto": 940.0, "adelantos_efectivo_count": 1,
            "adelantos_mercaderia_count": 0, "prestamos_count": 0, "ya_liquidado": False,
            "fecha_liquidacion": f"{TODAY}T12:00:00",
        })
    return data


def open_page(context, path, *, generic=False):
    page = context.new_page()
    errors = {"page": [], "console": [], "http5xx": [], "http4xx": [], "patched": {}}
    page.on("pageerror", lambda error: errors["page"].append(str(error)[:300]))
    page.on("console", lambda message: errors["console"].append(message.text[:300]) if message.type == "error" else None)
    page.on("response", lambda response: errors["http5xx"].append(f"{response.status} {urlparse(response.url).path}") if response.status >= 500 else None)
    page.on("response", lambda response: errors["http4xx"].append(f"{response.status} {urlparse(response.url).path}") if 400 <= response.status < 500 else None)

    def handler(route):
        request_path = urlparse(route.request.url).path
        if not request_path.startswith("/api/") and request_path != "/ventas/criterio-clientes/datos":
            route.continue_()
            return
        try:
            response = route.fetch()
            if "application/json" not in (response.headers.get("content-type") or ""):
                route.fulfill(response=response)
                return
            data = response.json()
            counter = [0]
            if generic:
                _generic_text_injection(data, counter)
            patch_response(request_path, data, counter)
            if counter[0] or request_path in {
                "/ventas/criterio-clientes/datos", "/api/rrhh/empleados", "/api/compras",
                "/api/gastos/listar", "/api/tesoreria/movimientos", "/api/tesoreria/arqueos",
                "/api/tesoreria/cta-cte-friar", "/api/rrhh/adelantos", "/api/rrhh/fichadas/resumen",
            } or request_path.startswith("/api/rrhh/liquidaciones"):
                errors["patched"][request_path] = errors["patched"].get(request_path, 0) + 1
            route.fulfill(response=response, json=data)
        except Exception as error:
            errors["page"].append(f"JSON interception {request_path}: {type(error).__name__}: {error}")
            route.continue_()

    page.route("**/*", handler)
    response = page.goto(BASE_URL + path, wait_until="domcontentloaded", timeout=30000)
    if response is None or response.status >= 400:
        raise RuntimeError(f"No abrió {path}: {response.status if response else 'sin respuesta'}")
    if urlparse(page.url).path == "/":
        raise RuntimeError(f"Acceso redirigido al login al abrir {path}")
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    page.wait_for_timeout(500)
    return page, errors


def assert_safe(page, label, expected=()):
    page.wait_for_timeout(350)
    if page.evaluate("typeof window.__xss") != "undefined":
        raise AssertionError(f"{label}: window.__xss se ejecutó")
    if page.locator('[onerror*="window.__xss"], [onload*="window.__xss"]').count():
        raise AssertionError(f"{label}: quedó un handler XSS ejecutable en el DOM")
    injected_scripts = page.locator("script").evaluate_all(
        "nodes => nodes.filter(node => node.textContent.includes('window.__xss=2')).length"
    )
    if injected_scripts:
        raise AssertionError(f"{label}: se creó un nodo script con payload")
    visible = page.locator("body").inner_text()
    input_values = page.locator("input, textarea").evaluate_all("nodes => nodes.map(node => node.value).join('\\n')")
    rendered = visible + "\\n" + input_values
    for text in expected:
        if text not in rendered:
            raise AssertionError(f"{label}: el texto no se ve literal: {text!r}")
    for encoded in ("&amp;lt;", "&amp;gt;", "&amp;quot;"):
        if encoded in rendered:
            raise AssertionError(f"{label}: doble escapado visible ({encoded})")


def save_shot(page, name):
    target = OUT / name
    page.screenshot(path=str(target), full_page=True)
    RESULT["screenshots"].append(str(target))


def assert_clean(errors, label):
    unexpected = {key: errors[key] for key in ("page", "console", "http5xx", "http4xx") if errors[key]}
    if unexpected:
        raise AssertionError(f"{label}: errores inesperados de consola/red: {unexpected}")


def run_scenario(name, callback):
    try:
        callback()
    except Exception as error:
        verify(name, False, f"{type(error).__name__}: {error}")


def seed_check_screens(context):
    # Producto: listado, alta por CRUD del módulo y edición del producto guardado.
    page, errors = open_page(context, "/admin/stock")
    tab = page.locator("#tab-productos")
    if tab.count():
        tab.click()
        page.wait_for_timeout(250)
    new_buttons = page.locator("button[data-entidad][data-fields]")
    new_button = None
    for index in range(new_buttons.count()):
        candidate = new_buttons.nth(index)
        if candidate.is_visible() and re.search("Nuevo", candidate.inner_text(), re.I):
            new_button = candidate
            break
    if new_button is None:
        raise AssertionError("No aparece el alta de Productos en /admin/stock")
    new_button.click()
    page.locator("#modalEntidad.show").wait_for(timeout=10000)
    modal = page.locator("#modalEntidad")
    name_input = modal.locator('input[name="name"]')
    if not name_input.count():
        raise AssertionError("El modal de alta no contiene el campo name")
    create_name = SVG + " " + NORMAL
    name_input.fill(create_name)
    if modal.locator('input[name="sku"]').count():
        modal.locator('input[name="sku"]').fill(SKU_NEW)
    if modal.locator('input[name="description"]').count():
        modal.locator('input[name="description"]').fill(NORMAL)
    modal.locator('button[type="submit"]').click()
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    page.wait_for_timeout(500)
    if tab.count():
        tab.click()
        page.wait_for_timeout(300)
    assert_safe(page, "alta-producto-admin", (create_name, NORMAL))
    verify("alta de producto en /admin/stock", True, "texto XSS y caracteres especiales literales")

    # Editar mantiene el payload como valor de input, sin convertirlo en HTML.
    if tab.count() and tab.is_visible():
        tab.click()
        page.wait_for_timeout(200)
    row = page.locator("tr").filter(has_text=SKU_FIXTURE).first
    row.wait_for(timeout=10000)
    row.locator("button.btn-outline-primary").first.click()
    page.locator("#modalEntidad.show").wait_for(timeout=10000)
    edit_value = page.locator('#modalCampos input[name="name"]').input_value()
    if edit_value != IMG:
        raise AssertionError(f"El nombre editado no preserva el texto literal: {edit_value!r}")
    assert_safe(page, "edicion-producto-admin", (IMG,))
    save_shot(page, "product-admin-edit-after.png")
    verify("edición de producto en /admin/stock", True, "input.value literal; sin nodos inyectados")
    assert_clean(errors, "admin-stock")
    page.close()
    RESULT["injected"]["admin_stock"] = errors["patched"]

    page, errors = open_page(context, "/products")
    assert_safe(page, "products-list", (IMG, NORMAL, create_name))
    save_shot(page, "product-listing-after.png")
    verify("listado /products", True, "payloads visibles literalmente, window.__xss indefinido")
    assert_clean(errors, "products-list")
    page.close()
    RESULT["injected"]["products"] = errors["patched"]

    # Lead name y comentario almacenados en el historial.
    page, errors = open_page(context, "/leads")
    card = page.locator(".kanban-card").filter(has_text=SCRIPT).first
    card.wait_for(timeout=15000)
    assert_safe(page, "lead-card", (SCRIPT,))
    card.get_by_role("button", name=re.compile("Historial", re.I)).click()
    page.locator("#historyPanel.is-open").wait_for(timeout=10000)
    page.wait_for_timeout(500)
    history_text = page.locator("#historyList").inner_text()
    if not page.locator("#historyList").is_visible() or SVG not in history_text:
        raise AssertionError(f"Historial del lead no muestra SVG literal: {history_text!r}")
    assert_safe(page, "lead-history", ())
    save_shot(page, "lead-history-after.png")
    verify("nombre e historial de lead", True, "script y SVG visibles literalmente; sin ejecución")
    assert_clean(errors, "lead-history")
    page.close()
    RESULT["injected"]["leads"] = errors["patched"]


def run_screen(context, path, name, expected=(), *, generic=True, after=None):
    page, errors = open_page(context, path, generic=generic)
    if after:
        after(page)
    assert_safe(page, name, expected)
    assert_clean(errors, name)
    verify(name, True, f"sin ejecución XSS; responses modificadas={errors['patched']}")
    RESULT["injected"][name] = errors["patched"]
    save_shot(page, name.replace("/", "-") + "-after.png")
    page.close()


def main():
    seed_primary_fixtures()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, executable_path=CHROMIUM,
            args=["--no-sandbox", "--explicitly-allowed-ports=5060"],
        )
        context = browser.new_context(locale="es-AR", viewport={"width": 1440, "height": 1050})
        login = context.new_page()
        login.goto(BASE_URL + "/", wait_until="domcontentloaded")
        login.fill("#username", ADMIN_USER)
        login.fill("#password", ADMIN_PASSWORD)
        login.click('button[type="submit"]')
        login.wait_for_load_state("networkidle")
        if urlparse(login.url).path == "/":
            raise RuntimeError("Login de administrador sintético falló")
        login.close()

        run_scenario("producto-admin-products-lead", lambda: seed_check_screens(context))
        run_scenario("criterio-clientes", lambda: run_screen(
            context, "/ventas/criterio-clientes", "criterio-clientes", (IMG, NORMAL, SCRIPT)
        ))
        run_scenario("compras-overview", lambda: run_screen(
            context, "/compras", "compras-overview", (SCRIPT,)
        ))
        run_scenario("gastos", lambda: run_screen(
            context, "/gastos", "gastos", (SVG, NORMAL, SCRIPT)
        ))
        run_scenario("tesoreria-panel", lambda: run_screen(
            context, "/tesoreria", "tesoreria-panel", (), generic=True
        ))
        run_scenario("tesoreria-movimientos", lambda: run_screen(
            context, "/tesoreria/movimientos", "tesoreria-movimientos", (IMG, NORMAL)
        ))

        def check_arqueos():
            page, errors = open_page(context, "/tesoreria/arqueos")
            row_button = page.locator('button[onclick^="editarArqueo("]').first
            row_button.wait_for(timeout=10000)
            row_button.click()
            page.locator("#modalEditarArqueo.show").wait_for(timeout=10000)
            obs = page.locator("#editObservaciones")
            if obs.input_value() != SCRIPT:
                raise AssertionError(f"Observación de arqueo no literal: {obs.input_value()!r}")
            assert_safe(page, "tesoreria-arqueos", (SCRIPT,))
            save_shot(page, "tesoreria-arqueos-after.png")
            verify("tesoreria-arqueos", True, "observación en input literal; sin ejecución")
            assert_clean(errors, "tesoreria-arqueos")
            RESULT["injected"]["tesoreria-arqueos"] = errors["patched"]
            page.close()
        run_scenario("tesoreria-arqueos", check_arqueos)

        def check_friar():
            page, errors = open_page(context, "/tesoreria/cta-cte-friar")
            page.wait_for_timeout(500)
            assert_safe(page, "friar-account", ())
            provider_name = page.evaluate("typeof cuentaActual !== 'undefined' ? cuentaActual?.proveedor : null")
            if provider_name != IMG:
                raise AssertionError(f"El proveedor de la cuenta Friar no llegó literal: {provider_name!r}")
            edit = page.locator("#btnEditarSaldo")
            if not edit.count() or not edit.is_visible():
                raise AssertionError("No aparece la edición de la cuenta Friar para administrador")
            edit.click()
            page.locator("#modalEditarSaldo.show").wait_for(timeout=10000)
            if page.locator("#observacionesSaldo").input_value() != SVG:
                raise AssertionError("La observación de cuenta Friar no se ve literal en el modal")
            assert_safe(page, "friar-edit", (SVG,))
            save_shot(page, "friar-account-after.png")
            verify("cuenta Friar", True, "dato de proveedor y observación sintéticos; sin ejecución")
            assert_clean(errors, "friar")
            RESULT["injected"]["friar"] = errors["patched"]
            page.close()
        run_scenario("friar", check_friar)

        run_scenario("rrhh-panel", lambda: run_screen(
            context, "/rrhh", "rrhh-panel", (SVG, NORMAL, SCRIPT)
        ))
        run_scenario("rrhh-adelantos", lambda: run_screen(
            context, "/rrhh/adelantos", "rrhh-adelantos", (SVG, IMG)
        ))
        run_scenario("rrhh-ausentismo", lambda: run_screen(
            context, "/rrhh/ausentismo", "rrhh-ausentismo", (SCRIPT,)
        ))

        def check_liquidaciones():
            page, errors = open_page(context, "/rrhh/liquidaciones")
            button = page.get_by_role("button", name=re.compile("Previsualizar", re.I))
            button.click()
            page.wait_for_timeout(1000)
            assert_safe(page, "rrhh-liquidaciones", (SVG,))
            save_shot(page, "rrhh-liquidaciones-after.png")
            verify("rrhh-liquidaciones", True, f"respuesta de preview inyectada={errors['patched']}")
            assert_clean(errors, "rrhh-liquidaciones")
            RESULT["injected"]["rrhh-liquidaciones"] = errors["patched"]
            page.close()
        run_scenario("rrhh-liquidaciones", check_liquidaciones)

        run_scenario("panel-ejecutivo", lambda: run_screen(
            context, "/panel-ejecutivo", "panel-ejecutivo", (), generic=True
        ))
        run_scenario("bi", lambda: run_screen(
            context, "/bi", "bi", (), generic=True
        ))
        browser.close()

    report = OUT / "e2e_xss_d3.json"
    report.write_text(json.dumps(RESULT, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [check for check in RESULT["checks"] if not check["ok"]]
    verify("resumen sin fallas", not failures, f"{len(failures)} falla(s); informe={report}")
    report.write_text(json.dumps(RESULT, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise SystemExit(1)
    print(f"E2E_XSS_D3_OK checks={len(RESULT['checks'])} screenshots={len(RESULT['screenshots'])} report={report}")


if __name__ == "__main__":
    main()
