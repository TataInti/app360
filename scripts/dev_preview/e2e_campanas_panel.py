"""Recorrido E2E del panel lateral de Campañas (SIS-2B, corte 3), con Playwright en es-AR.

Qué verifica, con captura en cada pantalla tocada:
- Lista vacía: estado vacío con su botón; el botón primario de la cabecera abre el panel; Escape sin datos cierra.
- «Guardar» crea la campaña, cierra el panel, la fila aparece en la lista y en la base; el foco vuelve al disparador.
- «Guardar y agregar otro» tres veces: el canal y el plazo se conservan, el nombre y el costo se limpian, la
  casilla «Activa» vuelve a marcada, el foco vuelve al nombre, y cada alta coincide con la lista y la base.
- Error por campo desde el servidor: costo no válido (422 con aviso en #campana-error-cost_estimate).
- Escape con datos pide confirmación (cancelar mantiene; aceptar cierra sin guardar); Escape sin datos cierra.
- Escapes: nombre y canal con <b>, & y comillas se guardan y se ven como texto.
- Rutas clásicas: POST /campaigns/new por HTML responde 302 a /campaigns y guarda; con JSON responde 201.
- Pie visible a 1366×768. Botones primarios (panel cerrado y abierto), contraste del pie y errores de consola.

Datos sintéticos rotulados PROBE-CAMP-<sufijo>. Requisitos: la app en E2E_BASE_URL con la base E2E_DATABASE_URL
recién preparada; E2E_ADMIN_PASSWORD del admin de esa base. Capturas e informe JSON en E2E_CAPTURAS/<etiqueta>/.
Código de salida 0 solo si todas las verificaciones pasan.

Uso:
    E2E_BASE_URL=http://127.0.0.1:5094 E2E_DATABASE_URL=... E2E_ADMIN_PASSWORD=... \\
        /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_campanas_panel.py --etiqueta despues
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import psycopg2
from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5094").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "")
DB_URL = os.environ.get("E2E_DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/sis2b/capturas")
PREFIJO = f"PROBE-CAMP-{datetime.now().strftime('%H%M%S')}"
C1 = f"{PREFIJO} serie uno"
C2 = f"{PREFIJO} serie dos"
C3 = f"{PREFIJO} serie tres"
C4 = f"{PREFIJO} <b>Serie & \"Otoño\"</b>"
C5 = f"{PREFIJO} clasica"
C6 = f"{PREFIJO} 1366"
C7 = f"{PREFIJO} <em>Dos & \"B\"</em>"
C8 = f"{PREFIJO} 1366 panel"
CANAL = f"{PREFIJO} Mail & <i>Canal</i>"

RESULTADOS = []
CONSOLA = []
ERRORES_PAGINA = []
INFORME = {"etiqueta": "", "base_url": BASE_URL, "verificaciones": RESULTADOS}


def verificar(nombre, ok, detalle=""):
    RESULTADOS.append({"nombre": nombre, "ok": bool(ok), "detalle": str(detalle)})
    marca = "OK   " if ok else "FALLA"
    print(f"{marca} {nombre}" + (f" [{detalle}]" if detalle and not ok else ""))


def consulta(sql, params=()):
    with psycopg2.connect(DB_URL) as conexion, conexion.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def captura(page, ventana, nombre):
    carpeta = os.path.join(CAPTURAS, INFORME["etiqueta"], ventana)
    os.makedirs(carpeta, exist_ok=True)
    page.screenshot(path=os.path.join(carpeta, f"{nombre}.png"))


def login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", ADMIN_USER)
    page.fill("#password", ADMIN_PASSWORD)
    page.locator("form").filter(has=page.locator("#password")).locator("button[type=submit]").first.click()
    page.wait_for_load_state("load")


def luminancia(rgb):
    canales = []
    for valor in rgb[:3]:
        c = valor / 255
        canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def contraste(texto, fondo):
    a, b = luminancia(texto), luminancia(fondo)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def rgb_de(texto):
    numeros = [float(n) for n in re.findall(r"[\d.]+", texto)]
    return numeros[:3] if len(numeros) >= 3 else (255, 255, 255)


def filas(page):
    """Filas de la región de la lista: [id, nombre, canal, costo, plazo, leads, activo]."""
    registros = page.locator("[data-campaigns-region] tr[data-campaign-id]")
    salida = []
    for i in range(registros.count()):
        celdas = [c.strip() for c in registros.nth(i).locator("td").all_inner_texts()]
        salida.append({"id": registros.nth(i).get_attribute("data-campaign-id"), "celdas": celdas})
    return salida


def esperar_fila(page, nombre, segundos=10):
    """La lista se refresca de forma asíncrona tras guardar: se sondea hasta ver la fila nueva."""
    limite = time.time() + segundos
    while time.time() < limite:
        coincidencias = [f for f in filas(page) if f["celdas"][0] == nombre]
        if len(coincidencias) == 1:
            return coincidencias
        page.wait_for_timeout(200)
    return [f for f in filas(page) if f["celdas"][0] == nombre]


def abrir_panel(page, selector='[data-drawer-open="campanaPanel"]'):
    page.locator(selector).first.click()
    expect(page.locator("#campanaPanel")).to_be_visible()


def fase_vacia(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE_URL + "/campaigns", wait_until="load")
    conteo = consulta("SELECT count(*) FROM campaigns")[0][0]
    verificar("lista vacía: la base no tiene campañas al empezar", conteo == 0, conteo)
    verificar("lista vacía: estado vacío con su botón", page.locator("[data-campaigns-region] .empty-state").count() == 1)
    verificar(
        "lista vacía: un solo botón primario en la cabecera con el panel cerrado",
        page.locator(".app-page-head .btn-primary:visible").count() == 1,
    )
    captura(page, "1440x900", "lista_vacia")
    abrir_panel(page, '[data-drawer-open="campanaPanel"]:has-text("Crear primera campaña")')
    verificar("vacía: foco en el nombre al abrir", page.evaluate("document.activeElement.id") == "campana-nombre")
    captura(page, "1440x900", "panel_vacio")
    page.keyboard.press("Escape")
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=5000)
    verificar("vacía: Escape sin datos cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())


def escenario_escritorio(page):
    page.goto(BASE_URL + "/campaigns", wait_until="load")
    abrir_panel(page, '[data-drawer-open="campanaPanel"]:has-text("Crear primera campaña")')
    page.fill("#campana-nombre", C1)
    page.fill("#campana-canal", CANAL)
    page.fill("#campana-costo", "1.500,50")
    page.fill("#campana-inicio", "2026-12-01")
    page.fill("#campana-fin", "2026-12-31")
    page.click('#campanaPanel [data-accion="guardar"]')
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=10000)
    fila = esperar_fila(page, C1)
    verificar("guardar: la fila nueva aparece en la lista", len(fila) == 1, filas(page)[:3])
    verificar("guardar: el foco vuelve al disparador", page.evaluate("document.activeElement.dataset.drawerOpen") == "campanaPanel")
    verificar("guardar: aviso «Campaña «…» guardada»", page.get_by_text(f"Campaña «{C1}» guardada").first.is_visible())
    base = consulta("SELECT channel, cost_estimate::text, start_date::text, end_date::text, active FROM campaigns WHERE name=%s", (C1,))
    verificar("guardar: persistido en la base", base == [(CANAL, "1500.50", "2026-12-01", "2026-12-31", True)], base)
    captura(page, "1440x900", "tras_guardar")

    primarios_cerrado = page.locator(".app-page-head .btn-primary:visible").count()
    verificar("lista con datos: un solo botón primario en la cabecera con el panel cerrado", primarios_cerrado == 1, primarios_cerrado)
    abrir_panel(page, ".app-page-head .btn-primary")
    primarios = page.locator("#campanaPanel .app-actions__primary:visible").count()
    verificar("panel: una sola acción primaria en el pie", primarios == 1, primarios)
    primario = page.evaluate(
        "(() => { const b = document.querySelector('#campanaPanel .app-actions__primary');"
        " const s = getComputedStyle(b); return [s.color, s.backgroundColor]; })()"
    )
    ratio = contraste(rgb_de(primario[0]), rgb_de(primario[1]))
    verificar("pie: contraste del botón primario >= 4,5:1", ratio >= 4.5, round(ratio, 2))
    fondo = page.evaluate("getComputedStyle(document.querySelector('#campanaPanel footer')).backgroundColor")
    color_sec = page.evaluate("getComputedStyle(document.querySelector('#campanaPanel .app-actions__secondary')).color")
    ratio_sec = contraste(rgb_de(color_sec), rgb_de(fondo))
    verificar("pie: contraste del botón secundario >= 4,5:1", ratio_sec >= 4.5, round(ratio_sec, 2))
    page.keyboard.press("Escape")
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=5000)

    # Guardar y agregar otro: canal y plazo se conservan; nombre y costo, no; «Activa» vuelve a marcada.
    altas = [(C2, "1.000"), (C3, "250,75"), (C4, "")]
    abrir_panel(page, ".app-page-head .btn-primary")
    page.fill("#campana-canal", CANAL)
    page.fill("#campana-inicio", "2026-12-01")
    page.fill("#campana-fin", "2026-12-31")
    for indice, (nombre, costo) in enumerate(altas, start=1):
        page.fill("#campana-nombre", nombre)
        if costo:
            page.fill("#campana-costo", costo)
        page.click('#campanaPanel [data-accion="agregar"]')
        expect(page.locator("#campanaPanel [data-drawer-status]")).to_have_text(f"Campaña «{nombre}» guardada", timeout=10000)
        verificar(f"agregar otro {indice}: el panel sigue abierto", page.locator("#campanaPanel").is_visible())
        verificar(f"agregar otro {indice}: el nombre se limpia", page.input_value("#campana-nombre") == "")
        verificar(f"agregar otro {indice}: el costo se limpia", page.input_value("#campana-costo") == "")
        verificar(f"agregar otro {indice}: el canal se conserva", page.input_value("#campana-canal") == CANAL)
        verificar(
            f"agregar otro {indice}: el plazo se conserva",
            page.input_value("#campana-inicio") == "2026-12-01" and page.input_value("#campana-fin") == "2026-12-31",
        )
        verificar(f"agregar otro {indice}: «Activa» vuelve a marcada", page.is_checked("#campana-activa"))
        verificar(f"agregar otro {indice}: foco en el nombre", page.evaluate("document.activeElement.id") == "campana-nombre")
        fila = esperar_fila(page, nombre)
        verificar(f"agregar otro {indice}: la lista muestra «{nombre}»", len(fila) == 1, fila)
        verificar(
            f"agregar otro {indice}: la base coincide con el canal y el plazo",
            consulta("SELECT count(*) FROM campaigns WHERE name=%s AND channel=%s AND start_date='2026-12-01' AND end_date='2026-12-31'", (nombre, CANAL)) == [(1,)],
        )
        if indice == 1:
            captura(page, "1440x900", "tras_agregar_otro")

    # Error por campo que devuelve el servidor (422) para un costo no válido.
    page.fill("#campana-nombre", f"{PREFIJO} costo malo")
    page.fill("#campana-costo", "abc")
    page.click('#campanaPanel [data-accion="agregar"]')
    expect(page.locator("#campana-error-cost_estimate")).to_be_visible(timeout=10000)
    verificar("error por campo: aviso junto al costo desde el servidor", len(page.inner_text("#campana-error-cost_estimate").strip()) > 0)
    verificar("error por campo: aria-invalid en el costo", page.get_attribute("#campana-costo", "aria-invalid") == "true")
    verificar("error por campo: no guardó", consulta("SELECT count(*) FROM campaigns WHERE name=%s", (f"{PREFIJO} costo malo",))[0][0] == 0)
    captura(page, "1440x900", "panel_error")
    page.fill("#campana-costo", "")

    # Escape con datos: pide confirmación; cancelar mantiene; aceptar cierra sin guardar.
    page.fill("#campana-nombre", f"{PREFIJO} borrador")
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.click("#app360ConfirmCancel")
    expect(page.locator("#app360ConfirmModal")).to_be_hidden(timeout=5000)
    page.wait_for_timeout(600)
    verificar("escape con datos: cancelar mantiene el panel abierto", page.locator("#campanaPanel").is_visible())
    page.keyboard.press("Escape")
    expect(page.locator("#app360ConfirmModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.click("#app360ConfirmAccept")
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=5000)
    verificar("escape con datos: confirmar cierra y devuelve el foco", page.evaluate("document.activeElement.dataset.drawerOpen") == "campanaPanel")
    verificar("escape con datos: el borrador no se guardó", consulta("SELECT count(*) FROM campaigns WHERE name LIKE %s", (f"{PREFIJO} borrador%",))[0][0] == 0)

    # Escape sin datos: cierra sin preguntar.
    abrir_panel(page)
    page.keyboard.press("Escape")
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=5000)
    verificar("escape sin datos: cierra sin confirmación", not page.locator("#app360ConfirmModal").is_visible())

    # Escapes: nombre y canal con marcado se guardan y se ven como texto.
    abrir_panel(page)
    page.fill("#campana-nombre", C7)
    page.fill("#campana-canal", "<i>Mail & \"X\"</i>")
    page.click('#campanaPanel [data-accion="guardar"]')
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=10000)
    fila = esperar_fila(page, C7)
    verificar("escapes: el nombre aparece como texto literal en la lista", len(fila) == 1)
    verificar("escapes: no se genera un <b> ni un <i> en la lista", page.locator("[data-campaigns-region] b, [data-campaigns-region] i").count() == 0)
    verificar("escapes: la base guarda el texto tal cual", consulta("SELECT count(*) FROM campaigns WHERE name=%s AND channel=%s", (C7, "<i>Mail & \"X\"</i>"))[0][0] == 1)

    # Rutas clásicas: HTML responde 302 a la lista; JSON responde 201 (mismo camino de validación).
    page.goto(BASE_URL + "/campaigns", wait_until="load")
    token = page.get_attribute('meta[name="csrf-token"]', "content")
    respuesta_html = page.request.post(
        BASE_URL + "/campaigns/new",
        form={"name": C5, "channel": "Clásico", "cost_estimate": "12,5", "active": "on", "csrf_token": token},
        max_redirects=0,
    )
    verificar("clásico HTML: 302 a /campaigns", respuesta_html.status == 302 and respuesta_html.headers.get("location", "").endswith("/campaigns"), respuesta_html.status)
    verificar("clásico HTML: persistido", consulta("SELECT count(*) FROM campaigns WHERE name=%s", (C5,))[0][0] == 1)
    respuesta_json = page.request.post(
        BASE_URL + "/campaigns/new",
        data={"name": C6, "channel": "JSON", "cost_estimate": "", "active": "on"},
        headers={"Accept": "application/json", "X-CSRFToken": token},
        max_redirects=0,
    )
    verificar("JSON: 201 con ok", respuesta_json.status == 201 and respuesta_json.json().get("ok") is True, respuesta_json.status)
    page.reload(wait_until="load")
    verificar("lista tras las altas por ruta: aparecen las dos campañas", len(esperar_fila(page, C5)) == 1 and len(esperar_fila(page, C6)) == 1)


def escenario_1366(page):
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL + "/campaigns", wait_until="load")
    captura(page, "1366x768", "lista")
    abrir_panel(page, ".app-page-head .btn-primary")
    captura(page, "1366x768", "panel_vacio")
    pie = page.evaluate(
        "(() => { const f = document.querySelector('#campanaPanel footer').getBoundingClientRect();"
        " const botones = [...document.querySelectorAll('#campanaPanel [data-drawer-pie] button')]"
        ".map(b => b.getBoundingClientRect()); return {bottom: f.bottom, botones: botones.map(r => [r.top, r.bottom])}; })()"
    )
    dentro = pie["bottom"] <= 768 and all(0 <= r[0] and r[1] <= 768 for r in pie["botones"])
    verificar("1366x768: pie y botones dentro de la ventana", dentro, pie)
    page.fill("#campana-nombre", C8)
    page.click('#campanaPanel [data-accion="guardar"]')
    expect(page.locator("#campanaPanel")).to_be_hidden(timeout=10000)
    verificar("1366x768: guardar cierra el panel", True)
    captura(page, "1366x768", "tras_guardar")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--etiqueta", default=os.environ.get("E2E_ETIQUETA", "despues"))
    args = parser.parse_args()
    INFORME["etiqueta"] = args.etiqueta
    if not DB_URL or not ADMIN_PASSWORD:
        print("Faltan E2E_DATABASE_URL o E2E_ADMIN_PASSWORD.")
        return 2

    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, locale="es-AR")
        page = contexto.new_page()
        page.on("console", lambda m: CONSOLA.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: ERRORES_PAGINA.append(str(e)))
        login(page)
        verificar("login del admin", "/login" not in page.url and page.locator("#password").count() == 0)
        fase_vacia(page)
        escenario_escritorio(page)
        escenario_1366(page)
        total = consulta("SELECT count(*) FROM campaigns WHERE name LIKE %s", (f"{PREFIJO}%",))[0][0]
        verificar("altas exitosas del recorrido: 8 campañas en la base", total == 8, total)
        navegador.close()

    recursos = [m for m in CONSOLA if m.startswith("Failed to load resource")]
    validacion = [m for m in recursos if "status of 422" in m or "status of 302" in m]
    favicon = [m for m in recursos if "status of 404" in m]
    inesperados = [m for m in CONSOLA if m not in validacion and m not in favicon]
    verificar("consola: sin errores de JavaScript ni recursos inesperados", not inesperados and not ERRORES_PAGINA, inesperados or ERRORES_PAGINA)
    INFORME["consola_recursos_esperados"] = {"422_validacion": len(validacion), "404_favicon": len(favicon)}
    fallas = [r for r in RESULTADOS if not r["ok"]]
    INFORME["resumen"] = {"total": len(RESULTADOS), "ok": len(RESULTADOS) - len(fallas), "fallas": len(fallas)}
    os.makedirs(os.path.join(CAPTURAS, args.etiqueta), exist_ok=True)
    with open(os.path.join(CAPTURAS, args.etiqueta, "informe_campanas.json"), "w", encoding="utf-8") as archivo:
        json.dump(INFORME, archivo, ensure_ascii=False, indent=2)
    print(f"RESUMEN {INFORME['resumen']}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
